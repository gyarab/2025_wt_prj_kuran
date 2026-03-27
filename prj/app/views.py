from django.shortcuts import render
from .models import Movie

def render_home(request):
    movies = Movie.objects.all()
    return render(request, 'home.html', {'movies': movies})

def render_about(request):
    return render(request, 'about.html')