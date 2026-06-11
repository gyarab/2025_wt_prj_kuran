from django.contrib import admin
from .models import Movie, Actor, Director, Genre, Writer, Episode

@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name', 'imdb_id')

@admin.register(Director)
class DirectorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name', 'imdb_id')

@admin.register(Writer)
class WriterAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name', 'imdb_id')

@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'kind', 'release_year', 'rating', 'num_votes',
                    'director_names', 'is_seen')
    list_filter = ('kind', 'is_seen', 'genres')
    search_fields = ('title', 'imdb_id')
    # Without autocomplete the change page would render <select>s containing
    # every actor/director/writer (1M+ <option>s). Autocomplete loads on demand.
    autocomplete_fields = ('directors', 'writers', 'actors', 'genres')

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('directors')

    @admin.display(description='Directors')
    def director_names(self, obj):
        return ', '.join(d.name for d in obj.directors.all()) or '—'


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('title', 'series', 'season_number', 'episode_number',
                    'rating', 'is_seen')
    list_filter = ('is_seen',)
    search_fields = ('title', 'imdb_id', 'series__title')
    # The parent series picker would otherwise list every series as an <option>.
    autocomplete_fields = ('series',)
    list_select_related = ('series',)
