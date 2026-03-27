from django.contrib import admin
from .models import Movie, Actor, Director, Genre

@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name') 

@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'imdb_id', 'release_year', 'is_seen')
    list_filter = ('is_seen', 'genres')
    search_fields = ('title', 'imdb_id')