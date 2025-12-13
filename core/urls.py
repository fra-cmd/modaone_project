# core/urls.py

from django.urls import path, include
from . import views 
from django.contrib.auth import views as auth_views # Importamos las vistas de auth de Django
from django.contrib.auth.decorators import user_passes_test # Para restringir por rol


urlpatterns = [
    # --- 1. RUTAS PÚBLICAS Y AUTENTICACIÓN ---
    path('', views.catalogo_digital, name='home'),
    path('registro/', views.registro_cliente, name='registro'),
    
    # Login Clientes
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
    # Login Staff (Backoffice)
# Usamos nuestra nueva vista personalizada
    path('backoffice/login/', views.staff_login_view, name='staff_login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),

    # --- 2. CARRITO Y COMPRA ---
    path('carrito/', views.ver_carrito, name='ver_carrito'),
    
    # Agregar ítems (Ruta moderna desde el catálogo)
    path('carrito/agregar-item/<int:producto_id>/', views.agregar_desde_catalogo, name='agregar_desde_catalogo'),
    # Agregar ítems (Ruta legacy, mantener por si acaso)
    path('carrito/add/<int:variante_id>/', views.agregar_al_carrito, name='agregar_al_carrito'),
    
    path('carrito/eliminar/<int:item_id>/', views.eliminar_item, name='eliminar_item'),
    path('carrito/actualizar/<int:item_id>/', views.actualizar_cantidad, name='actualizar_cantidad'),
    
    path('checkout/', views.checkout, name='checkout'),
    path('generar-orden/', views.generar_orden, name='generar_orden'),

    # --- 3. PASARELA Y POST-VENTA ---
    path('checkout/pasarela/<int:orden_id>/', views.pasarela_pago, name='pasarela_pago'),
    path('checkout/procesar/<int:orden_id>/', views.procesar_pago_real, name='procesar_pago_real'),
    path('orden/pago-simulado/<int:orden_id>/', views.pago_simulado, name='pago_simulado'),
    path('orden/descargar/<int:orden_id>/', views.descargar_boleta, name='descargar_boleta'),
    path('mis-pedidos/', views.mis_pedidos, name='mis_pedidos'),

    # --- 4. PANEL DE ADMINISTRACIÓN (BACKOFFICE) ---
    # La seguridad @user_passes_test ya está en views.py, no es necesario repetirla aquí
    path('admin-panel/', views.panel_admin_productos, name='panel_admin'),
    path('admin-panel/ordenes/', views.admin_ordenes, name='admin_ordenes'),
    path('admin-panel/ordenes/cambiar-estado/<int:orden_id>/', views.cambiar_estado_orden, name='cambiar_estado_orden'),

    # --- 5. MÓDULO TRY-ON (IA) ---
    path('try-on/<int:producto_id>/', views.try_on_view, name='try_on'),
    path('api/procesar-tryon/', views.procesar_ia_tryon, name='procesar_ia_tryon'),

    # --- 6. API REST (CRUD Y DASHBOARD) ---
    # Delega todo lo que sea 'api/v1/' al archivo core/api/urls.py
    path('api/v1/', include('core.api.urls')),
    path('admin-panel/reporte-bi/', views.generar_reporte_gestion, name='reporte_bi'),
    path('admin-panel/reportes-bi/', views.dashboard_bi, name='dashboard_bi'),
    path('api/registrar-tryon/', views.registrar_evento_tryon, name='registrar_tryon'),

    path('admin-panel/clientes/', views.panel_clientes, name='panel_clientes'),
    path('admin-panel/estrategia/', views.dashboard_expansion, name='dashboard_expansion'),
]