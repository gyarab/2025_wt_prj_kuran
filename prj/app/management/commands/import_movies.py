import csv
import gzip
import os
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        parser.add_argument('--limit', type=int, default=5000,
                            help='Number of movies to import per run (default: 5000)')
        parser.add_argument('--data-dir', type=str, default='./data',
                            help='Directory containing (or to download) IMDb TSV files')
        parser.add_argument('--download', action='store_true',
                            help='Download fresh IMDb data files before importing')

    # ------------------------------------------------------------------
    # Download helpers
    # ------------------------------------------------------------------

    def download_files(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        for filename in IMDB_FILES:
            tsv_path = os.path.join(data_dir, filename[:-3])
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

    # ------------------------------------------------------------------
    # TSV readers (run in parallel for ratings / crew / principals)
    # ------------------------------------------------------------------

    @staticmethod
    def _read_ratings(path, tconsts):
        result = {}
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                if row['tconst'] in tconsts:
                    v = row['averageRating']
                    result[row['tconst']] = float(v) if v != r'\N' else None
        return result

    @staticmethod
    def _read_crew(path, tconsts):
        directors = {}   # tconst -> nconst
        needed = set()
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                if row['tconst'] in tconsts:
                    parts = row['directors'].split(',')
                    if parts and parts[0] != r'\N':
                        directors[row['tconst']] = parts[0]
                        needed.add(parts[0])
        return directors, needed

    @staticmethod
    def _read_principals(path, tconsts):
        actors = {}   # tconst -> [nconst]
        needed = set()
        with open(path, encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                if row['tconst'] in tconsts and row['category'] in ('actor', 'actress'):
                    actors.setdefault(row['tconst'], []).append(row['nconst'])
                    needed.add(row['nconst'])
        return actors, needed

    # ------------------------------------------------------------------

    def parse_int(self, value):
        if value in (r'\N', ''):
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def handle(self, *args, **options):
        limit = options['limit']
        data_dir = options['data_dir']

        if options['download']:
            self.stdout.write('--- Downloading IMDb data ---')
            self.download_files(data_dir)

        paths = {
            name: os.path.join(data_dir, name)
            for name in ('title.basics.tsv', 'title.ratings.tsv', 'title.crew.tsv',
                         'title.principals.tsv', 'name.basics.tsv')
        }
        for path in paths.values():
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f'{path} not found. Run with --download to fetch IMDb files, '
                    f'or set --data-dir to the folder containing your TSV files.'
                )

        self.stdout.write(self.style.SUCCESS(f'--- Starting import (limit: {limit:,}) ---'))

        # 1. Basics
        self.stdout.write('1/5 Reading title.basics.tsv ...')
        existing_ids = set(Movie.objects.values_list('imdb_id', flat=True))
        movies_data = {}
        with open(paths['title.basics.tsv'], encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
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

        if not movies_data:
            self.stdout.write(self.style.SUCCESS('Nothing new to import.'))
            return

        tconsts = frozenset(movies_data)

        # 2-4. Read ratings / crew / principals in parallel
        self.stdout.write('2-4/5 Reading ratings, crew, principals in parallel ...')
        needed_directors = set()
        needed_actors = set()

        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_ratings = pool.submit(self._read_ratings, paths['title.ratings.tsv'], tconsts)
            fut_crew = pool.submit(self._read_crew, paths['title.crew.tsv'], tconsts)
            fut_principals = pool.submit(self._read_principals, paths['title.principals.tsv'], tconsts)

            ratings = fut_ratings.result()
            crew, needed_directors = fut_crew.result()
            actor_map, needed_actors = fut_principals.result()

        for tconst, rating in ratings.items():
            movies_data[tconst]['rating'] = rating
        for tconst, nconst in crew.items():
            movies_data[tconst]['director_nconst'] = nconst
        for tconst, nconsts in actor_map.items():
            movies_data[tconst]['actor_nconsts'] = nconsts

        self.stdout.write(f'  {len(ratings):,} ratings, {len(needed_directors):,} directors, '
                          f'{len(needed_actors):,} actors.')

        # 5. Names
        self.stdout.write('5/5 Reading name.basics.tsv ...')
        person_data = {}
        all_needed = needed_directors | needed_actors
        with open(paths['name.basics.tsv'], encoding='utf-8') as f:
            for row in csv.DictReader(f, delimiter='\t'):
                if row['nconst'] in all_needed:
                    person_data[row['nconst']] = {'name': row['primaryName'][:255]}
                    if len(person_data) == len(all_needed):
                        break
        self.stdout.write(f'  {len(person_data):,} people resolved.')

        # ------------------------------------------------------------------
        # Bulk DB writes
        # ------------------------------------------------------------------
        self.stdout.write('Writing to database ...')
        with transaction.atomic():

            # Genres
            all_genre_names = {g for md in movies_data.values() for g in md['genres']}
            Genre.objects.bulk_create(
                [Genre(name=n) for n in all_genre_names],
                ignore_conflicts=True,
            )
            genre_objs = {g.name: g for g in Genre.objects.filter(name__in=all_genre_names)}

            # Directors
            Director.objects.bulk_create(
                [Director(imdb_id=nc, name=person_data[nc]['name'])
                 for nc in needed_directors if nc in person_data],
                ignore_conflicts=True,
            )
            director_objs = {d.imdb_id: d for d in Director.objects.filter(imdb_id__in=needed_directors)}

            # Actors
            Actor.objects.bulk_create(
                [Actor(imdb_id=nc, name=person_data[nc]['name'])
                 for nc in needed_actors if nc in person_data],
                ignore_conflicts=True,
            )
            actor_objs = {a.imdb_id: a for a in Actor.objects.filter(imdb_id__in=needed_actors)}

            # Movies
            Movie.objects.bulk_create(
                [Movie(
                    imdb_id=tconst,
                    title=data['title'],
                    release_year=data['release_year'],
                    rating=data['rating'],
                    duration=data['duration'],
                    director=director_objs.get(data['director_nconst']),
                ) for tconst, data in movies_data.items()],
                update_conflicts=True,
                update_fields=['title', 'release_year', 'rating', 'duration', 'director'],
                unique_fields=['imdb_id'],
                batch_size=1000,
            )
            movie_objs = {m.imdb_id: m for m in Movie.objects.filter(imdb_id__in=tconsts)}

            # M2M: genres
            MovieGenre = Movie.genres.through
            MovieGenre.objects.bulk_create(
                [MovieGenre(movie_id=movie_objs[tc].id, genre_id=genre_objs[g].id)
                 for tc, data in movies_data.items()
                 for g in data['genres']
                 if tc in movie_objs and g in genre_objs],
                ignore_conflicts=True,
                batch_size=2000,
            )

            # M2M: actors
            MovieActor = Movie.actors.through
            MovieActor.objects.bulk_create(
                [MovieActor(movie_id=movie_objs[tc].id, actor_id=actor_objs[n].id)
                 for tc, data in movies_data.items()
                 for n in data['actor_nconsts']
                 if tc in movie_objs and n in actor_objs],
                ignore_conflicts=True,
                batch_size=2000,
            )

        self.stdout.write(self.style.SUCCESS(
            f'Done. {len(movies_data):,} movies imported.'
        ))
