# core/views.py

import os
import json
import base64
import requests
import time
from io import BytesIO
from datetime import timedelta

# Django Imports
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

# Librerías externas
from xhtml2pdf import pisa
import replicate

# Modelos y Formularios Locales
from .models import (
    Producto, Variante, Carrito, ItemCarrito, Direccion, 
    Orden, ItemOrden, ESTADOS_PEDIDO, RegistroTryOn
)
from .forms import ClienteRegistrationForm, DireccionForm


# ==========================================
# --- 1. FUNCIONES AUXILIARES & AUTH ---
# ==========================================

def is_staff_or_superuser(user):
    """Verifica permisos de Admin/Staff"""
    return user.is_staff or user.is_superuser

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

def staff_login_view(request):
    """Login exclusivo para el personal corporativo"""
    if request.user.is_authenticated and is_staff_or_superuser(request.user):
        return redirect('panel_admin')

    if request.method == 'POST':
        usuario = request.POST.get('username')
        clave = request.POST.get('password')
        user = authenticate(request, username=usuario, password=clave)

        if user is not None:
            if is_staff_or_superuser(user):
                login(request, user)
                return redirect('panel_admin') 
            else:
                messages.error(request, "No tienes permisos de acceso corporativo.")
        else:
            messages.error(request, "Credenciales inválidas.")
   
    return render(request, 'core/staff_login.html')


# ==========================================
# --- 2. CATÁLOGO Y NAVEGACIÓN ---
# ==========================================

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
    if min_price: productos_list = productos_list.filter(precio__gte=min_price)
    if max_price: productos_list = productos_list.filter(precio__lte=max_price)

    paginator = Paginator(productos_list, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    titulo = "Catálogo Completo"
    if cat_filter: titulo = f"Colección {cat_filter.capitalize()}"
    if marca_filter: titulo = f"Marca: {marca_filter.capitalize()}"

    contexto = {
        'productos': page_obj,
        'titulo': titulo,
        'cat_actual': cat_filter,
        'marca_actual': marca_filter
    }
    return render(request, 'core/catalogo.html', contexto)


# ==========================================
# --- 3. CARRITO DE COMPRAS ---
# ==========================================

def agregar_al_carrito(request, variante_id):
    if request.method == 'POST' and request.user.is_authenticated:
        variante = get_object_or_404(Variante, id=variante_id)
        cantidad = int(request.POST.get('cantidad', '1'))

        if cantidad > variante.stock:
            messages.error(request, f'Stock insuficiente. Disponible: {variante.stock}')
            return redirect('home')

        carrito, _ = Carrito.objects.get_or_create(usuario=request.user)
        item, created = ItemCarrito.objects.get_or_create(
            carrito=carrito, variante=variante,
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
            carrito=carrito, variante=variante,
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
        'items': items, 'total_carrito': total_carrito, 'titulo': 'Mi Carrito'
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
            if nueva <= 0: item.delete()
            elif nueva > item.variante.stock: messages.error(request, 'Stock insuficiente.')
            else:
                item.cantidad = nueva
                item.save()
        except ValueError: pass
    return redirect('ver_carrito')


# ==========================================
# --- 4. CHECKOUT Y ÓRDENES ---
# ==========================================

@login_required
def checkout(request):
    try:
        carrito = Carrito.objects.get(usuario=request.user)
        items = carrito.items.all()
        if not items: return redirect('home')
        subtotal = sum(item.subtotal for item in items)
        total_items = items.count()
    except Carrito.DoesNotExist: return redirect('home')

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
   
    costos = [{'id': 1, 'nombre': 'Courier Nacional', 'costo': 5990}, {'id': 2, 'nombre': 'Flash Local', 'costo': 3990}]

    return render(request, 'core/checkout.html', {
        'items': items, 'subtotal': subtotal, 'total_items': total_items,
        'direcciones_guardadas': direcciones, 'direccion_form': form, 'costos_envio': costos,
        'titulo': 'Checkout'
    })

@login_required
@transaction.atomic
def generar_orden(request):
    if request.method != 'POST': return redirect('checkout')

    direccion_id = request.POST.get('direccion_id')
    metodo_envio = request.POST.get('metodo_envio')
    email_contacto = request.POST.get('email_contacto')

    try:
        direccion = get_object_or_404(Direccion, id=direccion_id, usuario=request.user)
        carrito = Carrito.objects.get(usuario=request.user)
        items = list(carrito.items.all())
        if not items: return redirect('checkout')
    except:
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
            orden=orden, variante=i.variante, nombre_producto=i.variante.producto.nombre,
            talla_color=f"{i.variante.talla}/{i.variante.color}", cantidad=i.cantidad, precio_unitario=i.precio_unitario
        )
        i.variante.stock -= i.cantidad
        i.variante.save()
       
    carrito.delete()
    return redirect('pasarela_pago', orden_id=orden.id)

@login_required
def pasarela_pago(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id, usuario=request.user)
    if orden.estado != 'PENDIENTE': return redirect('home')
    return render(request, 'core/pasarela_pago.html', {'orden': orden})

@login_required
def procesar_pago_real(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id, usuario=request.user)
    if request.method == 'POST':
        orden.estado = 'CONFIRMADO'
        orden.save()
       
        # Generar PDF
        html = render_to_string('core/invoice.html', {'orden': orden})
        pdf = BytesIO()
        pisa.CreatePDF(html, dest=pdf)
       
        # Enviar Email
        if orden.email:
            email = EmailMessage(
                f'Tu Boleta - Orden #{orden.numero_orden}',
                f'Hola {orden.usuario.first_name}, tu compra está confirmada.',
                settings.EMAIL_HOST_USER, [orden.email]
            )
            email.attach(f'boleta_{orden.numero_orden}.pdf', pdf.getvalue(), 'application/pdf')
            try: email.send()
            except: pass

        return render(request, 'core/orden_confirmada.html', {'orden': orden})
    return redirect('home')

@login_required
def pago_simulado(request, orden_id):
    return redirect('pasarela_pago', orden_id=orden_id)

@login_required
def descargar_boleta(request, orden_id):
    orden = get_object_or_404(Orden, id=orden_id, usuario=request.user)
    html = render_to_string('core/invoice.html', {'orden': orden})
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Boleta_{orden.numero_orden}.pdf"'
    pisa.CreatePDF(html, dest=response)
    return response

@login_required
def mis_pedidos(request):
    ordenes = Orden.objects.filter(usuario=request.user).order_by('-fecha_creacion')
    return render(request, 'core/mis_pedidos.html', {'ordenes': ordenes, 'titulo': 'Mis Pedidos'})


# ==========================================
# --- 5. BACKOFFICE, BI Y CRM ---
# ==========================================

@user_passes_test(is_staff_or_superuser, login_url='staff_login')
def panel_admin_productos(request):
    return render(request, 'core/panel_admin.html', {'titulo': 'Panel Admin'})

@login_required
@user_passes_test(is_staff_or_superuser, login_url='staff_login')
def admin_ordenes(request):
    # Traemos las órdenes optimizando consulta para traer usuario y direcciones
    ordenes = Orden.objects.select_related('usuario').prefetch_related('usuario__direcciones').all().order_by('-fecha_creacion')
    return render(request, 'core/panel_ordenes.html', {
        'ordenes': ordenes,
        'estados': ESTADOS_PEDIDO
    })

@login_required
@user_passes_test(is_staff_or_superuser, login_url='staff_login')
def cambiar_estado_orden(request, orden_id):
    if request.method == 'POST':
        orden = get_object_or_404(Orden, id=orden_id)
        nuevo_estado = request.POST.get('nuevo_estado')
        tracking = request.POST.get('tracking_id')
       
        # Guardamos estado anterior
        estado_anterior = orden.estado
       
        if nuevo_estado:
            orden.estado = nuevo_estado
            if tracking:
                orden.codigo_seguimiento = tracking
            orden.save()
           
            # --- LÓGICA DE NOTIFICACIÓN POR CORREO ---
            if nuevo_estado != estado_anterior and orden.email:
                asunto = f"Actualización de tu Orden #{orden.numero_orden}"
                mensaje = ""
               
                # Detectar tipo de envío (Flash vs Courier)
                es_courier = int(orden.costo_envio) == 5990
               
                if nuevo_estado == 'CONFIRMADO':
                    mensaje = f"Hola {orden.usuario.first_name}, tu pago está confirmado. Estamos preparando tu pedido."
               
                elif nuevo_estado == 'DESPACHO':
                    if es_courier:
                        track_msg = f"Tu código de seguimiento es: {orden.codigo_seguimiento}" if orden.codigo_seguimiento else "Pronto recibirás tu código."
                        mensaje = f"¡Tu pedido va en camino! Lo hemos entregado al Courier. {track_msg}"
                    else:
                        # Mensaje Flash
                        mensaje = f"¡Tu pedido va en camino! Nuestro repartidor Flash ha salido a ruta hacia {orden.direccion_envio}."
               
                elif nuevo_estado == 'ENTREGADO':
                    mensaje = f"¡Pedido Entregado! Gracias por comprar en ModaOne. Esperamos que lo disfrutes."

                # Enviar correo
                if mensaje:
                    try:
                        email = EmailMessage(asunto, mensaje, settings.EMAIL_HOST_USER, [orden.email])
                        email.send()
                    except:
                        pass 
           
            messages.success(request, f'Orden #{orden.numero_orden} actualizada a {orden.get_estado_display()}.')
           
    return redirect('admin_ordenes')

@login_required
@user_passes_test(is_staff_or_superuser, login_url='staff_login')
def dashboard_bi(request):
    """Vista principal del Dashboard de BI"""
    return render(request, 'core/dashboard_bi.html', {'titulo': 'Inteligencia de Negocios'})

@user_passes_test(is_staff_or_superuser, login_url='staff_login')
def generar_reporte_gestion(request):
    """Genera PDF de Gestión BI"""
    fecha_fin = timezone.now()
    fecha_inicio = fecha_fin - timedelta(days=30)

    ordenes = Orden.objects.filter(fecha_creacion__range=(fecha_inicio, fecha_fin)).exclude(estado='CANCELADO')
    total_ventas = ordenes.aggregate(Sum('total_final'))['total_final__sum'] or 0
    total_pedidos = ordenes.count()
    ticket_promedio = total_ventas / total_pedidos if total_pedidos > 0 else 0

    top_productos = ItemOrden.objects.filter(orden__fecha_creacion__range=(fecha_inicio, fecha_fin)) \
        .values('nombre_producto') \
        .annotate(total_vendido=Sum('cantidad')) \
        .order_by('-total_vendido')[:5]

    top_tryon = RegistroTryOn.objects.filter(fecha__range=(fecha_inicio, fecha_fin)) \
        .values('producto__nombre') \
        .annotate(veces_probado=Count('id')) \
        .order_by('-veces_probado')[:5]

    contexto = {
        'fecha_inicio': fecha_inicio, 'fecha_fin': fecha_fin,
        'total_ventas': total_ventas, 'total_pedidos': total_pedidos,
        'ticket_promedio': ticket_promedio, 'top_productos': top_productos,
        'top_tryon': top_tryon, 'generado_por': request.user.username
    }
   
    html = render_to_string('core/reporte_bi_pdf.html', contexto)
    pdf = BytesIO()
    pisa.CreatePDF(html, dest=pdf)
    response = HttpResponse(pdf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="Informe_Gestion.pdf"'
    return response

@login_required
@user_passes_test(is_staff_or_superuser, login_url='staff_login')
def panel_clientes(request):
    """
    CRM de Clientes: Segmentación por comportamiento de compra y uso de IA.
    """
    # 1. Obtener métricas base de la base de datos
    clientes = User.objects.filter(is_staff=False).annotate(
        total_gastado=Sum('orden__total_final', filter=Q(orden__estado__in=['CONFIRMADO', 'DESPACHO', 'ENTREGADO'])),
        total_ordenes=Count('orden', filter=Q(orden__estado__in=['CONFIRMADO', 'DESPACHO', 'ENTREGADO'])),
        veces_ia=Count('registrotryon')
    ).order_by('-total_gastado')

    lista_clientes = []
    today = timezone.now().date()

    for c in clientes:
        # 2. Calcular días de inactividad
        ultima_orden = Orden.objects.filter(usuario=c).order_by('-fecha_creacion').first()
        dias_sin_compra = (today - ultima_orden.fecha_creacion.date()).days if ultima_orden else None
       
        # 3. Definir Perfil (Scoring)
        perfil = "Nuevo"
        color = "secondary"
       
        gasto = c.total_gastado or 0
        ordenes = c.total_ordenes or 0
        uso_ia = c.veces_ia or 0
       
        # Lógica de Segmentación
        if gasto > 50000 or ordenes >= 3:
            perfil = "💎 VIP"
            color = "info"
        elif uso_ia > 3 and ordenes < 1:
            perfil = "👀 Curioso (IA)"
            color = "warning"
        elif ordenes > 0 and dias_sin_compra and dias_sin_compra > 60:
            perfil = "👻 Inactivo"
            color = "danger"
        elif ordenes > 0:
            perfil = "✅ Cliente"
            color = "success"

        # 4. CÁLCULO SEGURO DE LA BARRA DE PROGRESO (0 a 100)
        # Cada uso de IA suma 10%. Máximo 100%.
        porcentaje_calc = uso_ia * 10
        if porcentaje_calc > 100:
            porcentaje_calc = 100
       
        # Guardamos todo en un diccionario limpio
        lista_clientes.append({
            'usuario': c,
            'gasto': gasto,
            'ordenes': ordenes,
            'uso_ia': uso_ia,
            'porcentaje_ia': porcentaje_calc, 
            'dias_inactivo': dias_sin_compra,
            'perfil': perfil,
            'color': color,
            'telefono': c.direcciones.last().telefono if c.direcciones.exists() else None
        })

    return render(request, 'core/panel_clientes.html', {'clientes': lista_clientes})


# ==========================================
# --- 6. IA TRY-ON (Replicate) ---
# ==========================================

@login_required
def try_on_view(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if not producto.imagen_url:
        messages.warning(request, 'Producto sin imagen.')
        return redirect('home')
    return render(request, 'core/try_on.html', {'producto': producto})

@csrf_exempt
def registrar_evento_tryon(request):
    return JsonResponse({'status': 'ok'}) 

@csrf_exempt
def procesar_ia_tryon(request):
    """
    Procesa la IA (Replicate) de forma segura y REGISTRA EL EVENTO PARA BI.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
           
            # Datos para la IA
            imagen_usuario = data.get('imagen_usuario')
            imagen_prenda = data.get('imagen_prenda')
            categoria = data.get('categoria', 'upper_body')
           
            # 1. SEGURIDAD: Obtener Token
            api_token = os.environ.get('REPLICATE_API_TOKEN')
           
            if not api_token:
                return JsonResponse({'status': 'error', 'message': 'Falta configurar el Token en el servidor'}, status=500)

            # Inicializamos el cliente
            client = replicate.Client(api_token=api_token)

            # 2. EJECUTAR IA (Modelo IDM-VTON)
            output = client.run(
                "cuuupid/idm-vton:c871bb9b046607b680449ecbae55fd8c6d945e0a1948644bf2361b3d021d3ff4",
                input={
                    "human_img": imagen_usuario,
                    "garm_img": imagen_prenda,
                    "garment_des": "clothing",
                    "category": categoria,
                    "crop": False,
                    "seed": 42,
                    "steps": 30
                }
            )
           
            final_image_url = str(output[0] if isinstance(output, list) else output)

            # 3. GUARDAR EL REGISTRO BI
            try:
                prod_id = data.get('producto_id')
                if prod_id:
                    producto_obj = Producto.objects.get(id=prod_id)
                    usuario_log = request.user if request.user.is_authenticated else None
                   
                    RegistroTryOn.objects.create(
                        producto=producto_obj,
                        usuario=usuario_log
                    )
                    print(f"✅ BI Registrado: Se probó {producto_obj.nombre}")
            except Exception as e:
                print(f"⚠️ Error guardando BI: {e}")

            return JsonResponse({'status': 'success', 'imagen_generada': final_image_url})

        except Exception as e:
            print(f"❌ Error CRÍTICO en IA: {str(e)}")
            return JsonResponse({'status': 'error', 'message': f'Error interno: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)