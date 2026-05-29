import csv
import gzip
import os
import shutil
import urllib.request

from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import Actor, Director, Genre, Movie

IMDB_BASE_URL = 'https://datasets.imdbws.com'
IMDB_FILES = [
    'title.basics.tsv.gz',
    'title.ratings.tsv.gz',
    'title.crew.tsv.gz',
    'title.principals.tsv.gz',
    'name.basics.tsv.gz',
]


class Command(BaseCommand):
    help = 'Import movies from IMDb TSV files. Use --download to fetch fresh data from IMDb.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=500,
                            help='Number of movies to import (default: 500)')
        parser.add_argument('--data-dir', type=str, default='./data',
                            help='Directory containing (or to download) IMDb TSV files')
        parser.add_argument('--download', action='store_true',
                            help='Download fresh IMDb data files before importing')

    def _report(self, n, label):
        self.stdout.write(f'  {n:,} {label}', ending='\r')
        self.stdout.flush()

    def download_files(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        for filename in IMDB_FILES:
            tsv_path = os.path.join(data_dir, filename[:-3])  # strip .gz
            if os.path.exists(tsv_path):
                self.stdout.write(f'  {filename[:-3]} already exists, skipping.')
                continue
            gz_path = os.path.join(data_dir, filename)
            url = f'{IMDB_BASE_URL}/{filename}'
            self.stdout.write(f'  Downloading {filename} ...')

            def _progress(block, block_size, total):
                if total > 0:
                    pct = min(block * block_size * 100 // total, 100)
                    self.stdout.write(f'    {pct}%', ending='\r')
                    self.stdout.flush()

            urllib.request.urlretrieve(url, gz_path, reporthook=_progress)
            self.stdout.write('')
            self.stdout.write(f'  Extracting {filename} ...')
            with gzip.open(gz_path, 'rb') as f_in, open(tsv_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
            os.remove(gz_path)
            self.stdout.write(f'  Done: {filename[:-3]}')
        self.stdout.write(self.style.SUCCESS('All files ready.'))

    def parse_int(self, value):
        if value in (r'\N', ''):
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def parse_decimal(self, value):
        if value in (r'\N', ''):
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def handle(self, *args, **options):
        limit = options['limit']
        data_dir = options['data_dir']

        if options['download']:
            self.stdout.write('--- Downloading IMDb data ---')
            self.download_files(data_dir)

        basics_path = os.path.join(data_dir, 'title.basics.tsv')
        ratings_path = os.path.join(data_dir, 'title.ratings.tsv')
        crew_path = os.path.join(data_dir, 'title.crew.tsv')
        principals_path = os.path.join(data_dir, 'title.principals.tsv')
        names_path = os.path.join(data_dir, 'name.basics.tsv')

        for path in (basics_path, ratings_path, crew_path, principals_path, names_path):
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f'{path} not found. Run with --download to fetch IMDb files, '
                    f'or set --data-dir to the folder containing your TSV files.'
                )

        self.stdout.write(self.style.SUCCESS(f'--- Starting import (limit: {limit:,}) ---'))

        movies_data = {}
        needed_directors = set()
        needed_actors = set()

        # 1. Basics
        self.stdout.write('1/5 Reading title.basics.tsv ...')
        existing_ids = set(Movie.objects.values_list('imdb_id', flat=True))
        with open(basics_path, encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                tconst = row['tconst']
                if row['titleType'] != 'movie' or tconst in existing_ids:
                    continue
                movies_data[tconst] = {
                    'title': row['primaryTitle'][:255],
                    'release_year': self.parse_int(row['startYear']),
                    'duration': self.parse_int(row['runtimeMinutes']),
                    'genres': row['genres'].split(',') if row['genres'] != r'\N' else [],
                    'rating': None,
                    'director_nconst': None,
                    'actor_nconsts': [],
                }
                if len(movies_data) >= limit:
                    break
        self.stdout.write(f'  {len(movies_data):,} new movies collected.')

        movie_tconsts = set(movies_data.keys())

        # 2. Ratings
        self.stdout.write('2/5 Reading title.ratings.tsv ...')
        matched = 0
        with open(ratings_path, encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row['tconst'] in movie_tconsts:
                    movies_data[row['tconst']]['rating'] = self.parse_decimal(row['averageRating'])
                    matched += 1
        self.stdout.write(f'  {matched:,} ratings matched.')

        # 3. Directors
        self.stdout.write('3/5 Reading title.crew.tsv ...')
        matched = 0
        with open(crew_path, encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row['tconst'] in movie_tconsts:
                    directors = row['directors'].split(',')
                    if directors and directors[0] != r'\N':
                        nconst = directors[0]
                        movies_data[row['tconst']]['director_nconst'] = nconst
                        needed_directors.add(nconst)
                        matched += 1
        self.stdout.write(f'  {matched:,} directors matched.')

        # 4. Actors
        self.stdout.write('4/5 Reading title.principals.tsv ...')
        matched = 0
        with open(principals_path, encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                if row['tconst'] in movie_tconsts and row['category'] in ('actor', 'actress'):
                    nconst = row['nconst']
                    movies_data[row['tconst']]['actor_nconsts'].append(nconst)
                    needed_actors.add(nconst)
                    matched += 1
        self.stdout.write(f'  {matched:,} actor roles matched.')

        # 5. Names
        self.stdout.write('5/5 Reading name.basics.tsv ...')
        person_data = {}
        all_needed = needed_directors | needed_actors
        with open(names_path, encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            for row in reader:
                nconst = row['nconst']
                if nconst in all_needed:
                    person_data[nconst] = {'name': row['primaryName'][:255]}
                    if len(person_data) == len(all_needed):
                        break
        self.stdout.write(f'  {len(person_data):,} people resolved.')

        # Write to DB
        self.stdout.write('Writing to database ...')
        with transaction.atomic():
            all_genres = {g for md in movies_data.values() for g in md['genres']}
            genre_objs = {
                name: Genre.objects.get_or_create(name=name)[0]
                for name in all_genres
            }

            director_objs = {}
            for nconst in needed_directors:
                if nconst in person_data:
                    obj, _ = Director.objects.get_or_create(
                        imdb_id=nconst,
                        defaults={'name': person_data[nconst]['name']},
                    )
                    director_objs[nconst] = obj

            actor_objs = {}
            for nconst in needed_actors:
                if nconst in person_data:
                    obj, _ = Actor.objects.get_or_create(
                        imdb_id=nconst,
                        defaults={'name': person_data[nconst]['name']},
                    )
                    actor_objs[nconst] = obj

            for i, (tconst, data) in enumerate(movies_data.items(), 1):
                movie, _ = Movie.objects.update_or_create(
                    imdb_id=tconst,
                    defaults={
                        'title': data['title'],
                        'release_year': data['release_year'],
                        'rating': data['rating'],
                        'duration': data['duration'],
                        'director': director_objs.get(data['director_nconst']),
                    },
                )
                if data['genres']:
                    movie.genres.set([genre_objs[g] for g in data['genres']])
                if data['actor_nconsts']:
                    movie.actors.set([actor_objs[n] for n in data['actor_nconsts'] if n in actor_objs])
                if i % 100 == 0:
                    self._report(i, f'/ {len(movies_data):,} movies written')
            self.stdout.write('')

        self.stdout.write(self.style.SUCCESS(
            f'Done. {len(movies_data):,} movies imported into the database.'
        ))
