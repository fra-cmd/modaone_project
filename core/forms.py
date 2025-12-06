# core/forms.py

from django import forms
from django.contrib.auth.models import User
from .models import Direccion

# Este formulario solo maneja el nombre de usuario, email y contraseña
class ClienteRegistrationForm(forms.ModelForm):
    password = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Repetir contraseña', widget=forms.PasswordInput)

    # Campos adicionales del cliente (ampliación futura de RF-001)
    # Aquí se añadirían campos como RUT, dirección y teléfono

    class Meta:
        # Usaremos el modelo de usuario por defecto de Django por ahora
        model = User 
        fields = ('username', 'email', 'first_name', 'last_name')
        # Podemos usar labels personalizados
        labels = {
            'username': 'Nombre de Usuario',
            'email': 'Correo Electrónico',
            'first_name': 'Nombre',
            'last_name': 'Apellido',
        }

    def clean_password2(self):
        """Verifica que ambas contraseñas coincidan."""
        cd = self.cleaned_data
        if cd['password'] != cd['password2']:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return cd['password2']

    def clean_email(self):
        """Verifica que el email no esté ya registrado."""
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Ya existe un usuario con este correo.')
        return email

class DireccionForm(forms.ModelForm):
    class Meta:
        model = Direccion
        fields = ('rut', 'calle', 'numero', 'depto', 'comuna', 'telefono', 'predeterminada')
        
        # AQUÍ ESTÁ LA MAGIA DEL DISEÑO:
        widgets = {
            'rut': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: 12.345.678-9'
            }),
            'calle': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Calle / Avenida'
            }),
            'numero': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Numeración'
            }),
            'depto': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Depto / Casa (Opcional)'
            }),
            'comuna': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Comuna'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': '+56 9 1234 5678'
            }),
            'predeterminada': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }