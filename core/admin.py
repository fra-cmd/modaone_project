# core/admin.py (Código limpio y único)

from django.contrib import admin
from .models import Producto, Variante

# 1. Definir cómo se ve el CRUD de las Variantes dentro del Producto
class VarianteInline(admin.TabularInline):
    model = Variante
    extra = 1 # Muestra 1 campo extra vacío por defecto
    # Permite ver el stock y el precio dentro del producto
    fields = ('talla', 'color', 'stock') 

# 2. Definir cómo se ve el CRUD principal del Producto
@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    # Muestra la gestión de Variantes (tallas/stock) dentro de este formulario
    inlines = [VarianteInline] 

    # Columnas visibles en el listado de productos
    list_display = ('nombre', 'precio', 'activo', 'fecha_creacion')

    # Filtros laterales para el administrador
    list_filter = ('activo',)

    # Campos de búsqueda rápida
    search_fields = ('nombre', 'descripcion')

# Opcional: Si quieres registrar Variante para un CRUD separado, descomentarías:
# @admin.register(Variante) 
# class VarianteAdmin(admin.ModelAdmin):
#     list_display = ('producto', 'talla', 'color', 'stock')