import gzip
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from app.models import Actor, Director, Genre, Movie, Writer

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


def _nconsts(value):
    """Split an IMDb comma-separated nconst list, dropping \\N / empties."""
    if value == NULL:
        return []
    return [n for n in value.split(',') if n and n != NULL]


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
        parser.add_argument('--update-existing', action='store_true',
                            help='Re-process movies already in the DB to backfill new '
                                 'fields/relations (preserves is_seen). Default: only add new.')

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
        i_t, i_r, i_v = idx['tconst'], idx['averageRating'], idx['numVotes']
        result = {}
        for row in rows:
            if row[i_t] in tconsts:
                v = row[i_r]
                rating = float(v) if v != NULL else None
                result[row[i_t]] = (rating, _parse_int(row[i_v]))
        return result

    @staticmethod
    def _read_crew(path, tconsts):
        rows = _read_tsv(path)
        idx = next(rows)
        i_t, i_d, i_w = idx['tconst'], idx['directors'], idx['writers']
        directors, writers = {}, {}
        need_d, need_w = set(), set()
        for row in rows:
            if row[i_t] in tconsts:
                ds = _nconsts(row[i_d])
                ws = _nconsts(row[i_w])
                if ds:
                    directors[row[i_t]] = ds
                    need_d.update(ds)
                if ws:
                    writers[row[i_t]] = ws
                    need_w.update(ws)
        return directors, writers, need_d, need_w

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
        # By default skip movies already imported; --update-existing re-processes
        # them so new fields/relations get backfilled (is_seen is preserved).
        existing_ids = (set() if options['update_existing']
                        else set(Movie.objects.values_list('imdb_id', flat=True)))
        rows = _read_tsv(paths['title.basics'])
        idx = next(rows)
        i_t = idx['tconst']
        i_type = idx['titleType']
        i_title = idx['primaryTitle']
        i_orig = idx['originalTitle']
        i_year = idx['startYear']
        i_runtime = idx['runtimeMinutes']
        i_genres = idx['genres']
        movies_data = {}
        for row in rows:
            tconst = row[i_t]
            if row[i_type] != 'movie' or tconst in existing_ids:
                continue
            orig = row[i_orig]
            movies_data[tconst] = {
                'title': row[i_title][:255],
                'original_title': orig[:255] if orig != NULL else None,
                'release_year': _parse_int(row[i_year]),
                'duration': _parse_int(row[i_runtime]),
                'genres': row[i_genres].split(',') if row[i_genres] != NULL else [],
                'rating': None,
                'num_votes': None,
                'director_nconsts': [],
                'writer_nconsts': [],
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
            crew_dirs, crew_writers, needed_directors, needed_writers = fut_crew.result()
            actor_map, needed_actors = fut_principals.result()

        for tconst, (rating, votes) in ratings.items():
            movies_data[tconst]['rating'] = rating
            movies_data[tconst]['num_votes'] = votes
        for tconst, ds in crew_dirs.items():
            movies_data[tconst]['director_nconsts'] = ds
        for tconst, ws in crew_writers.items():
            movies_data[tconst]['writer_nconsts'] = ws
        for tconst, nconsts in actor_map.items():
            movies_data[tconst]['actor_nconsts'] = nconsts

        self.stdout.write(f'  {len(ratings):,} ratings, {len(needed_directors):,} directors, '
                          f'{len(needed_writers):,} writers, {len(needed_actors):,} actors.')

        # 5. Names — resolve only the people we actually reference.
        self.stdout.write('5/5 Reading name.basics ...')
        all_needed = needed_directors | needed_writers | needed_actors
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

            # People (directors / writers / actors share the IMDb nconst id).
            for model, needed in ((Director, needed_directors),
                                  (Writer, needed_writers),
                                  (Actor, needed_actors)):
                model.objects.bulk_create(
                    [model(imdb_id=nc, name=person_data[nc])
                     for nc in needed if nc in person_data],
                    ignore_conflicts=True,
                    batch_size=2000,
                )
            director_objs = _id_map(Director, 'imdb_id', needed_directors)
            writer_objs = _id_map(Writer, 'imdb_id', needed_writers)
            actor_objs = _id_map(Actor, 'imdb_id', needed_actors)

            # Movies (M2M relations are written separately below).
            Movie.objects.bulk_create(
                [Movie(
                    imdb_id=tconst,
                    title=data['title'],
                    original_title=data['original_title'],
                    release_year=data['release_year'],
                    rating=data['rating'],
                    num_votes=data['num_votes'],
                    duration=data['duration'],
                ) for tconst, data in movies_data.items()],
                update_conflicts=True,
                update_fields=['title', 'original_title', 'release_year',
                               'rating', 'num_votes', 'duration'],
                unique_fields=['imdb_id'],
                batch_size=1000,
            )
            movie_objs = _id_map(Movie, 'imdb_id', tconsts)

            # M2M links
            self._link_m2m(Movie.genres.through, 'genre_id', movie_objs, genre_objs,
                           movies_data, 'genres')
            self._link_m2m(Movie.directors.through, 'director_id', movie_objs, director_objs,
                           movies_data, 'director_nconsts')
            self._link_m2m(Movie.writers.through, 'writer_id', movie_objs, writer_objs,
                           movies_data, 'writer_nconsts')
            self._link_m2m(Movie.actors.through, 'actor_id', movie_objs, actor_objs,
                           movies_data, 'actor_nconsts')

        elapsed = time.perf_counter() - started
        self.stdout.write(self.style.SUCCESS(
            f'Done. {len(movies_data):,} movies imported in {elapsed:.1f}s.'
        ))

    @staticmethod
    def _link_m2m(through, col, movie_objs, related_objs, movies_data, key):
        """Bulk-create rows of a Movie M2M through table from collected keys."""
        through.objects.bulk_create(
            [through(movie_id=movie_objs[tc], **{col: related_objs[k]})
             for tc, data in movies_data.items()
             for k in data[key]
             if tc in movie_objs and k in related_objs],
            ignore_conflicts=True,
            batch_size=2000,
        )
