from django.db import models
from django.contrib.auth.models import User
import time # <--- USAMOS ESTO EN VEZ DE TIMEZONE PARA QUE NO FALLE NUNCA

CATEGORIAS = (
    ('hombre', 'Hombres'),
    ('mujer', 'Mujeres'),
    ('accesorios', 'Accesorios'),
    # Eliminamos Unisex
)

MARCAS = (
    ('guess', 'Guess'),
    ('northface', 'The North Face'),
    ('ck', 'Calvin Klein'),
    ('ea7', 'EA7 Armani'),
    ('coach', 'Coach'),
    ('mk', 'Michael Kors'),
    ('ae', 'American Eagle'),
    ('versace', 'Versace'),
    ('tommy', 'Tommy Hilfiger'),
)

# 1. Producto
class Producto(models.Model):
    nombre = models.CharField(max_length=255)
    
    # --- NUEVOS CAMPOS DE CLASIFICACIÓN ---
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='unisex')
    marca = models.CharField(max_length=20, choices=MARCAS, default='generico')
    # --------------------------------------
    
    precio = models.DecimalField(max_digits=10, decimal_places=0)
    descripcion = models.TextField()
    imagen_url = models.URLField(max_length=500, blank=True)
    activo = models.BooleanField(default=True) 
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.nombre} - {self.get_marca_display()}" # Muestra marca en el admin

    def obtener_variante_disponible(self):
        return self.variantes.filter(stock__gt=0).first()

# 2. Variante
class Variante(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='variantes') 
    talla = models.CharField(max_length=10)
    color = models.CharField(max_length=50)
    stock = models.IntegerField(default=0)

    class Meta:
        unique_together = ('producto', 'talla', 'color') 

    def __str__(self):
        return f"{self.producto.nombre} - {self.talla}"

# 3. Carrito
class Carrito(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

# 4. ItemCarrito
class ItemCarrito(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE, related_name='items')
    variante = models.ForeignKey(Variante, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1) 
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2) 

    class Meta:
        unique_together = ('carrito', 'variante') 

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

# 5. Direccion
class Direccion(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direcciones')
    rut = models.CharField(max_length=12, verbose_name="RUT del Receptor")
    calle = models.CharField(max_length=255)
    numero = models.CharField(max_length=10)
    depto = models.CharField(max_length=50, blank=True, null=True)
    comuna = models.CharField(max_length=100)
    telefono = models.CharField(max_length=15)
    predeterminada = models.BooleanField(default=False) 

# Lista de estados
ESTADOS_PEDIDO = (
    ('PENDIENTE', 'Pendiente de Pago'),
    ('CONFIRMADO', 'Confirmado / En Preparación'),
    ('PICKING', 'Picking de Productos'),
    ('EMBALAJE', 'En Embalaje'),
    ('DESPACHO', 'Despachado al Courier'),
    ('ENTREGADO', 'Entregado al Cliente'),
    ('CANCELADO', 'Cancelado'),
)

# 6. Orden (AQUÍ ESTABA EL ERROR)
class Orden(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    numero_orden = models.CharField(max_length=20, unique=True, editable=False)
    email = models.EmailField(max_length=254, verbose_name="Email de Contacto")
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=0)
    costo_envio = models.DecimalField(max_digits=10, decimal_places=0)
    total_final = models.DecimalField(max_digits=10, decimal_places=0)
    codigo_seguimiento = models.CharField(max_length=50, blank=True, null=True, verbose_name="Tracking ID")

    estado = models.CharField(max_length=20, choices=ESTADOS_PEDIDO, default='PENDIENTE')
    direccion_envio = models.TextField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Si no tiene número, lo creamos usando time.time() que es infalible
        if not self.numero_orden:
            self.numero_orden = 'MODA' + str(int(time.time()))
        super().save(*args, **kwargs)

# 7. ItemOrden
class ItemOrden(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name='items_orden')
    variante = models.ForeignKey(Variante, on_delete=models.SET_NULL, null=True) 
    nombre_producto = models.CharField(max_length=255)
    talla_color = models.CharField(max_length=50) 
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=0)


class RegistroTryOn(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='probador_logs')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Prueba de {self.producto.nombre} - {self.fecha}"