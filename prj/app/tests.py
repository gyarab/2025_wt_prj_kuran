import json
import os
import tempfile
from io import StringIO
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from app.models import Movie, Episode, UserProfile


def _write_tsv(path, header, rows):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\t'.join(header) + '\n')
        for row in rows:
            f.write('\t'.join(row) + '\n')


class ImportCommandTests(TransactionTestCase):
    """Exercise import_movies end-to-end on a tiny synthetic IMDb dataset.

    Uses TransactionTestCase (not TestCase) because the command issues
    ``PRAGMA synchronous = OFF``, which SQLite rejects inside the surrounding
    transaction that a plain TestCase would open.
    """

    def _make_data_dir(self, d):
        N = r'\N'
        _write_tsv(os.path.join(d, 'title.basics.tsv'),
                   ['tconst', 'titleType', 'primaryTitle', 'originalTitle',
                    'isAdult', 'startYear', 'endYear', 'runtimeMinutes', 'genres'],
                   [
                       ['tt100', 'movie', 'The Movie', N, '0', '1999', N, '120', 'Action,Drama'],
                       ['tt200', 'tvSeries', 'The Series', N, '0', '2010', '2015', N, 'Comedy'],
                       ['tt300', 'tvEpisode', 'Pilot', N, '0', '2010', N, '30', 'Comedy'],
                       ['tt301', 'tvEpisode', 'Finale', N, '0', '2011', N, '30', 'Comedy'],
                       ['tt900', 'short', 'A Short', N, '0', '2000', N, '5', 'Comedy'],
                   ])
        _write_tsv(os.path.join(d, 'title.episode.tsv'),
                   ['tconst', 'parentTconst', 'seasonNumber', 'episodeNumber'],
                   [
                       ['tt300', 'tt200', '1', '1'],
                       ['tt301', 'tt200', '2', '3'],
                       ['tt999', 'tt404', N, N],  # parent not imported -> ignored
                   ])
        _write_tsv(os.path.join(d, 'title.ratings.tsv'),
                   ['tconst', 'averageRating', 'numVotes'],
                   [
                       ['tt100', '7.5', '1000'],
                       ['tt200', '8.8', '5000'],
                       ['tt300', '8.0', '200'],
                   ])
        _write_tsv(os.path.join(d, 'title.crew.tsv'),
                   ['tconst', 'directors', 'writers'],
                   [
                       ['tt100', 'nm1', 'nm2'],
                       ['tt200', 'nm1', N],
                   ])
        _write_tsv(os.path.join(d, 'title.principals.tsv'),
                   ['tconst', 'ordering', 'nconst', 'category', 'job', 'characters'],
                   [
                       ['tt100', '1', 'nm3', 'actor', N, N],
                       ['tt200', '1', 'nm3', 'actress', N, N],
                   ])
        _write_tsv(os.path.join(d, 'name.basics.tsv'),
                   ['nconst', 'primaryName', 'birthYear', 'deathYear',
                    'primaryProfession', 'knownForTitles'],
                   [
                       ['nm1', 'Dir One', N, N, 'director', N],
                       ['nm2', 'Writer Two', N, N, 'writer', N],
                       ['nm3', 'Actor Three', N, N, 'actor', N],
                   ])

    def test_import_movies_and_episodes(self):
        with tempfile.TemporaryDirectory() as d:
            self._make_data_dir(d)
            call_command('import_movies', '--data-dir', d, stdout=StringIO())

        # Movies vs series (short/episodes excluded from the Movie table)
        self.assertEqual(Movie.objects.filter(kind=Movie.MOVIE).count(), 1)
        self.assertEqual(Movie.objects.filter(kind=Movie.SERIES).count(), 1)

        series = Movie.objects.get(imdb_id='tt200')
        self.assertEqual(series.kind, Movie.SERIES)
        self.assertEqual(series.release_year, 2010)
        self.assertEqual(series.end_year, 2015)
        self.assertEqual(series.rating, 8.8)

        # Episodes linked to the series, with season/episode/rating
        eps = list(series.episodes.all())  # ordered by season, episode
        self.assertEqual([(e.season_number, e.episode_number, e.title) for e in eps],
                         [(1, 1, 'Pilot'), (2, 3, 'Finale')])
        self.assertEqual(eps[0].rating, 8.0)
        # Episode whose parent wasn't imported is skipped
        self.assertFalse(Episode.objects.filter(imdb_id='tt999').exists())

    def test_no_episodes_flag(self):
        with tempfile.TemporaryDirectory() as d:
            self._make_data_dir(d)
            call_command('import_movies', '--data-dir', d, '--no-episodes',
                         stdout=StringIO())
        self.assertEqual(Movie.objects.filter(kind=Movie.SERIES).count(), 1)
        self.assertEqual(Episode.objects.count(), 0)


class SeriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.movie = Movie.objects.create(
            title='A Movie', imdb_id='tt0000001', kind=Movie.MOVIE, release_year=1999)
        cls.series = Movie.objects.create(
            title='A Series', imdb_id='tt0000002', kind=Movie.SERIES,
            release_year=2010, end_year=2015)
        cls.ep1 = Episode.objects.create(
            series=cls.series, imdb_id='tt0000003', title='Pilot',
            season_number=1, episode_number=1, rating=8.0)
        cls.ep2 = Episode.objects.create(
            series=cls.series, imdb_id='tt0000004', title='Finale',
            season_number=2, episode_number=1)

    # --- Home page filter ---

    def test_home_defaults_to_movies(self):
        html = self.client.get('/').content.decode()
        self.assertIn('A Movie', html)
        self.assertNotIn('A Series', html)

    def test_home_kind_series(self):
        html = self.client.get('/', {'kind': 'series'}).content.decode()
        self.assertIn('A Series', html)
        self.assertNotIn('A Movie', html)
        # pagination links must carry the kind
        self.assertIn('kind=series', html)

    def test_home_kind_all_shows_both_with_labels(self):
        html = self.client.get('/', {'kind': 'all'}).content.decode()
        self.assertIn('A Movie', html)
        self.assertIn('A Series', html)
        self.assertIn('(Series)', html)

    # --- API ---

    def test_api_movie_defaults_to_movies(self):
        data = self.client.get('/api/movie').json()
        kinds = {m['kind'] for m in data}
        self.assertEqual(kinds, {'movie'})

    def test_api_movie_kind_series(self):
        data = self.client.get('/api/movie', {'kind': 'series'}).json()
        self.assertEqual([m['title'] for m in data], ['A Series'])
        self.assertEqual(data[0]['end_year'], 2015)

    def test_api_movie_kind_all(self):
        data = self.client.get('/api/movie', {'kind': 'all'}).json()
        self.assertEqual({m['kind'] for m in data}, {'movie', 'series'})

    def test_api_episodes_endpoint(self):
        data = self.client.get(f'/api/movie/{self.series.id}/episodes').json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['title'], 'Pilot')  # ordered by season, episode

    def test_api_episodes_season_filter(self):
        data = self.client.get(
            f'/api/movie/{self.series.id}/episodes', {'season': 2}).json()
        self.assertEqual([e['title'] for e in data], ['Finale'])

    def test_api_seasons_endpoint(self):
        Episode.objects.create(
            series=self.series, imdb_id='tt0000005', title='Special',
            season_number=None, episode_number=None)
        data = self.client.get(f'/api/movie/{self.series.id}/seasons').json()
        # season 1 (1 ep), season 2 (1 ep), and the null/"other" bucket (1 ep)
        self.assertEqual(
            [(s['season'], s['episode_count']) for s in data],
            [(None, 1), (1, 1), (2, 1)])

    def test_api_episodes_unseasoned_filter(self):
        Episode.objects.create(
            series=self.series, imdb_id='tt0000005', title='Special',
            season_number=None, episode_number=None)
        data = self.client.get(
            f'/api/movie/{self.series.id}/episodes', {'unseasoned': 'true'}).json()
        self.assertEqual([e['title'] for e in data], ['Special'])

    # --- TMDB series vs movie field/endpoint selection ---

    def test_fetch_poster_uses_tv_endpoints_for_series(self):
        import api as app_api  # api.py lives at the project root, not under app/

        calls = []

        def fake_get(url, params=None, timeout=None):
            calls.append((url, params or {}))
            m = mock.Mock()
            m.json.return_value = {}          # nothing found -> falls through all sources
            m.status_code = 200
            return m

        with mock.patch.object(app_api.requests, 'get', side_effect=fake_get):
            app_api._fetch_poster_and_plot(self.series)

        urls = [u for u, _ in calls]
        # A series must use the TV search endpoint with the TV year param,
        # never the movie ones.
        self.assertTrue(any('search/tv' in u for u in urls), urls)
        self.assertFalse(any('search/movie' in u for u in urls), urls)
        search_params = next(p for u, p in calls if 'search/tv' in u)
        self.assertIn('first_air_date_year', search_params)


class EpisodeStreamTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.series = Movie.objects.create(
            title='A Series', imdb_id='tt0000002', kind=Movie.SERIES)
        cls.ep = Episode.objects.create(
            series=cls.series, imdb_id='tt0000003', title='Pilot',
            season_number=1, episode_number=1)
        cls.ep_unseasoned = Episode.objects.create(
            series=cls.series, imdb_id='tt0000009', title='Special',
            season_number=None, episode_number=None)
        cls.user = User.objects.create_user('streamer', password='pw')
        cls.profile = UserProfile.objects.create(user=cls.user, rd_api_key='rdkey')

    def _auth(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.profile.auth_token}'}

    def test_streams_use_series_route(self):
        import api as app_api
        with mock.patch.object(app_api, '_torrentio_streams', return_value=[]) as mt:
            res = self.client.get(f'/api/episode/{self.ep.id}/streams', **self._auth())
        self.assertEqual(res.status_code, 200)
        # series imdb id + season:episode, not the episode's own tconst
        mt.assert_called_once_with('series', 'tt0000002:1:1')

    def test_streams_need_auth(self):
        res = self.client.get(f'/api/episode/{self.ep.id}/streams')
        self.assertEqual(res.status_code, 401)

    def test_streams_reject_unseasoned_episode(self):
        import api as app_api
        with mock.patch.object(app_api, '_torrentio_streams') as mt:
            res = self.client.get(
                f'/api/episode/{self.ep_unseasoned.id}/streams', **self._auth())
        self.assertEqual(res.status_code, 400)
        mt.assert_not_called()

    def test_stream_post_runs_through_rd(self):
        import api as app_api
        with mock.patch.object(app_api, '_rd_process',
                               return_value={'url': 'http://x', 'filename': 'f'}) as mp:
            res = self.client.post(
                f'/api/episode/{self.ep.id}/stream',
                data=json.dumps({'info_hash': 'abc', 'file_ids': []}),
                content_type='application/json', **self._auth())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['url'], 'http://x')
        mp.assert_called_once_with('rdkey', 'abc', [])

    def test_episode_subtitles_use_episode_imdb(self):
        import api as app_api
        with mock.patch.object(app_api, '_opensubtitles_search',
                               return_value=[]) as ms:
            res = self.client.get(f'/api/episode/{self.ep.id}/subtitles',
                                  {'language': 'cs'})
        self.assertEqual(res.status_code, 200)
        # called with the episode's own imdb id and the requested language
        args = ms.call_args.args
        self.assertEqual(args[1], 'tt0000003')
        self.assertEqual(args[2], 'cs')
