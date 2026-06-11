import gc
import gzip
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from app.models import Actor, Director, Episode, Genre, Movie, Writer

IMDB_BASE_URL = 'https://datasets.imdbws.com'
IMDB_FILES = [
    'title.basics.tsv.gz',
    'title.ratings.tsv.gz',
    'title.crew.tsv.gz',
    'title.principals.tsv.gz',
    'title.episode.tsv.gz',
    'name.basics.tsv.gz',
]
NULL = r'\N'

# IMDb titleTypes imported as the top-level Movie table, mapped to Movie.kind.
TITLE_KINDS = {
    'movie': Movie.MOVIE,
    'tvSeries': Movie.SERIES,
    'tvMiniSeries': Movie.SERIES,
}


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
        parser.add_argument('--no-episodes', action='store_true',
                            help='Import series as show-level records only, skipping the '
                                 'per-episode pass (title.episode). Default: import episodes.')

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

    @staticmethod
    def _read_episodes(path, series_tconsts):
        """Map each episode to its parent series + season/episode numbers.

        Returns {episode_tconst: (parent_tconst, season, episode)} for every
        episode whose parentTconst is one of the series we're importing.
        """
        rows = _read_tsv(path)
        idx = next(rows)
        i_t, i_p = idx['tconst'], idx['parentTconst']
        i_s, i_e = idx['seasonNumber'], idx['episodeNumber']
        result = {}
        for row in rows:
            if row[i_p] in series_tconsts:
                result[row[i_t]] = (row[i_p], _parse_int(row[i_s]), _parse_int(row[i_e]))
        return result

    @staticmethod
    def _read_episode_basics(path, ep_tconsts):
        """Second pass over title.basics: pull title/year/runtime for episodes.

        Episode metadata lives in title.basics (titleType=tvEpisode), but we
        only learn which episodes we need after reading title.episode, so this
        re-scans the file for just those tconsts.
        """
        rows = _read_tsv(path)
        idx = next(rows)
        i_t = idx['tconst']
        i_title = idx['primaryTitle']
        i_year = idx['startYear']
        i_runtime = idx['runtimeMinutes']
        result = {}
        for row in rows:
            if row[i_t] in ep_tconsts:
                title = row[i_title]
                result[row[i_t]] = (
                    title[:255] if title != NULL else '',
                    _parse_int(row[i_year]),
                    _parse_int(row[i_runtime]),
                )
                if len(result) == len(ep_tconsts):
                    break
        return result

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        limit = options['limit']
        data_dir = options['data_dir']
        started = time.perf_counter()

        if options['download']:
            self.stdout.write('--- Downloading IMDb data ---')
            self.download_files(data_dir)

        import_episodes = not options['no_episodes']
        path_names = ['title.basics', 'title.ratings', 'title.crew',
                      'title.principals', 'name.basics']
        if import_episodes:
            path_names.append('title.episode')
        paths = {name: self._resolve_path(data_dir, name) for name in path_names}

        cap = f'{limit:,}' if limit else 'ALL'
        self.stdout.write(self.style.SUCCESS(f'--- Single-pass import (limit: {cap}) ---'))

        # 1. Basics — the master set of movies + series to import.
        self.stdout.write('1/5 Reading title.basics ...')
        # By default skip titles already imported; --update-existing re-processes
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
        i_end = idx['endYear']
        i_runtime = idx['runtimeMinutes']
        i_genres = idx['genres']
        movies_data = {}
        for row in rows:
            tconst = row[i_t]
            kind = TITLE_KINDS.get(row[i_type])
            if kind is None or tconst in existing_ids:
                continue
            orig = row[i_orig]
            movies_data[tconst] = {
                'kind': kind,
                'title': row[i_title][:255],
                'original_title': orig[:255] if orig != NULL else None,
                'release_year': _parse_int(row[i_year]),
                'end_year': _parse_int(row[i_end]),
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

        series_tconsts = frozenset(tc for tc, d in movies_data.items()
                                   if d['kind'] == Movie.SERIES)
        n_movies = len(movies_data) - len(series_tconsts)
        self.stdout.write(f'  {n_movies:,} movies + {len(series_tconsts):,} series collected.')

        if not movies_data:
            self.stdout.write(self.style.SUCCESS('Nothing new to import.'))
            return

        tconsts = frozenset(movies_data)

        # 1b. Episodes — link episodes to the series we're importing, then pull
        # their metadata in a second pass over title.basics.
        episodes_data = {}
        if import_episodes and series_tconsts:
            self.stdout.write('1b. Reading title.episode + episode basics ...')
            ep_links = self._read_episodes(paths['title.episode'], series_tconsts)
            ep_basics = self._read_episode_basics(paths['title.basics'], set(ep_links))
            for ep_tc, (parent, season, episode) in ep_links.items():
                title, year, runtime = ep_basics.get(ep_tc, ('', None, None))
                episodes_data[ep_tc] = {
                    'parent': parent,
                    'season': season,
                    'episode': episode,
                    'title': title,
                    'release_year': year,
                    'duration': runtime,
                    'rating': None,
                    'num_votes': None,
                }
            # Both maps are ~one entry per episode (millions of rows at full
            # scale); drop them now so they don't stack with episodes_data.
            del ep_links, ep_basics
            gc.collect()
            self.stdout.write(f'  {len(episodes_data):,} episodes collected.')

        # 2-4. Ratings / crew / principals — one pass each, in parallel.
        # Ratings cover episodes too; crew/principals stay at movie/series level.
        self.stdout.write('2-4/5 Reading ratings, crew, principals ...')
        rating_tconsts = tconsts | frozenset(episodes_data)
        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_ratings = pool.submit(self._read_ratings, paths['title.ratings'], rating_tconsts)
            fut_crew = pool.submit(self._read_crew, paths['title.crew'], tconsts)
            fut_principals = pool.submit(self._read_principals, paths['title.principals'], tconsts)
            ratings = fut_ratings.result()
            crew_dirs, crew_writers, needed_directors, needed_writers = fut_crew.result()
            actor_map, needed_actors = fut_principals.result()

        for tconst, (rating, votes) in ratings.items():
            target = movies_data.get(tconst) or episodes_data.get(tconst)
            if target is not None:
                target['rating'] = rating
                target['num_votes'] = votes
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

            # Movies + series (M2M relations are written separately below).
            Movie.objects.bulk_create(
                [Movie(
                    imdb_id=tconst,
                    kind=data['kind'],
                    title=data['title'],
                    original_title=data['original_title'],
                    release_year=data['release_year'],
                    end_year=data['end_year'],
                    rating=data['rating'],
                    num_votes=data['num_votes'],
                    duration=data['duration'],
                ) for tconst, data in movies_data.items()],
                update_conflicts=True,
                update_fields=['kind', 'title', 'original_title', 'release_year',
                               'end_year', 'rating', 'num_votes', 'duration'],
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

        # Episodes — written after the movies/series transaction has committed
        # (so their parent pks are durable) and in bounded chunks. At full scale
        # this is ~9M rows; materialising them all at once would exhaust RAM, so
        # we drain episodes_data in place and never hold more than CHUNK objects.
        n_movies = len(movies_data) - len(series_tconsts)
        n_series = len(series_tconsts)
        n_episodes = 0
        if episodes_data:
            # Free the movie-only intermediates before the big episode pass.
            del (ratings, crew_dirs, crew_writers, actor_map, person_data,
                 genre_objs, director_objs, writer_objs, actor_objs)
            gc.collect()

            self.stdout.write(f'Writing {len(episodes_data):,} episodes ...')
            ep_fields = ['series_id', 'title', 'season_number', 'episode_number',
                         'release_year', 'duration', 'rating', 'num_votes']
            CHUNK = 50_000
            batch = []
            while episodes_data:
                ep_tc, d = episodes_data.popitem()
                parent_pk = movie_objs.get(d['parent'])
                if parent_pk is not None:
                    batch.append(Episode(
                        imdb_id=ep_tc,
                        series_id=parent_pk,
                        title=d['title'] or f'Episode {ep_tc}',
                        season_number=d['season'],
                        episode_number=d['episode'],
                        release_year=d['release_year'],
                        duration=d['duration'],
                        rating=d['rating'],
                        num_votes=d['num_votes'],
                    ))
                if len(batch) >= CHUNK:
                    n_episodes += self._write_episodes(batch, ep_fields)
                    batch.clear()
                    self.stdout.write(f'  {n_episodes:,} episodes written ...', ending='\r')
                    self.stdout.flush()
            if batch:
                n_episodes += self._write_episodes(batch, ep_fields)
            self.stdout.write(f'  {n_episodes:,} episodes written.    ')

        elapsed = time.perf_counter() - started
        self.stdout.write(self.style.SUCCESS(
            f'Done. {n_movies:,} movies + {n_series:,} series '
            f'+ {n_episodes:,} episodes imported in {elapsed:.1f}s.'
        ))

    @staticmethod
    def _write_episodes(batch, update_fields):
        with transaction.atomic():
            Episode.objects.bulk_create(
                batch,
                update_conflicts=True,
                update_fields=update_fields,
                unique_fields=['imdb_id'],
                batch_size=1000,
            )
        return len(batch)

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
