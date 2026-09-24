from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_publico, name='home'),

    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('inicio/', views.inicio, name='inicio'),

    path('consultores/', views.consultores, name='consultores'),
    path('consultores/eliminar/<int:pk>/', views.eliminar_consultor, name='eliminar_consultor'),

    path('empresas/', views.empresas, name='empresas'),
    path('empresas/eliminar/<int:pk>/', views.eliminar_empresa, name='eliminar_empresa'),

    path('proyectos/', views.proyectos, name='proyectos'),
    path('proyectos/eliminar/<int:pk>/', views.eliminar_proyecto, name='eliminar_proyecto'),

    path('debug-admins/', views.ver_admins, name='ver_admins'),  # SOLO DEBUG, borrar después
]