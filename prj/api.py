from ninja import NinjaAPI, Schema
from typing import List, Optional
from django.shortcuts import get_object_or_404
from app.models import Movie, Actor, Director, Genre

api = NinjaAPI(title="Debridflix API", version="1.0.0")

# --- Schemas ---

class GenreSchema(Schema):
    id: int
    name: str

class DirectorSchema(Schema):
    id: int
    name: str

class ActorSchema(Schema):
    id: int
    name: str

class MovieListSchema(Schema):
    id: int
    title: str
    imdb_id: str
    release_year: Optional[int] = None
    rating: Optional[float] = None
    duration: Optional[int] = None
    is_seen: bool

class MovieDetailSchema(Schema):
    id: int
    title: str
    imdb_id: str
    release_year: Optional[int] = None
    rating: Optional[float] = None
    duration: Optional[int] = None
    is_seen: bool
    plot_summary: Optional[str] = None
    poster_url: Optional[str] = None
    director: Optional[DirectorSchema] = None
    genres: List[GenreSchema] = []
    actors: List[ActorSchema] = []

class MovieCreateSchema(Schema):
    title: str
    imdb_id: str
    release_year: Optional[int] = None
    rating: Optional[float] = None
    duration: Optional[int] = None
    plot_summary: Optional[str] = None
    poster_url: Optional[str] = None

class MovieUpdateSchema(Schema):
    title: Optional[str] = None
    release_year: Optional[int] = None
    rating: Optional[float] = None
    duration: Optional[int] = None
    plot_summary: Optional[str] = None
    poster_url: Optional[str] = None
    is_seen: Optional[bool] = None

class ActorDetailSchema(Schema):
    id: int
    name: str
    movies: List[MovieListSchema] = []

class DirectorDetailSchema(Schema):
    id: int
    name: str
    movies: List[MovieListSchema] = []

# --- Movie endpoints ---

@api.get("/movie", response=List[MovieListSchema])
def list_movies(request, q: str = None):
    qs = Movie.objects.all().order_by('-release_year')
    if q:
        qs = qs.filter(title__icontains=q)
    return qs

@api.get("/movie/{movie_id}", response=MovieDetailSchema)
def get_movie(request, movie_id: int):
    return get_object_or_404(
        Movie.objects.prefetch_related('actors', 'genres').select_related('director'),
        id=movie_id
    )

@api.post("/movie", response=MovieDetailSchema)
def create_movie(request, payload: MovieCreateSchema):
    movie = Movie.objects.create(**payload.dict())
    return Movie.objects.prefetch_related('actors', 'genres').select_related('director').get(id=movie.id)

@api.put("/movie/{movie_id}", response=MovieDetailSchema)
def update_movie(request, movie_id: int, payload: MovieUpdateSchema):
    movie = get_object_or_404(Movie, id=movie_id)
    for attr, value in payload.dict(exclude_unset=True).items():
        setattr(movie, attr, value)
    movie.save()
    return Movie.objects.prefetch_related('actors', 'genres').select_related('director').get(id=movie.id)

@api.delete("/movie/{movie_id}")
def delete_movie(request, movie_id: int):
    movie = get_object_or_404(Movie, id=movie_id)
    movie.delete()
    return {"success": True}

# --- Genre endpoints (bonus) ---

@api.get("/genre", response=List[GenreSchema])
def list_genres(request):
    return Genre.objects.all().order_by('name')

@api.get("/genre/{genre_id}/movies", response=List[MovieListSchema])
def genre_movies(request, genre_id: int):
    genre = get_object_or_404(Genre, id=genre_id)
    return genre.movies.all().order_by('-release_year')

# --- Actor endpoints (bonus) ---

@api.get("/actor", response=List[ActorSchema])
def list_actors(request, q: str = None):
    qs = Actor.objects.all().order_by('name')
    if q:
        qs = qs.filter(name__icontains=q)
    return qs

@api.get("/actor/{actor_id}", response=ActorDetailSchema)
def get_actor(request, actor_id: int):
    actor = get_object_or_404(Actor.objects.prefetch_related('movies'), id=actor_id)
    return actor

# --- Director endpoints (bonus) ---

@api.get("/director", response=List[DirectorSchema])
def list_directors(request, q: str = None):
    qs = Director.objects.all().order_by('name')
    if q:
        qs = qs.filter(name__icontains=q)
    return qs

@api.get("/director/{director_id}", response=DirectorDetailSchema)
def get_director(request, director_id: int):
    director = get_object_or_404(Director.objects.prefetch_related('movies'), id=director_id)
    return director
