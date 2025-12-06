# core/api/serializers.py
from rest_framework import serializers
from core.models import Producto, Variante
from django.shortcuts import get_object_or_404

class VarianteSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    class Meta:
        model = Variante
        fields = ['id', 'talla', 'color', 'stock']

class ProductoSerializer(serializers.ModelSerializer):
    variantes = VarianteSerializer(many=True, required=False)

    class Meta:
        model = Producto
        # AGREGAMOS 'categoria' y 'marca' AQUÍ
        fields = ['id', 'nombre', 'precio', 'descripcion', 'imagen_url', 'activo', 'categoria', 'marca', 'variantes']
        read_only_fields = ['id']

    def create(self, validated_data):
        variantes_data = validated_data.pop('variantes', [])
        producto = Producto.objects.create(**validated_data)
        for v_data in variantes_data:
            Variante.objects.create(producto=producto, **v_data)
        return producto

    def update(self, instance, validated_data):
        # Actualizar campos simples (INCLUYENDO LOS NUEVOS)
        instance.nombre = validated_data.get('nombre', instance.nombre)
        instance.precio = validated_data.get('precio', instance.precio)
        instance.descripcion = validated_data.get('descripcion', instance.descripcion)
        instance.imagen_url = validated_data.get('imagen_url', instance.imagen_url)
        instance.activo = validated_data.get('activo', instance.activo)
        
        # Actualizar Categoría y Marca
        instance.categoria = validated_data.get('categoria', instance.categoria)
        instance.marca = validated_data.get('marca', instance.marca)
        
        instance.save()

        # Lógica de variantes (igual que antes)
        variantes_data = validated_data.pop('variantes', [])
        ids_conservar = []
        for v_data in variantes_data:
            v_id = v_data.get('id')
            if v_id:
                try:
                    v = Variante.objects.get(id=v_id, producto=instance)
                    v.talla = v_data.get('talla', v.talla)
                    v.color = v_data.get('color', v.color)
                    v.stock = v_data.get('stock', v.stock)
                    v.save()
                    ids_conservar.append(v.id)
                except: pass
            else:
                nv = Variante.objects.create(producto=instance, **v_data)
                ids_conservar.append(nv.id)
        
        if variantes_data is not None:
            instance.variantes.exclude(id__in=ids_conservar).delete()

        return instance