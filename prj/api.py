import logging
import re
import urllib.parse
import requests
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db.models import Case, Count, F, IntegerField, Value, When
from ninja import NinjaAPI, Schema
from ninja.security import HttpBearer
from typing import List, Optional
from django.conf import settings
from django.shortcuts import get_object_or_404
from app.models import Movie, Actor, Director, Episode, Genre, Writer, UserProfile

logger = logging.getLogger(__name__)


class TokenAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            return UserProfile.objects.select_related('user').get(auth_token=token).user
        except UserProfile.DoesNotExist:
            return None

api = NinjaAPI(title="Debridflix API", version="1.0.0")

# --- Schemas ---

class GenreSchema(Schema):
    id: int
    name: str

class DirectorSchema(Schema):
    id: int
    name: str

class WriterSchema(Schema):
    id: int
    name: str

class ActorSchema(Schema):
    id: int
    name: str

class MovieListSchema(Schema):
    id: int
    title: str
    original_title: Optional[str] = None
    imdb_id: str
    kind: str
    release_year: Optional[int] = None
    end_year: Optional[int] = None
    rating: Optional[float] = None
    num_votes: Optional[int] = None
    duration: Optional[int] = None
    is_seen: bool
    poster_url: Optional[str] = None

class MovieDetailSchema(Schema):
    id: int
    title: str
    original_title: Optional[str] = None
    imdb_id: str
    kind: str
    release_year: Optional[int] = None
    end_year: Optional[int] = None
    rating: Optional[float] = None
    num_votes: Optional[int] = None
    duration: Optional[int] = None
    is_seen: bool
    plot_summary: Optional[str] = None
    poster_url: Optional[str] = None
    directors: List[DirectorSchema] = []
    writers: List[WriterSchema] = []
    genres: List[GenreSchema] = []
    actors: List[ActorSchema] = []

class EpisodeSchema(Schema):
    id: int
    imdb_id: str
    title: str
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    release_year: Optional[int] = None
    duration: Optional[int] = None
    rating: Optional[float] = None
    num_votes: Optional[int] = None
    is_seen: bool

class SeasonSchema(Schema):
    season: Optional[int] = None
    episode_count: int

class MovieCreateSchema(Schema):
    title: str
    original_title: Optional[str] = None
    imdb_id: str
    release_year: Optional[int] = None
    rating: Optional[float] = None
    num_votes: Optional[int] = None
    duration: Optional[int] = None
    plot_summary: Optional[str] = None
    poster_url: Optional[str] = None

class MovieUpdateSchema(Schema):
    title: Optional[str] = None
    original_title: Optional[str] = None
    release_year: Optional[int] = None
    rating: Optional[float] = None
    num_votes: Optional[int] = None
    duration: Optional[int] = None
    plot_summary: Optional[str] = None
    poster_url: Optional[str] = None
    is_seen: Optional[bool] = None

class PersonDetailSchema(Schema):
    id: int
    name: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    movies: List[MovieListSchema] = []

def _fetch_wikipedia_person(name: str):
    search_name = urllib.parse.quote(name.replace(' ', '_'))
    try:
        data = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{search_name}",
            headers={"User-Agent": "DebridflixApp/1.0"},
            timeout=5,
        ).json()
        if data.get('type') == 'standard':
            bio = data.get('extract')
            photo = data.get('thumbnail', {}).get('source')
            return bio, photo
    except Exception as e:
        logger.warning("Wikipedia person error for %s: %s", name, e)
    return None, None


def _person_movies(qs):
    """Sort movies: poster first, then by num_votes desc."""
    return qs.annotate(
        has_poster=Case(
            When(poster_url__isnull=False, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        )
    ).order_by('-has_poster', F('num_votes').desc(nulls_last=True))


# --- Movie endpoints ---

def _sort_fields(sort: str):
    V = F('num_votes').desc(nulls_last=True)
    R = F('rating').desc(nulls_last=True)
    Y = F('release_year').desc(nulls_last=True)
    D = F('duration').asc(nulls_last=True)
    return {
        'votes':        [V, R, Y],
        'rating':       [R, V, Y],
        'year_desc':    [Y, R, V],
        'year_asc':     [F('release_year').asc(nulls_last=True), R, V],
        'title_asc':    ['title'],
        'title_desc':   [F('title').desc()],
        'duration_asc': [D, R],
        'duration_desc':[F('duration').desc(nulls_last=True), R],
        'seen':         [F('is_seen').desc(), V, R],
    }.get(sort, [V, R, Y])

@api.get("/movie", response=List[MovieListSchema])
def list_movies(request, q: str = None, limit: int = 50, offset: int = 0,
                sort: str = 'votes', min_votes: int = 0, genre: str = None,
                kind: str = 'movie'):
    limit = max(1, min(limit, 200))
    qs = Movie.objects.all()
    # 'movie' / 'series' filter by kind; 'all' returns both.
    if kind in (Movie.MOVIE, Movie.SERIES):
        qs = qs.filter(kind=kind)
    if q:
        qs = qs.filter(title__icontains=q)
    if min_votes > 0:
        qs = qs.filter(num_votes__gte=min_votes)
    if genre:
        qs = qs.filter(genres__name__iexact=genre)
    qs = qs.order_by(*_sort_fields(sort))
    return qs[offset:offset + limit]

def _title_matches(query: str, result_title: str) -> bool:
    """Require titles to be close enough in length and content to be the same film."""
    def normalise(s):
        return ''.join(c.lower() for c in s if c.isalnum() or c.isspace()).strip()
    a, b = normalise(query), normalise(result_title)
    if not a or not b:
        return False
    # Reject if one title is much longer than the other (e.g. "10 rounds" vs "10 Rounds Sample Workout")
    if min(len(a), len(b)) / max(len(a), len(b)) < 0.8:
        return False
    return a == b or a in b or b in a


def _fetch_poster_and_plot(movie: Movie):
    poster_url = None
    plot_summary = None

    # TMDB uses different endpoints/fields for TV: tv_results vs movie_results,
    # search/tv vs search/movie, and 'name'/'first_air_date_year' vs 'title'/'year'.
    is_series = movie.kind == Movie.SERIES
    find_key = 'tv_results' if is_series else 'movie_results'
    search_path = 'search/tv' if is_series else 'search/movie'
    title_field = 'name' if is_series else 'title'
    year_param = 'first_air_date_year' if is_series else 'year'

    # 1. TMDB — find by IMDb ID (most reliable: exact ID match)
    try:
        data = requests.get(
            f"https://api.themoviedb.org/3/find/{movie.imdb_id}",
            params={"api_key": settings.TMDB_API_KEY, "external_source": "imdb_id"},
            timeout=5,
        ).json()
        result = (data.get(find_key) or [None])[0]
        if result:
            if result.get('poster_path'):
                poster_url = f"https://image.tmdb.org/t/p/w500{result['poster_path']}"
            if result.get('overview'):
                plot_summary = result['overview']
    except Exception as e:
        logger.warning("TMDB find error for %s: %s", movie.imdb_id, e)

    # 2. TMDB — search by title+year, but only accept results whose title matches
    if not poster_url:
        try:
            params = {"api_key": settings.TMDB_API_KEY, "query": movie.title}
            if movie.release_year:
                params[year_param] = movie.release_year
            data = requests.get(
                f"https://api.themoviedb.org/3/{search_path}",
                params=params,
                timeout=5,
            ).json()
            for result in (data.get('results') or []):
                if not _title_matches(movie.title, result.get(title_field, '')):
                    continue
                if result.get('poster_path'):
                    poster_url = f"https://image.tmdb.org/t/p/w500{result['poster_path']}"
                if not plot_summary and result.get('overview'):
                    plot_summary = result['overview']
                break
        except Exception as e:
            logger.warning("TMDB search error for %s: %s", movie.title, e)

    # 3. OMDb — poster from IMDb CDN + votes/rating from IMDb
    num_votes = None
    omdb_rating = None
    try:
        data = requests.get(
            "http://www.omdbapi.com/",
            params={"i": movie.imdb_id, "apikey": settings.OMDB_API_KEY},
            timeout=5,
        ).json()
        if data.get('Response') == 'True':
            if not poster_url and data.get('Poster') not in (None, 'N/A'):
                poster_url = data['Poster']
            if not plot_summary and data.get('Plot') not in (None, 'N/A'):
                plot_summary = data['Plot']
            try:
                raw_votes = data.get('imdbVotes', '').replace(',', '')
                if raw_votes.isdigit():
                    num_votes = int(raw_votes)
            except Exception:
                pass
            try:
                raw_rating = data.get('imdbRating', '')
                if raw_rating and raw_rating != 'N/A':
                    omdb_rating = float(raw_rating)
            except Exception:
                pass
    except Exception as e:
        logger.warning("OMDb error for %s: %s", movie.imdb_id, e)

    update_fields = []
    if poster_url:
        movie.poster_url = poster_url
        update_fields.append('poster_url')
    if plot_summary:
        movie.plot_summary = plot_summary
        update_fields.append('plot_summary')
    if num_votes is not None:
        movie.num_votes = num_votes
        update_fields.append('num_votes')
    if omdb_rating is not None:
        movie.rating = omdb_rating
        update_fields.append('rating')
    if update_fields:
        movie.save(update_fields=update_fields)

    return poster_url, plot_summary


@api.get("/movie/{movie_id}", response=MovieDetailSchema)
def get_movie(request, movie_id: int):
    movie = get_object_or_404(
        Movie.objects.prefetch_related('actors', 'genres', 'directors', 'writers'),
        id=movie_id
    )
    if not movie.poster_url or not movie.plot_summary or movie.num_votes is None:
        _fetch_poster_and_plot(movie)
    return movie

@api.get("/movie/{series_id}/seasons", response=List[SeasonSchema])
def list_seasons(request, series_id: int):
    """Distinct seasons of a series with per-season episode counts."""
    series = get_object_or_404(Movie, id=series_id)
    rows = (series.episodes
            .values('season_number')
            .annotate(episode_count=Count('id'))
            .order_by('season_number'))
    return [{'season': r['season_number'], 'episode_count': r['episode_count']}
            for r in rows]

@api.get("/movie/{series_id}/episodes", response=List[EpisodeSchema])
def list_episodes(request, series_id: int, season: int = None,
                  unseasoned: bool = False):
    """Episodes of a series, ordered by season then episode number.

    ``season=N`` filters to one season; ``unseasoned=true`` returns episodes
    with no season number (specials etc.).
    """
    series = get_object_or_404(Movie, id=series_id)
    qs = series.episodes.all()
    if unseasoned:
        qs = qs.filter(season_number__isnull=True)
    elif season is not None:
        qs = qs.filter(season_number=season)
    return qs

@api.post("/movie", response=MovieDetailSchema)
def create_movie(request, payload: MovieCreateSchema):
    movie = Movie.objects.create(**payload.dict())
    return Movie.objects.prefetch_related('actors', 'genres', 'directors', 'writers').get(id=movie.id)

@api.put("/movie/{movie_id}", response=MovieDetailSchema)
def update_movie(request, movie_id: int, payload: MovieUpdateSchema):
    movie = get_object_or_404(Movie, id=movie_id)
    for attr, value in payload.dict(exclude_unset=True).items():
        setattr(movie, attr, value)
    movie.save()
    return Movie.objects.prefetch_related('actors', 'genres', 'directors', 'writers').get(id=movie.id)

@api.delete("/movie/{movie_id}")
def delete_movie(request, movie_id: int):
    movie = get_object_or_404(Movie, id=movie_id)
    movie.delete()
    return {"success": True}

# --- Genre endpoints (bonus) ---

@api.get("/genre", response=List[GenreSchema])
def list_genres(request):
    return Genre.objects.all().order_by('name')

@api.get("/genre/{genre_id}/movies", response=List[MovieListSchema])
def genre_movies(request, genre_id: int):
    genre = get_object_or_404(Genre, id=genre_id)
    return genre.movies.all().order_by('-release_year')

# --- Actor endpoints (bonus) ---

@api.get("/actor", response=List[ActorSchema])
def list_actors(request, q: str = None):
    qs = Actor.objects.all().order_by('name')
    if q:
        qs = qs.filter(name__icontains=q)
    return qs

@api.get("/actor/{actor_id}", response=PersonDetailSchema)
def get_actor(request, actor_id: int):
    actor = get_object_or_404(Actor, id=actor_id)
    bio, photo_url = _fetch_wikipedia_person(actor.name)
    return {
        'id': actor.id,
        'name': actor.name,
        'bio': bio,
        'photo_url': photo_url,
        'movies': list(_person_movies(actor.movies.all())),
    }

# --- Director endpoints (bonus) ---

@api.get("/director", response=List[DirectorSchema])
def list_directors(request, q: str = None):
    qs = Director.objects.all().order_by('name')
    if q:
        qs = qs.filter(name__icontains=q)
    return qs

@api.get("/director/{director_id}", response=PersonDetailSchema)
def get_director(request, director_id: int):
    director = get_object_or_404(Director, id=director_id)
    bio, photo_url = _fetch_wikipedia_person(director.name)
    return {
        'id': director.id,
        'name': director.name,
        'bio': bio,
        'photo_url': photo_url,
        'movies': list(_person_movies(director.movies.all())),
    }

# --- Writer endpoints ---

@api.get("/writer/{writer_id}", response=PersonDetailSchema)
def get_writer(request, writer_id: int):
    writer = get_object_or_404(Writer, id=writer_id)
    bio, photo_url = _fetch_wikipedia_person(writer.name)
    return {
        'id': writer.id,
        'name': writer.name,
        'bio': bio,
        'photo_url': photo_url,
        'movies': list(_person_movies(writer.movies.all())),
    }


# --- Real-Debrid streaming ---

RD_BASE = 'https://api.real-debrid.com/rest/1.0'

LANG_PATTERNS = {
    'cs': ['[CZ]', '.CZ.', '-CZ.', '-CZ-', 'CZ.', 'CZECH', 'CESKY', 'ČESKY',
           '[CS]', '.CS.', 'CZENG', 'CZ+SK', 'CZ/SK', 'CZ DABING', 'CZ DUB'],
    'sk': ['[SK]', '.SK.', '-SK.', '-SK-', 'SK.', 'SLOVAK', 'SLOVENSKY',
           'SLOVENČINA', 'CZ+SK', 'SK+CZ', 'CZ/SK', 'SK DABING', 'SK DUB'],
    'en': ['[EN]', '.EN.', 'ENGLISH', '.ENG.', '[ENG]'],
}


def _detect_languages(title: str) -> list[str]:
    t = title.upper()
    found = [lang for lang, markers in LANG_PATTERNS.items() if any(m in t for m in markers)]
    return found if found else ['en']


def _detect_quality(name: str, title: str) -> str:
    t = (name + ' ' + title).upper()
    if '2160' in t or '4K' in t or 'UHD' in t:
        return '4K'
    if '1080' in t:
        return '1080p'
    if '720' in t:
        return '720p'
    if '480' in t:
        return '480p'
    return 'SD'


# Friendly, actionable text for the Real-Debrid error codes users actually hit.
RD_ERROR_HINTS = {
    'infringing_file':    'This torrent is blocked by Real-Debrid (DMCA). Pick a different stream.',
    'bad_token':          'Your Real-Debrid API key is invalid — update it in your profile.',
    'permission_denied':  'Real-Debrid denied this request — check your account and API key.',
    'hoster_unavailable': 'Real-Debrid can’t serve this torrent right now — try another stream.',
    'too_many_requests':  'Real-Debrid is rate-limiting you — wait a moment and try again.',
    'account_locked':     'Your Real-Debrid account is locked — resolve it on real-debrid.com.',
}


def _rd(method: str, path: str, key: str, **kwargs):
    r = requests.request(
        method, f'{RD_BASE}{path}',
        headers={'Authorization': f'Bearer {key}'},
        timeout=15, **kwargs
    )
    if not r.ok:
        # Surface Real-Debrid's own error instead of a bare HTTP status, so the
        # caller can show something actionable rather than "Unexpected error".
        err = ''
        try:
            err = r.json().get('error') or ''
        except Exception:
            pass
        hint = RD_ERROR_HINTS.get(err)
        if hint:
            raise ValueError(hint)
        detail = err or (r.text or '').strip()[:200] or f'HTTP {r.status_code}'
        raise ValueError(f'Real-Debrid {path} failed ({r.status_code}): {detail}')
    # Some endpoints (e.g. selectFiles) return 204 No Content.
    if not r.content:
        return {}
    return r.json()


_BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://torrentio.strem.fun/',
}


def _torrentio_streams(stream_type: str, stream_id: str) -> list:
    """Fetch raw Torrentio streams.

    ``stream_type`` is 'movie' (id = imdb id) or 'series' (id =
    '<seriesImdbId>:<season>:<episode>').
    """
    resp = requests.get(
        f'https://torrentio.strem.fun/stream/{stream_type}/{stream_id}.json',
        headers=_BROWSER_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get('streams', [])


def _rd_process(rd_key: str, info_hash: str, file_ids: list) -> dict:
    """Add magnet, select files, wait for download, unrestrict → return {url, filename}."""
    import time

    magnet     = f'magnet:?xt=urn:btih:{info_hash}'
    added      = _rd('POST', '/torrents/addMagnet', rd_key, data={'magnet': magnet})
    torrent_id = added['id']

    try:
        files_param = ','.join(file_ids) if file_ids else 'all'
        _rd('POST', f'/torrents/selectFiles/{torrent_id}', rd_key, data={'files': files_param})
    except Exception:
        _rd('POST', f'/torrents/selectFiles/{torrent_id}', rd_key, data={'files': 'all'})

    for _ in range(20):
        info = _rd('GET', f'/torrents/info/{torrent_id}', rd_key)
        if info.get('status') == 'downloaded' and info.get('links'):
            break
        time.sleep(1)
    else:
        raise ValueError('RD processing timed out — try again.')

    best_url = best_name = ''
    best_size = 0
    for raw_link in info.get('links', []):
        try:
            u = _rd('POST', '/unrestrict/link', rd_key, data={'link': raw_link})
            if u.get('filesize', 0) > best_size:
                best_size = u['filesize']
                best_url  = u['download']
                best_name = u.get('filename', '')
        except Exception:
            continue

    if not best_url:
        raise ValueError('Could not unrestrict any link.')
    return {'url': best_url, 'filename': best_name}


def _stream_results(streams: list, rd_key: str) -> list:
    """Annotate raw Torrentio streams with quality/language and RD cache info."""
    if not streams:
        return []

    hashes = list({s['infoHash'].lower() for s in streams if s.get('infoHash')})[:20]
    try:
        avail = _rd('GET', f'/torrents/instantAvailability/{"/".join(hashes)}', rd_key)
    except Exception:
        avail = {}

    result, seen = [], set()
    for s in streams:
        h = s.get('infoHash', '').lower()
        if not h or h in seen:
            continue
        seen.add(h)

        name  = s.get('name', '')
        title = (s.get('title') or name).split('\n')[0]

        cached_data = avail.get(h, {})
        variants    = cached_data.get('rd', []) if isinstance(cached_data, dict) else []
        cached      = bool(variants)
        file_ids    = []
        if cached and variants:
            file_ids = [k for k, v in variants[0].items()
                        if isinstance(v, dict) and v.get('filesize', 0) > 50_000_000] \
                       or list(variants[0].keys())

        result.append({
            'info_hash': h,
            'quality':   _detect_quality(name, title),
            'languages': _detect_languages(title),
            'title':     title[:120],
            'cached':    cached,
            'file_ids':  file_ids,
        })

    return result


# GET /api/movie/{id}/streams  — list available streams with quality/language/cache info
@api.get('/movie/{movie_id}/streams', auth=TokenAuth())
def list_streams(request, movie_id: int):
    movie   = get_object_or_404(Movie, id=movie_id)
    profile = get_object_or_404(UserProfile, user=request.auth)
    if not profile.rd_api_key:
        return api.create_response(request, {'detail': 'No Real-Debrid key configured.'}, status=400)

    try:
        streams = _torrentio_streams('movie', movie.imdb_id)
    except Exception as e:
        return api.create_response(request, {'detail': f'Torrentio error: {e}'}, status=502)

    return _stream_results(streams, profile.rd_api_key)


# GET /api/episode/{id}/streams  — Torrentio series streams for one episode
@api.get('/episode/{episode_id}/streams', auth=TokenAuth())
def list_episode_streams(request, episode_id: int):
    episode = get_object_or_404(Episode.objects.select_related('series'), id=episode_id)
    profile = get_object_or_404(UserProfile, user=request.auth)
    if not profile.rd_api_key:
        return api.create_response(request, {'detail': 'No Real-Debrid key configured.'}, status=400)
    if episode.season_number is None or episode.episode_number is None:
        return api.create_response(
            request, {'detail': 'Episode has no season/episode number to stream.'}, status=400)

    stream_id = f'{episode.series.imdb_id}:{episode.season_number}:{episode.episode_number}'
    try:
        streams = _torrentio_streams('series', stream_id)
    except Exception as e:
        return api.create_response(request, {'detail': f'Torrentio error: {e}'}, status=502)

    return _stream_results(streams, profile.rd_api_key)


# POST /api/movie/{id}/stream  — process a specific stream through RD
class StreamRequestSchema(Schema):
    info_hash: str
    file_ids:  List[str] = []


def _process_stream(request, rd_key: str, payload: StreamRequestSchema, label: str):
    """Run a selected stream through Real-Debrid, returning {url, filename}."""
    if not rd_key:
        return api.create_response(request, {'detail': 'No Real-Debrid key configured.'}, status=400)
    try:
        return _rd_process(rd_key, payload.info_hash, payload.file_ids)
    except ValueError as e:
        # Includes RD API errors and our own timeout/no-link messages.
        return api.create_response(request, {'detail': str(e)}, status=502)
    except requests.RequestException as e:
        logger.warning('RD network error for %s: %s', label, e)
        return api.create_response(request, {'detail': f'Real-Debrid network error: {e}'}, status=502)
    except Exception as e:
        logger.exception('RD stream error for %s', label)
        return api.create_response(request, {'detail': f'Unexpected error: {e}'}, status=500)


@api.post('/movie/{movie_id}/stream', auth=TokenAuth())
def stream_movie(request, movie_id: int, payload: StreamRequestSchema):
    movie   = get_object_or_404(Movie, id=movie_id)
    profile = get_object_or_404(UserProfile, user=request.auth)
    return _process_stream(request, profile.rd_api_key, payload, movie.imdb_id)


@api.post('/episode/{episode_id}/stream', auth=TokenAuth())
def stream_episode(request, episode_id: int, payload: StreamRequestSchema):
    episode = get_object_or_404(Episode, id=episode_id)
    profile = get_object_or_404(UserProfile, user=request.auth)
    return _process_stream(request, profile.rd_api_key, payload, episode.imdb_id)


# GET /api/movie|episode/{id}/subtitles?language=cs  — search OpenSubtitles (no key needed)
OSUB_LANG = {'cs': 'cze', 'sk': 'slo', 'en': 'eng'}

def _opensubtitles_search(request, imdb_id: str, language: str):
    lang3 = OSUB_LANG.get(language, 'eng')
    imdb_num = imdb_id.replace('tt', '')
    try:
        resp = requests.get(
            f'https://rest.opensubtitles.org/search/imdbid-{imdb_num}/sublanguageid-{lang3}',
            headers={'User-Agent': 'DebridflixApp v1.0'},
            timeout=8,
        )
        data = resp.json()
    except Exception as e:
        return api.create_response(request, {'detail': f'OpenSubtitles error: {e}'}, status=502)

    # Prefer SRT: it carries absolute timestamps, so it always stays in sync.
    # Frame-based formats (MicroDVD .sub) are still converted by the proxy, but
    # listing SRT first makes the auto-selected default the reliable one.
    items = list(data or [])
    items.sort(key=lambda it: 0 if str(it.get('SubFormat', 'srt')).lower() == 'srt' else 1)

    results = []
    for item in items[:10]:
        results.append({
            'id':       item.get('IDSubtitleFile'),
            'name':     item.get('SubFileName', ''),
            'rating':   item.get('SubRating', '0'),
            'downloads':item.get('SubDownloadsCnt', '0'),
            'url':      item.get('SubDownloadLink', ''),
            'format':   item.get('SubFormat', 'srt'),
        })
    return results


@api.get('/movie/{movie_id}/subtitles', auth=None)
def list_subtitles(request, movie_id: int, language: str = 'en'):
    movie = get_object_or_404(Movie, id=movie_id)
    return _opensubtitles_search(request, movie.imdb_id, language)


@api.get('/episode/{episode_id}/subtitles', auth=None)
def list_episode_subtitles(request, episode_id: int, language: str = 'en'):
    episode = get_object_or_404(Episode, id=episode_id)
    return _opensubtitles_search(request, episode.imdb_id, language)


def _decode_subtitle(raw: bytes) -> str:
    """Decode subtitle bytes to text.

    Czech/Slovak subtitles on OpenSubtitles are almost always Windows-1250
    (or ISO-8859-2), not UTF-8, so a plain utf-8 decode mangles diacritics
    (ě š č ř ž ý …). Prefer real UTF-8 when valid, then sniff the encoding,
    then fall back to the common single-byte CZ/SK code pages.
    """
    # Valid UTF-8 (with optional BOM) — covers English and modern files exactly.
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        pass
    # Detect the encoding (charset-normalizer ships as a requests dependency).
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best:
            return str(best)
    except Exception:
        pass
    # Deterministic fallback for the languages this app targets.
    for enc in ('cp1250', 'iso-8859-2'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _vtt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f'{h:02d}:{m:02d}:{s:02d}.{ms:03d}'


def _microdvd_to_vtt(text: str, default_fps: float = 23.976) -> str:
    """{start_frame}{end_frame}text|text  →  WebVTT cues (frame-based)."""
    line_re = re.compile(r'^\s*\{(\d+)\}\{(\d+)\}(.*)$')
    fps = default_fps
    rows = []
    for raw_line in text.split('\n'):
        m = line_re.match(raw_line)
        if not m:
            continue
        start_f, end_f, body = int(m.group(1)), int(m.group(2)), m.group(3)
        # A line like {1}{1}23.976 declares the frame rate.
        if start_f == end_f:
            try:
                fps = float(body.strip().replace(',', '.'))
                continue
            except ValueError:
                pass
        rows.append((start_f, end_f, body))
    if fps <= 0:
        fps = default_fps
    cues = []
    for start_f, end_f, body in rows:
        body = re.sub(r'\{[^}]*\}', '', body)        # strip {y:i}-style control codes
        body = body.replace('|', '\n').strip()
        if not body:
            continue
        cues.append(f'{_vtt_timestamp(start_f / fps)} --> {_vtt_timestamp(end_f / fps)}\n{body}')
    return '\n\n'.join(cues)


def _mpl2_to_vtt(text: str) -> str:
    """[start][end]text  →  WebVTT cues (deciseconds)."""
    line_re = re.compile(r'^\s*\[(\d+)\]\[(\d+)\](.*)$')
    cues = []
    for raw_line in text.split('\n'):
        m = line_re.match(raw_line)
        if not m:
            continue
        start, end = int(m.group(1)) / 10, int(m.group(2)) / 10
        body = m.group(3).replace('|', '\n').strip()
        if not body:
            continue
        cues.append(f'{_vtt_timestamp(start)} --> {_vtt_timestamp(end)}\n{body}')
    return '\n\n'.join(cues)


def _subviewer_to_vtt(text: str) -> str:
    """HH:MM:SS.cc,HH:MM:SS.cc + text  →  WebVTT cues."""
    ts = re.compile(r'(\d{2}):(\d{2}):(\d{2})\.(\d{2})\s*,\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2})')
    cues = []
    for block in re.split(r'\n\s*\n', text):
        lines = [l for l in block.split('\n') if l.strip()]
        if not lines:
            continue
        m = ts.search(lines[0])
        if not m:
            continue
        g = list(map(int, m.groups()))
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 100
        end   = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 100
        body = '\n'.join(lines[1:]).replace('[br]', '\n').strip()
        if not body:
            continue
        cues.append(f'{_vtt_timestamp(start)} --> {_vtt_timestamp(end)}\n{body}')
    return '\n\n'.join(cues)


def _subtitle_to_vtt(text: str) -> str:
    """Convert SRT / MicroDVD / MPL2 / SubViewer subtitle text to WebVTT.

    OpenSubtitles serves several formats under the .sub extension (mostly
    frame-based MicroDVD for CZ/SK). The HTML5 <track> element only accepts
    WebVTT, so normalise everything here. Note: frame-based formats need the
    video frame rate; without an in-file FPS declaration we assume 23.976,
    so MicroDVD subs may need sync adjustment.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n').lstrip('﻿')
    head = text.lstrip()
    if re.match(r'\{\d+\}\{\d+\}', head):
        body = _microdvd_to_vtt(text)
    elif re.match(r'\[\d+\]\[\d+\]', head):
        body = _mpl2_to_vtt(text)
    elif re.search(r'\d{2}:\d{2}:\d{2}\.\d{2}\s*,\s*\d{2}:\d{2}:\d{2}\.\d{2}', text):
        body = _subviewer_to_vtt(text)
    else:
        # SRT (or already VTT-ish): normalise comma decimals, drop any WEBVTT header.
        body = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', text)
        body = re.sub(r'^\s*WEBVTT[^\n]*\n+', '', body).strip()
    return 'WEBVTT\n\n' + body


# GET /api/movie|episode/{id}/subtitle-proxy?url=...  — proxy + convert any text format → VTT
def _subtitle_proxy(request, url: str):
    """Download subtitle, convert SRT/MicroDVD/MPL2/SubViewer to WebVTT."""
    from django.http import HttpResponse
    import gzip as gz

    if not url.startswith('https://dl.opensubtitles.org'):
        return api.create_response(request, {'detail': 'Invalid URL.'}, status=400)
    try:
        r = requests.get(url, headers={'User-Agent': 'DebridflixApp v1.0'}, timeout=10)
        content = r.content
        # OpenSubtitles sometimes returns gzipped content
        if content[:2] == b'\x1f\x8b':
            content = gz.decompress(content)
        raw_text = _decode_subtitle(content)
    except Exception as e:
        return api.create_response(request, {'detail': str(e)}, status=502)

    vtt = _subtitle_to_vtt(raw_text)
    return HttpResponse(vtt, content_type='text/vtt; charset=utf-8')


@api.get('/movie/{movie_id}/subtitle-proxy', auth=None)
def subtitle_proxy(request, movie_id: int, url: str):
    return _subtitle_proxy(request, url)


@api.get('/episode/{episode_id}/subtitle-proxy', auth=None)
def episode_subtitle_proxy(request, episode_id: int, url: str):
    return _subtitle_proxy(request, url)


# --- Auth endpoints ---

class LoginSchema(Schema):
    username: str
    password: str

class RegisterSchema(Schema):
    username: str
    password: str

class UserSchema(Schema):
    id: int
    username: str
    has_rd_key: bool

class ProfileUpdateSchema(Schema):
    rd_api_key: str


def _user_schema(user: User) -> dict:
    has_rd = hasattr(user, 'profile') and bool(user.profile.rd_api_key)
    return {'id': user.id, 'username': user.username, 'has_rd_key': has_rd}


@api.post("/auth/register", response=UserSchema, auth=None)
def register(request, payload: RegisterSchema):
    if User.objects.filter(username=payload.username).exists():
        return api.create_response(request, {'detail': 'Username already taken'}, status=400)
    user = User.objects.create_user(username=payload.username, password=payload.password)
    UserProfile.objects.create(user=user)
    return _user_schema(user)


@api.post("/auth/login", auth=None)
def login(request, payload: LoginSchema):
    user = authenticate(username=payload.username, password=payload.password)
    if not user:
        return api.create_response(request, {'detail': 'Invalid credentials'}, status=401)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return {'token': profile.auth_token, 'user': _user_schema(user)}


@api.get("/auth/me", response=UserSchema, auth=TokenAuth())
def me(request):
    return _user_schema(request.auth)


@api.get("/profile", auth=TokenAuth())
def get_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.auth)
    return {'username': request.auth.username, 'has_rd_key': bool(profile.rd_api_key)}


@api.put("/profile", auth=TokenAuth())
def update_profile(request, payload: ProfileUpdateSchema):
    profile, _ = UserProfile.objects.get_or_create(user=request.auth)
    # Validate key with RD before saving
    if payload.rd_api_key:
        try:
            r = requests.get(
                'https://api.real-debrid.com/rest/1.0/user',
                headers={'Authorization': f'Bearer {payload.rd_api_key}'},
                timeout=5,
            )
            if r.status_code != 200:
                return api.create_response(request, {'detail': 'Invalid Real-Debrid API key'}, status=400)
        except Exception:
            return api.create_response(request, {'detail': 'Could not reach Real-Debrid'}, status=502)
    profile.rd_api_key = payload.rd_api_key
    profile.save(update_fields=['rd_api_key'])
    return {'username': request.auth.username, 'has_rd_key': bool(profile.rd_api_key)}
