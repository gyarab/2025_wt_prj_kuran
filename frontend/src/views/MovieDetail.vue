<script setup>
import { ref, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../auth.js'
import StreamPicker from '../components/StreamPicker.vue'

const route = useRoute()
const router = useRouter()
const { isLoggedIn, hasRdKey, authFetch } = useAuth()
const movie = ref(null)
const loading = ref(false)
const error = ref('')

// series episodes
const isSeries = computed(() => movie.value?.kind === 'series')
const seasons = ref([])             // [{ season, episode_count }]
const selectedSeason = ref(null)    // a season number, or 'none' for unseasoned
const episodes = ref([])
const episodesLoading = ref(false)
const pad = (n) => String(n).padStart(2, '0')

// streaming
const showPicker    = ref(false)
const streamBase    = ref('')   // API prefix for the chosen title: /api/movie/N or /api/episode/N
const streamTitle   = ref('')
const streamUrl     = ref('')
const streamName    = ref('')
const streamQuality = ref('')
const subtitleUrl   = ref('')
const subtitleLang  = ref('')
const copied        = ref(false)

const SUBTITLE_LABELS = { cs: 'Czech', sk: 'Slovak', en: 'English' }

let loadSeq = 0   // guards against a slow response for a previous movie winning

async function load(id) {
    const seq = ++loadSeq
    loading.value = true
    error.value = ''
    movie.value = null
    try {
        const res = await fetch(`/api/movie/${id}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (seq !== loadSeq) return   // navigated to another movie; discard
        movie.value = data
        seasons.value = []
        episodes.value = []
        selectedSeason.value = null
        if (data.kind === 'series') loadSeasons(data.id, seq)
    } catch (e) {
        if (seq === loadSeq) error.value = e.message
    } finally {
        if (seq === loadSeq) loading.value = false
    }
}

async function loadSeasons(id, seq) {
    try {
        const res = await fetch(`/api/movie/${id}/seasons`)
        if (!res.ok || seq !== loadSeq) return
        seasons.value = await res.json()
        if (seasons.value.length) {
            const first = seasons.value[0]
            selectSeason(first.season === null ? 'none' : first.season)
        }
    } catch { /* silent */ }
}

async function loadEpisodes(id, seq) {
    episodesLoading.value = true
    try {
        const params = new URLSearchParams()
        if (selectedSeason.value === 'none') params.set('unseasoned', 'true')
        else if (selectedSeason.value !== null) params.set('season', String(selectedSeason.value))
        const res = await fetch(`/api/movie/${id}/episodes?${params}`)
        const data = res.ok ? await res.json() : []
        if (seq !== loadSeq) return   // navigated away; discard
        episodes.value = data
    } catch {
        episodes.value = []
    } finally {
        episodesLoading.value = false
    }
}

function selectSeason(s) {
    selectedSeason.value = s
    loadEpisodes(movie.value.id, loadSeq)
}

async function toggleSeen() {
    if (!movie.value) return
    const res = await fetch(`/api/movie/${movie.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_seen: !movie.value.is_seen }),
    })
    if (res.ok) movie.value = await res.json()
}

const duration = computed(() => {
    if (!movie.value?.duration) return null
    const h = Math.floor(movie.value.duration / 60)
    const m = movie.value.duration % 60
    return h > 0 ? `${h}h ${m}m` : `${m}m`
})

const imdbUrl = computed(() =>
    movie.value ? `https://www.imdb.com/title/${movie.value.imdb_id}/` : '#'
)

function openPicker(base, title) {
    if (!isLoggedIn.value) { router.push('/login'); return }
    if (!hasRdKey.value)   { router.push('/profile'); return }
    streamBase.value  = base
    streamTitle.value = title
    showPicker.value  = true
}

function play() {
    openPicker(`/api/movie/${movie.value.id}`, movie.value.title)
}

function playEpisode(ep) {
    const code = (ep.season_number != null && ep.episode_number != null)
        ? `S${pad(ep.season_number)}E${pad(ep.episode_number)} · ` : ''
    openPicker(`/api/episode/${ep.id}`, `${movie.value.title} — ${code}${ep.title}`)
}

function onStreamReady({ url, filename, quality, subtitleUrl: sub, subtitleLang: subLang }) {
    showPicker.value    = false
    streamUrl.value     = url
    streamName.value    = filename
    streamQuality.value = quality
    subtitleUrl.value   = sub || ''
    subtitleLang.value  = subLang || ''
}

function closePlayer() {
    streamUrl.value    = ''
    subtitleUrl.value  = ''
    subtitleLang.value = ''
    copied.value       = false
}

// Build an .m3u playlist pointing at the Real-Debrid direct URL. The file itself
// is a tiny text pointer — VLC (or any default player) streams the video over
// HTTP from RD without downloading it. The selected subtitle, if any, rides along
// as a slave input so you can fix sync in VLC (G / H keys).
function buildPlaylist() {
    const title = (streamName.value || movie.value?.title || 'stream').trim()
    const lines = ['#EXTM3U', `#EXTINF:-1,${title}`]
    if (subtitleUrl.value) {
        const absSub = new URL(subtitleUrl.value, window.location.origin).href
        lines.push(`#EXTVLCOPT:input-slave=${absSub}`)
    }
    lines.push(streamUrl.value)
    return lines.join('\n') + '\n'
}

function openInExternalPlayer() {
    if (!streamUrl.value) return
    const safe = (streamName.value || movie.value?.title || 'stream')
        .replace(/[^\w.-]+/g, '_').slice(0, 80) || 'stream'
    const blob = new Blob([buildPlaylist()], { type: 'audio/x-mpegurl' })
    const href = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = href
    a.download = `${safe}.m3u`
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(href), 15000)
}

async function copyStreamLink() {
    if (!streamUrl.value) return
    try {
        await navigator.clipboard.writeText(streamUrl.value)
        copied.value = true
        setTimeout(() => { copied.value = false }, 2000)
    } catch {
        // Clipboard API blocked (e.g. non-secure context) — fall back to a prompt.
        window.prompt('Stream URL — paste into VLC ▸ Open Network Stream (Ctrl+N):', streamUrl.value)
    }
}

watch(() => route.params.id, load, { immediate: true })
</script>

<template>
    <!-- Stream picker -->
    <Teleport to="body">
        <StreamPicker
            v-if="showPicker"
            :base="streamBase"
            :title="streamTitle"
            @play="onStreamReady"
            @close="showPicker = false"
        />
    </Teleport>

    <!-- Video player overlay -->
    <Teleport to="body">
        <div v-if="streamUrl" class="player-overlay" @click.self="closePlayer">
            <div class="player-box">
                <div class="player-header">
                    <span class="player-title">{{ streamName || streamTitle || movie?.title }}</span>
                    <span v-if="streamQuality" class="player-quality">{{ streamQuality }}</span>
                    <button class="player-close" @click="closePlayer">✕</button>
                </div>
                <video
                    class="player-video"
                    :src="streamUrl"
                    controls
                    autoplay
                >
                    <track v-if="subtitleUrl" :src="subtitleUrl" kind="subtitles"
                        :srclang="subtitleLang || 'und'"
                        :label="SUBTITLE_LABELS[subtitleLang] || 'Subtitles'" default />
                </video>
                <div class="player-fallback">
                    <button class="ext-action ext-vlc" @click="openInExternalPlayer">
                        ▶ Open in VLC / player
                    </button>
                    <button class="ext-action" @click="copyStreamLink">
                        {{ copied ? '✓ Link copied' : '⧉ Copy stream link' }}
                    </button>
                    <a :href="streamUrl" target="_blank" rel="noopener" class="ext-action">↗ New tab</a>
                </div>
            </div>
        </div>
    </Teleport>

    <div v-if="loading" class="state-msg">Loading…</div>
    <div v-else-if="error" class="state-msg error">Error: {{ error }}</div>

    <div v-else-if="movie" class="detail">
        <div class="backdrop"
            :style="movie.poster_url ? `background-image: url(${movie.poster_url})` : ''">
        </div>

        <div class="detail-body">
            <RouterLink to="/" class="back-link">← Back</RouterLink>

            <!-- Hero: poster + core info side by side -->
            <div class="hero">
                <div class="hero-poster">
                    <img v-if="movie.poster_url" :src="movie.poster_url" :alt="movie.title" />
                    <div v-else class="placeholder"></div>
                </div>

                <div class="hero-info">
                    <h1 class="title">{{ movie.title }}</h1>
                    <p v-if="movie.original_title && movie.original_title !== movie.title" class="original-title">
                        {{ movie.original_title }}
                    </p>

                    <div class="quick-meta">
                        <span v-if="movie.release_year">{{ movie.release_year }}</span>
                        <span v-if="duration" class="sep">·</span>
                        <span v-if="duration">{{ duration }}</span>
                        <span v-if="movie.genres.length" class="sep">·</span>
                        <span v-if="movie.genres.length">{{ movie.genres.map(g => g.name).join(', ') }}</span>
                    </div>

                    <div class="badges">
                        <span v-if="movie.rating" class="badge badge-imdb">IMDb {{ movie.rating }}</span>
                        <span v-if="movie.num_votes" class="badge badge-votes">
                            {{ movie.num_votes >= 1000 ? (movie.num_votes / 1000).toFixed(0) + 'k' : movie.num_votes }} votes
                        </span>
                    </div>

                    <p v-if="movie.plot_summary" class="plot">{{ movie.plot_summary }}</p>

                    <div class="info-block">
                        <div v-if="movie.directors.length" class="info-row">
                            <span class="info-label">Director{{ movie.directors.length > 1 ? 's' : '' }}</span>
                            <div class="info-value">
                                <RouterLink v-for="d in movie.directors" :key="d.id"
                                    :to="`/director/${d.id}`" class="person-link">{{ d.name }}</RouterLink>
                            </div>
                        </div>
                        <div v-if="movie.writers.length" class="info-row">
                            <span class="info-label">Writer{{ movie.writers.length > 1 ? 's' : '' }}</span>
                            <div class="info-value">
                                <RouterLink v-for="w in movie.writers" :key="w.id"
                                    :to="`/writer/${w.id}`" class="person-link">{{ w.name }}</RouterLink>
                            </div>
                        </div>
                    </div>

                    <div class="actions">
                        <!-- Series play per-episode (below); movies play here. -->
                        <button v-if="!isSeries" class="btn-play" @click="play">▶ Play</button>
                        <button class="btn-seen" :class="{ seen: movie.is_seen }" @click="toggleSeen">
                            {{ movie.is_seen ? '✓ Seen' : 'Mark as seen' }}
                        </button>
                    </div>
                </div>
            </div>

            <!-- More info -->
            <div class="more-info">
                <section v-if="isSeries" class="section">
                    <h3 class="section-title">Episodes</h3>

                    <div v-if="seasons.length" class="chip-bar season-bar">
                        <button v-for="s in seasons" :key="s.season ?? 'none'" class="chip"
                            :class="{ active: (s.season === null ? 'none' : s.season) === selectedSeason }"
                            @click="selectSeason(s.season === null ? 'none' : s.season)">
                            {{ s.season === null ? 'Other' : 'Season ' + s.season }}
                            <span class="chip-count">{{ s.episode_count }}</span>
                        </button>
                    </div>

                    <p v-if="episodesLoading" class="ep-msg">Loading episodes…</p>
                    <ul v-else-if="episodes.length" class="ep-list">
                        <li v-for="ep in episodes" :key="ep.id" class="ep-row" :class="{ seen: ep.is_seen }">
                            <span class="ep-num">{{ ep.season_number != null && ep.episode_number != null
                                ? `S${pad(ep.season_number)}E${pad(ep.episode_number)}` : '—' }}</span>
                            <span class="ep-title">{{ ep.title }}</span>
                            <span v-if="ep.rating" class="ep-rating">★ {{ ep.rating }}</span>
                            <span v-if="ep.release_year" class="ep-year">{{ ep.release_year }}</span>
                            <button class="ep-play" @click="playEpisode(ep)" title="Play episode">▶</button>
                        </li>
                    </ul>
                    <p v-else class="ep-msg">No episodes found.</p>
                </section>

                <section v-if="movie.actors.length" class="section">
                    <h3 class="section-title">Cast</h3>
                    <div class="cast-grid">
                        <RouterLink v-for="a in movie.actors" :key="a.id"
                            :to="`/actor/${a.id}`" class="cast-chip">{{ a.name }}</RouterLink>
                    </div>
                </section>

                <section class="section">
                    <h3 class="section-title">Details</h3>
                    <div class="details-table">
                        <div v-if="movie.release_year" class="detail-row">
                            <span class="detail-label">Year</span>
                            <span>{{ movie.release_year }}</span>
                        </div>
                        <div v-if="duration" class="detail-row">
                            <span class="detail-label">Runtime</span>
                            <span>{{ duration }} ({{ movie.duration }} min)</span>
                        </div>
                        <div v-if="movie.genres.length" class="detail-row">
                            <span class="detail-label">Genres</span>
                            <span>{{ movie.genres.map(g => g.name).join(', ') }}</span>
                        </div>
                        <div v-if="movie.original_title && movie.original_title !== movie.title" class="detail-row">
                            <span class="detail-label">Original title</span>
                            <span>{{ movie.original_title }}</span>
                        </div>
                        <div v-if="movie.rating" class="detail-row">
                            <span class="detail-label">IMDb rating</span>
                            <span>{{ movie.rating }} / 10
                                <span v-if="movie.num_votes" class="muted">({{ movie.num_votes.toLocaleString() }} votes)</span>
                            </span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">IMDb</span>
                            <a :href="imdbUrl" target="_blank" rel="noopener" class="external-link">{{ movie.imdb_id }} ↗</a>
                        </div>
                    </div>
                </section>
            </div>
        </div>
    </div>
</template>

<style scoped>
.state-msg { padding: 60px 0; color: #888; font-size: 1.1rem; }
.state-msg.error { color: #e50914; }

.detail { position: relative; }

.backdrop {
    position: fixed; inset: 0; z-index: -1;
    background-size: cover; background-position: center;
    filter: blur(40px) brightness(0.18);
    transform: scale(1.1);
}

.detail-body { padding: 32px 0 80px; }

.back-link {
    display: inline-block; color: #aaa; font-size: 1rem;
    margin-bottom: 32px; transition: color 0.15s;
}
.back-link:hover { color: #fff; }

/* Hero */
.hero {
    display: flex;
    gap: 40px;
    align-items: flex-start;
    margin-bottom: 48px;
}

.hero-poster {
    flex-shrink: 0;
    width: 200px;
    aspect-ratio: 2 / 3;
    border-radius: 10px;
    overflow: hidden;
    background: #1a1a1a;
    box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}
@media (min-width: 1024px) { .hero-poster { width: 260px; } }
@media (min-width: 1440px) { .hero-poster { width: 320px; } }
@media (min-width: 1920px) { .hero-poster { width: 360px; } }

.hero-poster img { width: 100%; height: 100%; object-fit: cover; display: block; }

.placeholder {
    width: 100%; height: 100%;
    background:
        linear-gradient(to bottom right, transparent calc(50% - 1px), #2e2e2e calc(50% - 1px), #2e2e2e calc(50% + 1px), transparent calc(50% + 1px)),
        linear-gradient(to bottom left,  transparent calc(50% - 1px), #2e2e2e calc(50% - 1px), #2e2e2e calc(50% + 1px), transparent calc(50% + 1px)),
        #181818;
}

.hero-info { flex: 1; min-width: 0; }

.title { margin: 0 0 6px; font-size: 2rem; line-height: 1.2; font-weight: 700; }
@media (min-width: 1440px) { .title { font-size: 2.4rem; } }
@media (min-width: 1920px) { .title { font-size: 2.8rem; } }

.original-title { margin: 0 0 10px; color: #666; font-size: 0.9rem; font-style: italic; }

.quick-meta { font-size: 0.9rem; color: #888; margin-bottom: 16px; line-height: 1.6; }
.sep { margin: 0 6px; color: #444; }

.badges { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }

.badge { font-size: 0.85rem; font-weight: 700; padding: 5px 12px; border-radius: 6px; }
.badge-imdb { background: #f5c518; color: #000; }
.badge-votes { background: #222; color: #aaa; border: 1px solid #333; }

.plot {
    font-size: 1rem; line-height: 1.7; color: #ccc;
    margin: 0 0 24px;
    border-left: 4px solid #e50914; padding-left: 16px;
    max-width: 800px;
}
@media (min-width: 1920px) { .plot { font-size: 1.05rem; max-width: 1000px; } }

.info-block { margin-bottom: 8px; }

.info-row {
    display: flex; gap: 12px; font-size: 0.9rem;
    margin-bottom: 10px; align-items: baseline; flex-wrap: wrap;
}
.info-label { color: #555; flex-shrink: 0; width: 76px; font-size: 0.82rem; }
.info-value { display: flex; flex-wrap: wrap; gap: 4px; }

.person-link {
    color: #ccc; border-bottom: 1px solid #333; margin-right: 8px;
    transition: color 0.15s, border-color 0.15s;
}
.person-link:hover { color: #fff; border-color: #888; }

/* Actions */
.actions { display: flex; gap: 14px; margin-top: 32px; }

.btn-play, .btn-seen {
    padding: 16px 40px;
    border: none; border-radius: 8px;
    font-size: 1rem; font-weight: 600;
    transition: opacity 0.15s;
    min-width: 160px;
}
@media (min-width: 1440px) {
    .btn-play, .btn-seen { padding: 18px 48px; font-size: 1.05rem; min-width: 180px; }
}
.btn-play { background: #e50914; color: #fff; }
.btn-play:hover { opacity: 0.85; }
.btn-seen { background: transparent; border: 1px solid #444; color: #aaa; }
.btn-seen.seen { border-color: #4caf50; color: #4caf50; }
.btn-seen:hover { border-color: #888; color: #e5e5e5; }

/* More info */
.more-info { border-top: 1px solid #1e1e1e; padding-top: 40px; }

.section { margin-bottom: 40px; }

.section-title {
    font-size: 0.75rem; text-transform: uppercase;
    letter-spacing: 0.12em; color: #555;
    margin: 0 0 16px; font-weight: 600;
}

.cast-grid { display: flex; flex-wrap: wrap; gap: 8px; }

.cast-chip {
    font-size: 0.88rem; color: #bbb;
    background: #1a1a1a; border: 1px solid #2a2a2a;
    padding: 8px 16px; border-radius: 24px;
    transition: border-color 0.15s, color 0.15s;
}
.cast-chip:hover { border-color: #666; color: #fff; }

/* Episodes */
.chip-bar { display: flex; flex-wrap: wrap; gap: 7px; }
.season-bar { margin-bottom: 20px; }

.chip {
    display: inline-flex; align-items: center; gap: 8px;
    background: #1a1a1a; border: 1px solid #2a2a2a; color: #888;
    font-size: 0.82rem; padding: 7px 16px; border-radius: 24px;
    transition: border-color 0.15s, color 0.15s;
}
.chip:hover { border-color: #555; color: #ccc; }
.chip.active { border-color: #e50914; color: #e5e5e5; }
.chip-count {
    font-size: 0.72rem; color: #666;
    background: #000; border-radius: 12px; padding: 1px 8px;
}
.chip.active .chip-count { color: #aaa; }

.ep-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.ep-row {
    display: flex; align-items: baseline; gap: 14px;
    padding: 12px 8px; border-bottom: 1px solid #1a1a1a;
    font-size: 0.92rem;
}
.ep-row:hover { background: #141414; }
.ep-num {
    flex-shrink: 0; width: 72px; color: #777;
    font-variant-numeric: tabular-nums; font-size: 0.82rem;
}
.ep-title { flex: 1; min-width: 0; color: #ccc; }
.ep-rating { flex-shrink: 0; color: #f5c518; font-size: 0.82rem; }
.ep-year { flex-shrink: 0; color: #555; font-size: 0.82rem; width: 40px; text-align: right; }
.ep-play {
    flex-shrink: 0;
    background: transparent; border: 1px solid #333; color: #aaa;
    border-radius: 6px; padding: 5px 12px; font-size: 0.82rem;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.ep-play:hover { border-color: #e50914; color: #fff; background: #e50914; }
.ep-row.seen .ep-title { color: #6a6a6a; }
.ep-msg { color: #444; font-size: 0.9rem; padding: 12px 0; }

.details-table { display: flex; flex-direction: column; gap: 14px; }

.detail-row { display: flex; gap: 16px; font-size: 0.95rem; align-items: baseline; }
.detail-label { color: #555; flex-shrink: 0; width: 120px; font-size: 0.82rem; }
.muted { color: #666; }

.external-link { color: #aaa; border-bottom: 1px solid #333; transition: color 0.15s; }
.external-link:hover { color: #f5c518; border-color: #f5c518; }


/* Player overlay */
.player-overlay {
    position: fixed; inset: 0; z-index: 1000;
    background: rgba(0,0,0,0.92);
    display: flex; align-items: center; justify-content: center;
    padding: 20px;
}

.player-box {
    width: 100%; max-width: 1400px;
    background: #0a0a0a;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 20px 80px rgba(0,0,0,0.8);
}

.player-header {
    display: flex; align-items: center; gap: 12px;
    padding: 14px 20px;
    background: #111; border-bottom: 1px solid #222;
}

.player-title {
    flex: 1; font-size: 0.95rem; color: #ccc;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

.player-quality {
    font-size: 0.75rem; color: #888;
    background: #1a1a1a; border: 1px solid #333;
    padding: 2px 10px; border-radius: 20px;
}

.player-close {
    background: none; border: none; color: #666;
    font-size: 1.1rem; padding: 4px 8px;
    transition: color 0.15s;
}
.player-close:hover { color: #fff; }

.player-video {
    width: 100%;
    aspect-ratio: 16 / 9;
    background: #000;
    display: block;
}

.player-fallback {
    padding: 12px 20px; background: #111; border-top: 1px solid #1e1e1e;
    display: flex; align-items: center; justify-content: center;
    gap: 10px; flex-wrap: wrap;
}

.ext-action {
    background: #1a1a1a; border: 1px solid #2a2a2a; color: #aaa;
    font-size: 0.82rem; padding: 7px 14px; border-radius: 6px;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.ext-action:hover { border-color: #555; color: #fff; }

.ext-vlc { border-color: #e8590c; color: #ff7518; }
.ext-vlc:hover { background: #e8590c; color: #fff; border-color: #e8590c; }
</style>
