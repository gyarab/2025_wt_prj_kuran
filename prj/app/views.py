import logging
import urllib.parse

import requests
from django.conf import settings
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .models import Actor, Director, Movie

logger = logging.getLogger(__name__)


def fetch_wikipedia_movie_poster(movie_title):
    search_name = urllib.parse.quote(f"{movie_title} film".replace(' ', '_'))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_name}"
    try:
        response = requests.get(url, headers={'User-Agent': 'MyDjangoMovieApp/1.0'}, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get('type') == 'standard':
                return data.get('thumbnail', {}).get('source')
    except Exception as e:
        logger.warning("Wikipedia poster fallback error for %s: %s", movie_title, e)
    return None


def fetch_wikipedia_data(person_name):
    search_name = urllib.parse.quote(person_name.replace(' ', '_'))
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_name}"
    try:
        response = requests.get(url, headers={'User-Agent': 'MyDjangoMovieApp/1.0'}, timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get('type') == 'standard':
                return data.get('extract'), data.get('thumbnail', {}).get('source')
    except Exception as e:
        logger.warning("Wikipedia API error for %s: %s", person_name, e)
    return None, None


def render_home(request):
    movie_list = Movie.objects.all()
    search_query = request.GET.get('q', '')
    if search_query:
        movie_list = movie_list.filter(title__icontains=search_query)
    movie_list = movie_list.order_by('-release_year', 'title')
    paginator = Paginator(movie_list, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'home.html', {'page_obj': page_obj, 'query': search_query})


def render_movie_detail(request, movie_id):
    movie = get_object_or_404(
        Movie.objects.prefetch_related('actors', 'genres'),
        imdb_id=movie_id,
    )

    poster_url = None
    plot_summary = None

    tmdb_url = f"https://api.themoviedb.org/3/find/{movie.imdb_id}?api_key={settings.TMDB_API_KEY}&external_source=imdb_id"
    try:
        response = requests.get(tmdb_url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            movie_results = data.get('movie_results', [])
            if movie_results:
                tmdb_movie = movie_results[0]
                if tmdb_movie.get('poster_path'):
                    poster_url = f"https://image.tmdb.org/t/p/w500{tmdb_movie['poster_path']}"
                if tmdb_movie.get('overview'):
                    plot_summary = tmdb_movie['overview']
    except Exception as e:
        logger.warning("TMDB error: %s", e)

    if not poster_url or not plot_summary:
        omdb_url = f"http://www.omdbapi.com/?i={movie.imdb_id}&apikey={settings.OMDB_API_KEY}"
        try:
            response = requests.get(omdb_url, timeout=3)
            data = response.json()
            if data.get('Response') == 'True':
                if not poster_url and data.get('Poster') != 'N/A':
                    poster_url = data['Poster']
                if not plot_summary and data.get('Plot') != 'N/A':
                    plot_summary = data['Plot']
        except Exception as e:
            logger.warning("OMDb error: %s", e)

    if not poster_url:
        poster_url = fetch_wikipedia_movie_poster(movie.title)

    return render(request, 'movie_detail.html', {
        'movie': movie,
        'poster_url': poster_url,
        'plot_summary': plot_summary,
    })


def render_about(request):
    return render(request, 'about.html')


def render_actor_detail(request, actor_id):
    actor = get_object_or_404(Actor, id=actor_id)
    movies = Movie.objects.filter(actors=actor).order_by('-release_year')
    bio, photo_url = fetch_wikipedia_data(actor.name)
    return render(request, 'person_detail.html', {
        'person': actor,
        'role': 'Actor',
        'movies': movies,
        'bio': bio,
        'photo_url': photo_url,
    })


def render_director_detail(request, director_id):
    director = get_object_or_404(Director, id=director_id)
    movies = Movie.objects.filter(director=director).order_by('-release_year')
    bio, photo_url = fetch_wikipedia_data(director.name)
    return render(request, 'person_detail.html', {
        'person': director,
        'role': 'Director',
        'movies': movies,
        'bio': bio,
        'photo_url': photo_url,
    })


def render_api_playground(request):
    return render(request, 'api_playground.html')
