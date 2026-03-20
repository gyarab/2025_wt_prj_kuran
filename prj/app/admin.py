from django.contrib import admin
from .models import Movie, Director, Actor, Genre

@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ('name', 'imdb_id')
    search_fields = ('name', 'imdb_id')

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'release_year', 'rating', 'duration', 'is_seen', 'imdb_id')
    list_filter = ('is_seen', 'release_year', 'rating')
    search_fields = ('title', 'imdb_id')


@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
    list_display = ('name', 'birth_year')
    search_fields = ('name',)

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)