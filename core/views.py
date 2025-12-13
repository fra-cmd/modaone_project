# core/views.py

# ======================
# IMPORTS ESTÁNDAR PYTHON
# ======================
import os
import json
import base64
import time
from io import BytesIO
from datetime import timedelta

# ======================
# IMPORTS DJANGO
# ======================
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Q, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

# ======================
# LIBRERÍAS EXTERNAS
# ======================
from xhtml2pdf import pisa
import replicate
import requests

# ======================
# MODELOS Y FORMULARIOS
# ======================
from .models import (
    Producto, Variante, Carrito, ItemCarrito,
    Direccion, Orden, ItemOrden,
    ESTADOS_PEDIDO, RegistroTryOn
)
from .forms import ClienteRegistrationForm, DireccionForm


# ==================================================
# FUNCIONES AUXILIARES
# ==================================================

def is_staff_or_superuser(user):
    """Verifica permisos de Admin/Staff"""
    return user.is_staff or user.is_superuser


# ==================================================
# VISTAS PÚBLICAS (CLIENTE)
# ==================================================

def catalogo_digital(request):
    productos_list = Producto.objects.filter(activo=True).order_by('-fecha_creacion')

    query = request.GET.get('q')
    if query:
        productos_list = productos_list.filter(Q(nombre__icontains=query) | Q(descripcion__icontains=query))

    cat_filter = request.GET.get('categoria')
    if cat_filter:
        productos_list = productos_list.filter(categoria=cat_filter)

    marca_filter = request.GET.get('marca')
    if marca_filter:
        productos_list = productos_list.filter(marca=marca_filter)

    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    if min_price:
        productos_list = productos_list.filter(precio__gte=min_price)
    if max_price:
        productos_list = productos_list.filter(precio__lte=max_price)

    paginator = Paginator(productos_list, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    titulo = "Catálogo Completo"
    if cat_filter:
        titulo = f"Colección {cat_filter.capitalize()}"
    if marca_filter:
        titulo = f"Marca: {marca_filter.capitalize()}"

    contexto = {
        'productos': page_obj,
        'titulo': titulo,
        'cat_actual': cat_filter,
        'marca_actual': marca_filter
    }
    return render(request, 'core/catalogo.html', contexto)


def registro_cliente(request):
    if request.method == 'POST':
        form = ClienteRegistrationForm(request.POST)
        if form.is_valid():
            new_user = form.save(commit=False)
            new_user.set_password(form.cleaned_data['password'])
            new_user.save()
            return redirect('home')
    else:
        form = ClienteRegistrationForm()
    return render(request, 'core/registro.html', {'form': form, 'titulo': 'Registro'})


def agregar_al_carrito(request, variante_id):
    if request.method == 'POST' and request.user.is_authenticated:
        variante = get_object_or_404(Variante, id=variante_id)
        cantidad = int(request.POST.get('cantidad', '1'))

        if cantidad > variante.stock:
            messages.error(request, f'Stock insuficiente. Disponible: {variante.stock}')
            return redirect('home')

        carrito, _ = Carrito.objects.get_or_create(usuario=request.user)
        item, created = ItemCarrito.objects.get_or_create(
            carrito=carrito,
            variante=variante,
            defaults={'cantidad': cantidad, 'precio_unitario': variante.producto.precio}
        )
        if not created:
            item.cantidad += cantidad
            item.save()

        messages.success(request, f'Añadido: {variante.producto.nombre}')
        return redirect(request.META.get('HTTP_REFERER', 'home'))

    return redirect('login')


def agregar_desde_catalogo(request, producto_id):
    if request.method == 'POST':
        if not request.user.is_authenticated:
            return redirect('login')

        variante_id = request.POST.get('variante_id')
        if not variante_id:
            messages.error(request, "Selecciona una talla.")
            return redirect('home')

        variante = get_object_or_404(Variante, id=variante_id)

        carrito, _ = Carrito.objects.get_or_create(usuario=request.user)
        item, created = ItemCarrito.objects.get_or_create(
            carrito=carrito,
            variante=variante,
            defaults={'precio_unitario': variante.producto.precio}
        )
        if not created:
            item.cantidad += 1
            item.save()

        messages.success(request, "Producto añadido al carrito.")
        return redirect('home')
    return redirect('home')


@login_required
def ver_carrito(request):
    try:
        carrito = Carrito.objects.get(usuario=request.user)
        items = carrito.items.all()
        total_carrito = sum(item.subtotal for item in items)
    except Carrito.DoesNotExist:
        carrito, items, total_carrito = None, [], 0

    return render(request, 'core/carrito.html', {
        'items': items,
        'total_carrito': total_carrito,
        'titulo': 'Mi Carrito'
    })


@login_required
def eliminar_item(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(ItemCarrito, id=item_id, carrito__usuario=request.user)
        item.delete()
    return redirect('ver_carrito')


@login_required
def actualizar_cantidad(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(ItemCarrito, id=item_id, carrito__usuario=request.user)
        try:
            nueva = int(request.POST.get('cantidad'))
            if nueva <= 0:
                item.delete()
            elif nueva > item.variante.stock:
                messages.error(request, 'Stock insuficiente.')
            else:
                item.cantidad = nueva
                item.save()
        except ValueError:
            pass
    return redirect('ver_carrito')


@login_required
def checkout(request):
    try:
        carrito = Carrito.objects.get(usuario=request.user)
        items = carrito.items.all()
        if not items:
            return redirect('home')
        subtotal = sum(item.subtotal for item in items)
        total_items = items.count()
    except Carrito.DoesNotExist:
        return redirect('home')

    direcciones = Direccion.objects.filter(usuario=request.user).order_by('-predeterminada')

    if request.method == 'POST':
        form = DireccionForm(request.POST)
        if form.is_valid():
            nueva = form.save(commit=False)
            nueva.usuario = request.user
            if nueva.predeterminada:
                Direccion.objects.filter(usuario=request.user).update(predeterminada=False)
            nueva.save()
            return redirect('checkout')
    else:
        form = DireccionForm()

    costos = [
        {'id': 1, 'nombre': 'Courier Nacional', 'costo': 5990},
        {'id': 2, 'nombre': 'Flash Local', 'costo': 3990}
    ]

    return render(request, 'core/checkout.html', {
        'items': items,
        'subtotal': subtotal,
        'total_items': total_items,
        'direcciones_guardadas': direcciones,
        'direccion_form': form,
        'costos_envio': costos,
        'titulo': 'Checkout'
    })


@login_required
@transaction.atomic
def generar_orden(request):
    if request.method != 'POST':
        return redirect('checkout')

    direccion_id = request.POST.get('direccion_id')
    metodo_envio = request.POST.get('metodo_envio')
    email_contacto = request.POST.get('email_contacto')

    try:
        direccion = get_object_or_404(Direccion, id=direccion_id, usuario=request.user)
        carrito = Carrito.objects.get(usuario=request.user)
        items = list(carrito.items.all())
        if not items:
            return redirect('checkout')
    except Exception:
        messages.error(request, 'Error en los datos.')
        return redirect('checkout')

    costos = {'1': 5990, '2': 3990}
    envio_val = costos.get(metodo_envio, 0)
    subtotal = sum(i.subtotal for i in items)
    total = subtotal + envio_val

    orden = Orden.objects.create(
        usuario=request.user,
        email=email_contacto,
        subtotal=subtotal,
        costo_envio=envio_val,
        total_final=total,
        estado='PENDIENTE',
        direccion_envio=f"{direccion.calle} #{direccion.numero}, {direccion.comuna}",
    )

    for i in items:
        ItemOrden.objects.create(
            orden=orden,
            variante=i.variante,
            nombre_producto=i.variante.producto.nombre,
            talla_color=f"{i.variante.talla}/{i.variante.color}",
            cantidad=i.cantidad,
            precio_unitario=i.precio_unitario
        )
        i.variante.stock -= i.cantidad
        i.variante.save()

    carrito.delete()
    return redirect('pasarela_pago', orden_id=orden.id)
