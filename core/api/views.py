# core/api/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser
from django.db.models import Sum, Count
from core.models import Orden, Producto, Variante, ItemOrden, RegistroTryOn 
from .serializers import ProductoSerializer

# 1. CRUD DE PRODUCTOS (API para la tabla de inventario)
class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all().order_by('-fecha_creacion')
    serializer_class = ProductoSerializer
    permission_classes = [IsAdminUser]

# 2. DASHBOARD DE KPIs (Inteligencia de Negocios Real)
class DashboardKPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        # A. Ventas Totales (Dinero real confirmado)
        # Sumamos órdenes que NO estén pendientes ni canceladas
        total_ventas = Orden.objects.exclude(
            estado__in=['PENDIENTE', 'CANCELADO']
        ).aggregate(total=Sum('total_final'))['total'] or 0
        
        # B. Total Pedidos
        total_ordenes = Orden.objects.count()
        
        # C. Stock Crítico (Productos con alguna variante bajo 5 unidades)
        productos_bajo_stock = Producto.objects.filter(variantes__stock__lte=5).distinct().count()

        # D. Top 5 Productos Vendidos (Para el Gráfico de Barras)
        top_productos = ItemOrden.objects.values('nombre_producto').annotate(
            total_vendido=Sum('cantidad')
        ).order_by('-total_vendido')[:5]

        # E. ANÁLISIS REAL DE TRY-ON vs VENTAS (Para la Tabla de Interés)
        # 1. Obtenemos los 5 productos más probados
        top_tryon_query = RegistroTryOn.objects.values('producto__nombre').annotate(
            veces_probado=Count('id')
        ).order_by('-veces_probado')[:5]

        lista_tryon_real = []
        
        for item in top_tryon_query:
            nombre_prod = item['producto__nombre']
            pruebas = item['veces_probado']
            
            # 2. Consultamos las VENTAS REALES de ese producto específico
            # Filtramos solo ventas concretadas (Confirmado, Despacho, Entregado, etc.)
            ventas_reales = ItemOrden.objects.filter(
                nombre_producto=nombre_prod,
                orden__estado__in=['CONFIRMADO', 'PICKING', 'EMBALAJE', 'DESPACHO', 'ENTREGADO']
            ).aggregate(total=Sum('cantidad'))['total'] or 0
            
            # 3. Calculamos Tasa de Conversión Real (%)
            # (Ventas / Pruebas) * 100
            tasa = (ventas_reales / pruebas * 100) if pruebas > 0 else 0
            
            # Agregamos el diccionario con los datos calculados a la lista
            lista_tryon_real.append({
                'producto__nombre': nombre_prod,
                'veces_probado': pruebas,
                'ventas_reales': ventas_reales, 
                'tasa_conversion': round(tasa, 1)
            })
        
        # Preparamos el JSON final para el Frontend
        data = {
            "total_ventas": total_ventas,
            "total_ordenes": total_ordenes,
            "bajo_stock": productos_bajo_stock,
            "top_productos": list(top_productos), 
            "top_tryon": lista_tryon_real # Enviamos la lista procesada con la conversión
        }
        return Response(data)
