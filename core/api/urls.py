# core/api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductoViewSet, DashboardKPIView # <--- Importante importar ambas

router = DefaultRouter()
router.register(r'productos', ProductoViewSet)

urlpatterns = [
    path('', include(router.urls)),
    # Esta es la ruta que busca tu HTML para llenar los gráficos
    path('dashboard-kpi/', DashboardKPIView.as_view(), name='dashboard_kpi'),
]