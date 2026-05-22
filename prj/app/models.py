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

class Movie(models.Model):
    title = models.CharField(max_length=255)
    imdb_id = models.CharField(max_length=20, unique=True)
    release_year = models.IntegerField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)
    rating = models.FloatField(null=True, blank=True)
    poster_url = models.URLField(max_length=500, null=True, blank=True)
    plot_summary = models.TextField(null=True, blank=True)
    
    is_seen = models.BooleanField(default=False)
    genres = models.ManyToManyField(Genre, related_name='movies')
    
    director = models.ForeignKey(Director, on_delete=models.SET_NULL, null=True, blank=True)
    actors = models.ManyToManyField(Actor, related_name='movies')

    def __str__(self):
        return self.title