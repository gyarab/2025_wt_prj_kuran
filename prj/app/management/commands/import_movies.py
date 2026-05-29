import os
import csv
from django.core.management.base import BaseCommand
from django.db import transaction
from app.models import Genre, Actor, Director, Movie

class Command(BaseCommand):
    help = 'Imports a fraction of movies and related data from IMDb TSV files.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=500,
            help='Number of movies to import (default: 500)'
        )
        parser.add_argument(
            '--data-dir',
            type=str,
            default='./data',
            help='Path to the directory containing IMDb TSV files'
        )

    def parse_int(self, value):
        if value == r'\N' or not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def parse_decimal(self, value):
        if value == r'\N' or not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def handle(self, *args, **options):
        limit = options['limit']
        data_dir = options['data_dir']

        # File paths
        basics_path = os.path.join(data_dir, 'title.basics.tsv')
        ratings_path = os.path.join(data_dir, 'title.ratings.tsv')
        crew_path = os.path.join(data_dir, 'title.crew.tsv')
        principals_path = os.path.join(data_dir, 'title.principals.tsv')
        names_path = os.path.join(data_dir, 'name.basics.tsv')

        # Dictionaries to hold data in memory before writing to DB
        movies_data = {}  # tconst -> dict of movie info
        needed_directors = set() # nconsts
        needed_actors = set()    # nconsts

        self.stdout.write(self.style.SUCCESS(f'--- Starting Import (Limit: {limit} movies) ---'))

        # 1. READ MOVIES (title.basics.tsv)
        self.stdout.write('1/5: Reading title.basics.tsv...')

        # Get already imported movies
        existing_ids = set(Movie.objects.values_list('imdb_id', flat=True))

        with open(basics_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                tconst = row['tconst']
                # Skip if not a movie or already imported
                if row['titleType'] != 'movie' or tconst in existing_ids:
                    continue

                movies_data[tconst] = {
                    'title': row['primaryTitle'][:255],
                    'release_year': self.parse_int(row['startYear']),
                    'duration': self.parse_int(row['runtimeMinutes']),
                    'genres': row['genres'].split(',') if row['genres'] != r'\N' else [],
                    'rating': None,
                    'director_nconst': None,
                    'actor_nconsts': []
                }

                if len(movies_data) >= limit:
                    break

        movie_tconsts = set(movies_data.keys())

        # 2. READ RATINGS (title.ratings.tsv)
        self.stdout.write('2/5: Reading title.ratings.tsv...')
        with open(ratings_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row['tconst'] in movie_tconsts:
                    movies_data[row['tconst']]['rating'] = self.parse_decimal(row['averageRating'])

        # 3. READ DIRECTORS (title.crew.tsv)
        self.stdout.write('3/5: Reading title.crew.tsv...')
        with open(crew_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row['tconst'] in movie_tconsts:
                    directors = row['directors'].split(',')
                    if directors and directors[0] != r'\N':
                        first_director = directors[0]
                        movies_data[row['tconst']]['director_nconst'] = first_director
                        needed_directors.add(first_director)

        # 4. READ ACTORS (title.principals.tsv)
        self.stdout.write('4/5: Reading title.principals.tsv...')
        with open(principals_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row['tconst'] in movie_tconsts:
                    if row['category'] in ['actor', 'actress']:
                        nconst = row['nconst']
                        movies_data[row['tconst']]['actor_nconsts'].append(nconst)
                        needed_actors.add(nconst)

        # 5. READ NAMES (name.basics.tsv)
        self.stdout.write('5/5: Extracting Actor/Director names (this might take a minute)...')
        person_data = {}
        all_needed_people = needed_directors.union(needed_actors)
        
        with open(names_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                nconst = row['nconst']
                if nconst in all_needed_people:
                    person_data[nconst] = {'name': row['primaryName'][:255]}
                    # Small optimization: stop reading if we found everyone we need
                    if len(person_data) == len(all_needed_people):
                        break

        # --- DATABASE INSERTION ---
        self.stdout.write('Writing data to the database...')
        
        with transaction.atomic():
            # Create Genres
            all_genres = set()
            for md in movies_data.values():
                all_genres.update(md['genres'])
            
            genre_objs = {}
            for g_name in all_genres:
                genre, _ = Genre.objects.get_or_create(name=g_name)
                genre_objs[g_name] = genre

            # Create Directors
            director_objs = {}
            for nconst in needed_directors:
                if nconst in person_data:
                    person_name = person_data[nconst]['name']
                    dir_obj, _ = Director.objects.get_or_create(
                        imdb_id=nconst,
                        defaults={"name": person_name}
                    )
                    director_objs[nconst] = dir_obj

            # Create Actors
            actor_objs = {}
            for nconst in needed_actors:
                if nconst in person_data:
                    person_name = person_data[nconst]['name']
                    act_obj, _ = Actor.objects.get_or_create(
                        imdb_id=nconst,
                        defaults={"name": person_name}
                    )
                    actor_objs[nconst] = act_obj

            # Create Movies
            for tconst, data in movies_data.items():
                director = director_objs.get(data['director_nconst'])
                
                movie, created = Movie.objects.update_or_create(
                    imdb_id=tconst,
                    defaults={
                        'title': data['title'],
                        'release_year': data['release_year'],
                        'rating': data['rating'],
                        'duration': data['duration'],
                        'director': director,
                    }
                )

                # Assign M2M relationships
                if data['genres']:
                    movie.genres.set([genre_objs[g] for g in data['genres']])
                
                if data['actor_nconsts']:
                    movie_actors = [actor_objs[n] for n in data['actor_nconsts'] if n in actor_objs]
                    movie.actors.set(movie_actors)

        self.stdout.write(self.style.SUCCESS('Successfully imported movie data!'))