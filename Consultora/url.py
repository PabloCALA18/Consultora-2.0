from django.urls import path
    
from Consultora.myapp import views


urlpatterns = [
    path('index/', views.index, name='index'),
 ]
