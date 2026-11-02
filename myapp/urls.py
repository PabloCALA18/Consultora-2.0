from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_publico, name='home'),
    path('equipo/<slug:slug>/', views.fundador_detalle, name='fundador_detalle'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('inicio/', views.inicio, name='inicio'),

    path('consultores/', views.consultores, name='consultores'),
    path('consultores/<int:pk>/', views.consultor_detalle, name='consultor_detalle'),
    path('consultores/<int:pk>/editar/', views.consultor_editar, name='consultor_editar'),
    path('consultores/eliminar/<int:pk>/', views.eliminar_consultor, name='eliminar_consultor'),

    path('empresas/', views.empresas, name='empresas'),
    path('empresas/<int:pk>/', views.empresa_detalle, name='empresa_detalle'),
    path('empresas/<int:pk>/editar/', views.empresa_editar, name='empresa_editar'),
    path('empresas/eliminar/<int:pk>/', views.eliminar_empresa, name='eliminar_empresa'),

    path('proyectos/', views.proyectos, name='proyectos'),
    path('proyectos/<int:pk>/', views.proyecto_detalle, name='proyecto_detalle'),
    path('proyectos/<int:pk>/editar/', views.proyecto_editar, name='proyecto_editar'),
    path('proyectos/eliminar/<int:pk>/', views.eliminar_proyecto, name='eliminar_proyecto'),

    path('debug-admins/', views.ver_admins, name='ver_admins'),  # SOLO DEBUG, borrar después

    path('caja/', views.caja, name='caja'),
    path('caja/nuevo/', views.caja_nuevo, name='caja_nuevo'),
    path('caja/<int:pk>/editar/', views.caja_editar, name='caja_editar'),
    path('caja/<int:pk>/eliminar/', views.caja_eliminar, name='caja_eliminar'),
]