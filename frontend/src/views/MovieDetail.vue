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

// streaming
const showPicker    = ref(false)
const streamUrl     = ref('')
const streamName    = ref('')
const streamQuality = ref('')
const subtitleUrl   = ref('')

async function load(id) {
    loading.value = true
    error.value = ''
    movie.value = null
    try {
        const res = await fetch(`/api/movie/${id}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        movie.value = await res.json()
    } catch (e) {
        error.value = e.message
    } finally {
        loading.value = false
    }
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

function play() {
    if (!isLoggedIn.value) { router.push('/login'); return }
    if (!hasRdKey.value)   { router.push('/profile'); return }
    showPicker.value = true
}

function onStreamReady({ url, filename, quality, subtitleUrl: sub }) {
    showPicker.value    = false
    streamUrl.value     = url
    streamName.value    = filename
    streamQuality.value = quality
    subtitleUrl.value   = sub || ''
}

function closePlayer() {
    streamUrl.value  = ''
    subtitleUrl.value = ''
}

watch(() => route.params.id, load, { immediate: true })
</script>

<template>
    <!-- Stream picker -->
    <Teleport to="body">
        <StreamPicker
            v-if="showPicker"
            :movie-id="movie?.id"
            :movie-title="movie?.title"
            @play="onStreamReady"
            @close="showPicker = false"
        />
    </Teleport>

    <!-- Video player overlay -->
    <Teleport to="body">
        <div v-if="streamUrl" class="player-overlay" @click.self="closePlayer">
            <div class="player-box">
                <div class="player-header">
                    <span class="player-title">{{ streamName || movie?.title }}</span>
                    <span v-if="streamQuality" class="player-quality">{{ streamQuality }}</span>
                    <button class="player-close" @click="closePlayer">✕</button>
                </div>
                <video
                    class="player-video"
                    :src="streamUrl"
                    controls
                    autoplay
                >
                    <track v-if="subtitleUrl" :src="subtitleUrl" kind="subtitles" default />
                </video>
                <div class="player-fallback">
                    <a :href="streamUrl" target="_blank" rel="noopener" class="player-open-link">
                        ↗ Open in new tab / download
                    </a>
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
                        <button class="btn-play" @click="play">▶ Play</button>
                        <button class="btn-seen" :class="{ seen: movie.is_seen }" @click="toggleSeen">
                            {{ movie.is_seen ? '✓ Seen' : 'Mark as seen' }}
                        </button>
                    </div>
                </div>
            </div>

            <!-- More info -->
            <div class="more-info">
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
    text-align: center;
}

.player-open-link {
    color: #666; font-size: 0.82rem;
    transition: color 0.15s;
}
.player-open-link:hover { color: #ccc; }
</style>
