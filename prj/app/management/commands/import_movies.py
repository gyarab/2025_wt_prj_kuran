import gzip
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from app.models import Actor, Director, Genre, Movie

IMDB_BASE_URL = 'https://datasets.imdbws.com'
IMDB_FILES = [
    'title.basics.tsv.gz',
    'title.ratings.tsv.gz',
    'title.crew.tsv.gz',
    'title.principals.tsv.gz',
    'name.basics.tsv.gz',
]
NULL = r'\N'


def _open_text(path):
    """Open an IMDb dataset whether it's gzipped (.tsv.gz) or plain (.tsv)."""
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', newline='')
    return open(path, encoding='utf-8', newline='')


def _read_tsv(path):
    """Yield (column_index, row_list) for a TSV file, header parsed once.

    First yields the {column_name: index} map, then plain ``str.split('\\t')``
    lists. Much faster than csv.DictReader over hundreds of millions of rows.
    """
    with _open_text(path) as f:
        header = f.readline().rstrip('\n').split('\t')
        idx = {name: i for i, name in enumerate(header)}
        yield idx
        for line in f:
            yield line.rstrip('\n').split('\t')


def _parse_int(value):
    if value == NULL or value == '':
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _id_map(model, field, values):
    """Build a {field_value: pk} map, chunking the IN query.

    A single ``filter(field__in=<huge list>)`` blows past SQLite's
    ``SQLITE_MAX_VARIABLE_NUMBER`` limit ("too many SQL variables"), so we
    look the rows up in safe-sized batches and merge the results.
    """
    result = {}
    values = list(values)
    chunk = 900
    for i in range(0, len(values), chunk):
        batch = values[i:i + chunk]
        result.update(
            model.objects.filter(**{f'{field}__in': batch}).values_list(field, 'id')
        )
    return result


class Command(BaseCommand):
    help = ('Import movies from IMDb TSV(.gz) files in a single pass. '
            'Use --download to fetch fresh data from IMDb.')

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None,
                            help='Cap number of movies (for testing). Default: import all.')
        parser.add_argument('--data-dir', type=str, default='./data',
                            help='Directory containing (or to download) IMDb TSV(.gz) files')
        parser.add_argument('--download', action='store_true',
                            help='Download fresh IMDb data files before importing')

    # ------------------------------------------------------------------
    # Download (keeps files gzipped — we read .gz directly)
    # ------------------------------------------------------------------

    def download_files(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        for filename in IMDB_FILES:
            gz_path = os.path.join(data_dir, filename)
            if os.path.exists(gz_path):
                self.stdout.write(f'  {filename} already exists, skipping.')
                continue
            url = f'{IMDB_BASE_URL}/{filename}'
            self.stdout.write(f'  Downloading {filename} ...')

            def _progress(block, block_size, total):
                if total > 0:
                    pct = min(block * block_size * 100 // total, 100)
                    self.stdout.write(f'    {pct}%', ending='\r')
                    self.stdout.flush()

            urllib.request.urlretrieve(url, gz_path, reporthook=_progress)
            self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('All files ready.'))

    def _resolve_path(self, data_dir, basename):
        """Find <basename>.tsv.gz or <basename>.tsv in data_dir."""
        for candidate in (f'{basename}.tsv.gz', f'{basename}.tsv'):
            path = os.path.join(data_dir, candidate)
            if os.path.exists(path):
                return path
        raise FileNotFoundError(
            f'{basename}.tsv(.gz) not found in {data_dir}. '
            f'Run with --download to fetch IMDb files, or set --data-dir.'
        )

    # ------------------------------------------------------------------
    # Single-pass TSV readers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_ratings(path, tconsts):
        rows = _read_tsv(path)
        idx = next(rows)
        i_t, i_r = idx['tconst'], idx['averageRating']
        result = {}
        for row in rows:
            if row[i_t] in tconsts:
                v = row[i_r]
                result[row[i_t]] = float(v) if v != NULL else None
        return result

    @staticmethod
    def _read_crew(path, tconsts):
        rows = _read_tsv(path)
        idx = next(rows)
        i_t, i_d = idx['tconst'], idx['directors']
        directors, needed = {}, set()
        for row in rows:
            if row[i_t] in tconsts:
                first = row[i_d].split(',', 1)[0]
                if first and first != NULL:
                    directors[row[i_t]] = first
                    needed.add(first)
        return directors, needed

    @staticmethod
    def _read_principals(path, tconsts):
        rows = _read_tsv(path)
        idx = next(rows)
        i_t, i_n, i_c = idx['tconst'], idx['nconst'], idx['category']
        actors, needed = {}, set()
        for row in rows:
            if row[i_t] in tconsts and row[i_c] in ('actor', 'actress'):
                actors.setdefault(row[i_t], []).append(row[i_n])
                needed.add(row[i_n])
        return actors, needed

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        limit = options['limit']
        data_dir = options['data_dir']
        started = time.perf_counter()

        if options['download']:
            self.stdout.write('--- Downloading IMDb data ---')
            self.download_files(data_dir)

        paths = {
            name: self._resolve_path(data_dir, name)
            for name in ('title.basics', 'title.ratings', 'title.crew',
                         'title.principals', 'name.basics')
        }

        cap = f'{limit:,}' if limit else 'ALL'
        self.stdout.write(self.style.SUCCESS(f'--- Single-pass import (limit: {cap}) ---'))

        # 1. Basics — the master set of movies to import.
        self.stdout.write('1/5 Reading title.basics ...')
        existing_ids = set(Movie.objects.values_list('imdb_id', flat=True))
        rows = _read_tsv(paths['title.basics'])
        idx = next(rows)
        i_t = idx['tconst']
        i_type = idx['titleType']
        i_title = idx['primaryTitle']
        i_year = idx['startYear']
        i_runtime = idx['runtimeMinutes']
        i_genres = idx['genres']
        movies_data = {}
        for row in rows:
            tconst = row[i_t]
            if row[i_type] != 'movie' or tconst in existing_ids:
                continue
            movies_data[tconst] = {
                'title': row[i_title][:255],
                'release_year': _parse_int(row[i_year]),
                'duration': _parse_int(row[i_runtime]),
                'genres': row[i_genres].split(',') if row[i_genres] != NULL else [],
                'rating': None,
                'director_nconst': None,
                'actor_nconsts': [],
            }
            if limit and len(movies_data) >= limit:
                break
        self.stdout.write(f'  {len(movies_data):,} new movies collected.')

        if not movies_data:
            self.stdout.write(self.style.SUCCESS('Nothing new to import.'))
            return

        tconsts = frozenset(movies_data)

        # 2-4. Ratings / crew / principals — one pass each, in parallel.
        self.stdout.write('2-4/5 Reading ratings, crew, principals ...')
        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_ratings = pool.submit(self._read_ratings, paths['title.ratings'], tconsts)
            fut_crew = pool.submit(self._read_crew, paths['title.crew'], tconsts)
            fut_principals = pool.submit(self._read_principals, paths['title.principals'], tconsts)
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

        # 5. Names — resolve only the people we actually reference.
        self.stdout.write('5/5 Reading name.basics ...')
        all_needed = needed_directors | needed_actors
        rows = _read_tsv(paths['name.basics'])
        idx = next(rows)
        i_n, i_name = idx['nconst'], idx['primaryName']
        person_data = {}
        for row in rows:
            if row[i_n] in all_needed:
                person_data[row[i_n]] = row[i_name][:255]
                if len(person_data) == len(all_needed):
                    break
        self.stdout.write(f'  {len(person_data):,} people resolved.')

        # ------------------------------------------------------------------
        # Bulk DB writes
        # ------------------------------------------------------------------
        self.stdout.write('Writing to database ...')
        is_sqlite = connection.vendor == 'sqlite'
        if is_sqlite:
            # Trade durability for speed during this one-off bulk load.
            with connection.cursor() as c:
                c.execute('PRAGMA synchronous = OFF')
                c.execute('PRAGMA journal_mode = MEMORY')

        with transaction.atomic():
            # Genres
            all_genre_names = {g for md in movies_data.values() for g in md['genres']}
            Genre.objects.bulk_create(
                [Genre(name=n) for n in all_genre_names],
                ignore_conflicts=True,
            )
            genre_objs = _id_map(Genre, 'name', all_genre_names)

            # Directors
            Director.objects.bulk_create(
                [Director(imdb_id=nc, name=person_data[nc])
                 for nc in needed_directors if nc in person_data],
                ignore_conflicts=True,
                batch_size=2000,
            )
            director_objs = _id_map(Director, 'imdb_id', needed_directors)

            # Actors
            Actor.objects.bulk_create(
                [Actor(imdb_id=nc, name=person_data[nc])
                 for nc in needed_actors if nc in person_data],
                ignore_conflicts=True,
                batch_size=2000,
            )
            actor_objs = _id_map(Actor, 'imdb_id', needed_actors)

            # Movies
            Movie.objects.bulk_create(
                [Movie(
                    imdb_id=tconst,
                    title=data['title'],
                    release_year=data['release_year'],
                    rating=data['rating'],
                    duration=data['duration'],
                    director_id=director_objs.get(data['director_nconst']),
                ) for tconst, data in movies_data.items()],
                update_conflicts=True,
                update_fields=['title', 'release_year', 'rating', 'duration', 'director'],
                unique_fields=['imdb_id'],
                batch_size=1000,
            )
            movie_objs = _id_map(Movie, 'imdb_id', tconsts)

            # M2M: genres
            MovieGenre = Movie.genres.through
            MovieGenre.objects.bulk_create(
                [MovieGenre(movie_id=movie_objs[tc], genre_id=genre_objs[g])
                 for tc, data in movies_data.items()
                 for g in data['genres']
                 if tc in movie_objs and g in genre_objs],
                ignore_conflicts=True,
                batch_size=2000,
            )

            # M2M: actors
            MovieActor = Movie.actors.through
            MovieActor.objects.bulk_create(
                [MovieActor(movie_id=movie_objs[tc], actor_id=actor_objs[n])
                 for tc, data in movies_data.items()
                 for n in data['actor_nconsts']
                 if tc in movie_objs and n in actor_objs],
                ignore_conflicts=True,
                batch_size=2000,
            )

        elapsed = time.perf_counter() - started
        self.stdout.write(self.style.SUCCESS(
            f'Done. {len(movies_data):,} movies imported in {elapsed:.1f}s.'
        ))
