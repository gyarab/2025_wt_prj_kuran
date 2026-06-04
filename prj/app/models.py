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
    title = models.CharField(max_length=255)
    original_title = models.CharField(max_length=255, null=True, blank=True)
    imdb_id = models.CharField(max_length=20, unique=True)
    release_year = models.IntegerField(null=True, blank=True)
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