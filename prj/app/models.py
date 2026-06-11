import secrets
from django.contrib.auth.models import User
from django.db import models

class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name

class Actor(models.Model):
    name = models.CharField(max_length=255)
    imdb_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    def __str__(self):
        return self.name

class Director(models.Model):
    name = models.CharField(max_length=255)
    imdb_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    def __str__(self):
        return self.name

class Writer(models.Model):
    name = models.CharField(max_length=255)
    imdb_id = models.CharField(max_length=32, unique=True, null=True, blank=True)
    def __str__(self):
        return self.name

class Movie(models.Model):
    MOVIE = 'movie'
    SERIES = 'series'
    KIND_CHOICES = [(MOVIE, 'Movie'), (SERIES, 'Series')]

    title = models.CharField(max_length=255)
    original_title = models.CharField(max_length=255, null=True, blank=True)
    imdb_id = models.CharField(max_length=20, unique=True)
    # 'movie' covers IMDb titleType=movie; 'series' covers tvSeries/tvMiniSeries.
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=MOVIE,
                            db_index=True)
    release_year = models.IntegerField(null=True, blank=True)
    # Year a series finished airing (IMDb endYear). Null for movies / ongoing shows.
    end_year = models.IntegerField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    num_votes = models.IntegerField(null=True, blank=True)
    poster_url = models.URLField(max_length=500, null=True, blank=True)
    plot_summary = models.TextField(null=True, blank=True)

    is_seen = models.BooleanField(default=False)
    genres = models.ManyToManyField(Genre, related_name='movies')

    directors = models.ManyToManyField(Director, related_name='movies', blank=True)
    writers = models.ManyToManyField(Writer, related_name='movies', blank=True)
    actors = models.ManyToManyField(Actor, related_name='movies')

    def __str__(self):
        return self.title


class Episode(models.Model):
    """A single episode of a series (IMDb titleType=tvEpisode).

    ``series`` points at the parent Movie row whose ``kind`` is 'series'.
    """
    series = models.ForeignKey(Movie, on_delete=models.CASCADE,
                               related_name='episodes')
    imdb_id = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=255)
    season_number = models.IntegerField(null=True, blank=True)
    episode_number = models.IntegerField(null=True, blank=True)
    release_year = models.IntegerField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    num_votes = models.IntegerField(null=True, blank=True)
    poster_url = models.URLField(max_length=500, null=True, blank=True)
    plot_summary = models.TextField(null=True, blank=True)
    is_seen = models.BooleanField(default=False)

    class Meta:
        ordering = ['season_number', 'episode_number']
        indexes = [
            models.Index(fields=['series', 'season_number', 'episode_number']),
        ]

    def __str__(self):
        s, e = self.season_number, self.episode_number
        if s is not None and e is not None:
            return f'{self.series.title} S{s:02d}E{e:02d}'
        return self.title


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    rd_api_key = models.CharField(max_length=255, blank=True, default='')
    auth_token = models.CharField(max_length=64, unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.auth_token:
            self.auth_token = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.username