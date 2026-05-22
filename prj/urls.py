"""
URL configuration for prj project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from app import views
from api import api

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
    path('', views.render_home, name='home'),
    path('about/', views.render_about, name='about'),
    path('movie/<str:movie_id>/', views.render_movie_detail, name='movie_detail'),
    path('actor/<int:actor_id>/', views.render_actor_detail, name='actor_detail'),
    path('director/<int:director_id>/', views.render_director_detail, name='director_detail'),
    path('playground/', views.render_api_playground, name='api_playground'),
]