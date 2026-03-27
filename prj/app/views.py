from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from .models import Movie, Actor, Director
import requests
import urllib.parse

def render_home(request):
    movie_list = Movie.objects.all()
    
    search_query = request.GET.get('q', '')
    
    if search_query:
        movie_list = movie_list.filter(title__icontains=search_query)
        
    movie_list = movie_list.order_by('-release_year', 'title')
    
    paginator = Paginator(movie_list, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'home.html', {
        'page_obj': page_obj, 
        'query': search_query
    })

def render_movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, imdb_id=movie_id)
    
    api_key = 'efdcbbf3'
    url = f"http://www.omdbapi.com/?i={movie.imdb_id}&apikey={api_key}"
    poster_url = None
    
    try:
        response = requests.get(url, timeout=3)
        data = response.json()
        if data.get('Response') == 'True' and data.get('Poster') != 'N/A':
            poster_url = data['Poster']
    except Exception as e:
        print(f"Error fetching poster: {e}")

    return render(request, 'movie_detail.html', {'movie': movie, 'poster_url': poster_url})

def render_about(request):
    return render(request, 'about.html')

def render_actor_detail(request, actor_id):
    actor = get_object_or_404(Actor, id=actor_id)
    movies = Movie.objects.filter(actors=actor).order_by('-release_year')

    return render(request, 'person_detail.html', {'person': actor, 'role': 'Actor', 'movies': movies})

def render_director_detail(request, director_id):
    director = get_object_or_404(Director, id=director_id)
    movies = Movie.objects.filter(director=director).order_by('-release_year')
    
    return render(request, 'person_detail.html', {'person': director, 'role': 'Director', 'movies': movies})