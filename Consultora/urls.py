# Este archivo va en Consultora/urls.py (la carpeta de configuración del proyecto,
# NO dentro de myapp). Reemplazá el contenido actual por esto.

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('myapp.urls')),
]