from django.db import models

class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Actor(models.Model):
    name = models.CharField(max_length=255)
    birth_year = models.PositiveSmallIntegerField(blank=True, null=True)

    def __str__(self):
        return self.name

class Director(models.Model):
    name = models.CharField(max_length=255)
    birth_year = models.PositiveSmallIntegerField(blank=True, null=True)
    imdb_id = models.CharField(max_length=20, blank=True, null=True, unique=True)

    def __str__(self):
        return self.name

class Movie(models.Model):
    title = models.CharField(max_length=255)
    release_year = models.PositiveSmallIntegerField(blank=True, null=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, blank=True, null=True)
    duration = models.PositiveIntegerField(help_text="Duration in minutes", blank=True, null=True)
    is_seen = models.BooleanField(default=False)
    imdb_id = models.CharField(max_length=20, blank=True, null=True, unique=True)
    
    director = models.ForeignKey(Director, on_delete=models.SET_NULL, blank=True, null=True, related_name='movies')
    actors = models.ManyToManyField(Actor, blank=True, related_name='movies')
    genres = models.ManyToManyField(Genre, blank=True, related_name='movies')

    def __str__(self):
        return f"{self.title} ({self.release_year})"