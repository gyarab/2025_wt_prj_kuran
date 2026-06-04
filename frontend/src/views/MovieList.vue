<script setup>
import { ref, onMounted } from 'vue'

const genres = ref([])
async function loadGenres() {
    try {
        const res = await fetch('/api/genre')
        if (res.ok) genres.value = await res.json()
    } catch { /* silent */ }
}

const movies = ref([])
const query = ref('')
const sort = ref('votes')
const minVotes = ref(5000)
const genre = ref(null)
const loading = ref(false)
const error = ref('')
const offset = ref(0)
const hasMore = ref(true)
const LIMIT = 20

const SORT_OPTIONS = [
    { value: 'votes',         label: 'Most popular' },
    { value: 'rating',        label: 'Top rated' },
    { value: 'year_desc',     label: 'Newest' },
    { value: 'year_asc',      label: 'Oldest' },
    { value: 'duration_asc',  label: 'Shortest' },
    { value: 'duration_desc', label: 'Longest' },
    { value: 'title_asc',     label: 'A → Z' },
    { value: 'title_desc',    label: 'Z → A' },
    { value: 'seen',          label: 'Seen first' },
]

const VOTE_FILTERS = [
    { value: 0,      label: 'Any' },
    { value: 1000,   label: '1k+' },
    { value: 5000,   label: '5k+' },
    { value: 50000,  label: '50k+' },
    { value: 500000, label: '500k+' },
]

async function load(reset = true) {
    if (reset) {
        offset.value = 0
        movies.value = []
        hasMore.value = true
    }
    loading.value = true
    error.value = ''
    try {
        const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset.value), sort: sort.value, min_votes: String(minVotes.value) })
        if (genre.value) params.set('genre', genre.value)
        if (query.value.trim()) params.set('q', query.value.trim())
        const res = await fetch(`/api/movie?${params}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const batch = await res.json()
        movies.value = reset ? batch : [...movies.value, ...batch]
        offset.value += batch.length
        hasMore.value = batch.length === LIMIT
        fetchMissingPosters(batch)
    } catch (e) {
        error.value = e.message
    } finally {
        loading.value = false
    }
}

async function fetchMissingPosters(batch) {
    const missing = batch.filter(m => !m.poster_url)
    const CONCURRENCY = 4
    for (let i = 0; i < missing.length; i += CONCURRENCY) {
        await Promise.all(
            missing.slice(i, i + CONCURRENCY).map(async (m) => {
                try {
                    const res = await fetch(`/api/movie/${m.id}`)
                    if (!res.ok) return
                    const detail = await res.json()
                    if (detail.poster_url) {
                        const idx = movies.value.findIndex(x => x.id === m.id)
                        if (idx !== -1) movies.value[idx] = { ...movies.value[idx], poster_url: detail.poster_url }
                    }
                } catch { /* silent */ }
            })
        )
    }
}

onMounted(() => { load(); loadGenres() })
</script>

<template>
    <div class="list-wrap">
        <form class="search-bar" @submit.prevent="load(true)">
            <input v-model="query" type="text" placeholder="Search movies…" />
        </form>

        <div class="filter-row">
            <div class="filter-group">
                <span class="filter-label">Sort</span>
                <div class="chip-bar">
                    <button v-for="opt in SORT_OPTIONS" :key="opt.value" class="chip"
                        :class="{ active: sort === opt.value }"
                        @click="sort = opt.value; load(true)">{{ opt.label }}</button>
                </div>
            </div>
            <div class="filter-group">
                <span class="filter-label">Votes</span>
                <div class="chip-bar">
                    <button v-for="opt in VOTE_FILTERS" :key="opt.value" class="chip"
                        :class="{ active: minVotes === opt.value }"
                        @click="minVotes = opt.value; load(true)">{{ opt.label }}</button>
                </div>
            </div>
            <div class="filter-group" v-if="genres.length">
                <span class="filter-label">Genre</span>
                <div class="chip-bar">
                    <button class="chip" :class="{ active: genre === null }"
                        @click="genre = null; load(true)">All</button>
                    <button v-for="g in genres" :key="g.id" class="chip"
                        :class="{ active: genre === g.name }"
                        @click="genre = g.name; load(true)">{{ g.name }}</button>
                </div>
            </div>
        </div>

        <p v-if="error" class="msg-error">Error: {{ error }}</p>

        <div v-if="movies.length" class="grid">
            <RouterLink v-for="m in movies" :key="m.id" :to="`/movie/${m.id}`" class="card">
                <div class="card-poster">
                    <img v-if="m.poster_url" :src="m.poster_url" :alt="m.title" />
                    <div v-else class="placeholder"></div>
                    <span v-if="m.is_seen" class="seen-badge">✓</span>
                    <span v-if="m.rating" class="rating-badge">★ {{ m.rating }}</span>
                </div>
                <div class="card-title">
                    {{ m.title }}
                    <span v-if="m.release_year" class="card-year"> {{ m.release_year }}</span>
                </div>
            </RouterLink>
        </div>

        <p v-else-if="!loading" class="msg-empty">No movies found.</p>

        <div class="load-more">
            <button v-if="hasMore" class="btn-more" :disabled="loading" @click="load(false)">
                {{ loading ? 'Loading…' : '… more movies …' }}
            </button>
            <p v-else-if="movies.length" class="msg-end">— end of list —</p>
        </div>
    </div>
</template>

<style scoped>
.list-wrap { padding-top: 24px; }

/* Search */
.search-bar { margin-bottom: 20px; }
.search-bar input {
    width: 100%;
    padding: 14px 20px;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    color: #e5e5e5;
    font-size: 1rem;
    outline: none;
    transition: border-color 0.2s;
}
.search-bar input:focus { border-color: #e50914; }
.search-bar input::placeholder { color: #555; }

/* Filters */
.filter-row { display: flex; flex-direction: column; gap: 12px; margin-bottom: 28px; }

.filter-group { display: flex; align-items: flex-start; gap: 12px; flex-wrap: wrap; }

.filter-label {
    font-size: 0.7rem;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    flex-shrink: 0;
    width: 38px;
    padding-top: 8px;
}

.chip-bar { display: flex; flex-wrap: wrap; gap: 7px; }

.chip {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #888;
    font-size: 0.82rem;
    padding: 7px 16px;
    border-radius: 24px;
    transition: border-color 0.15s, color 0.15s;
}
.chip:hover { border-color: #555; color: #ccc; }
.chip.active { border-color: #e50914; color: #e5e5e5; }

/* Grid */
.grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 14px;
}
@media (min-width: 600px)  { .grid { grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 16px; } }
@media (min-width: 1024px) { .grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; } }
@media (min-width: 1440px) { .grid { grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 24px; } }
@media (min-width: 1920px) { .grid { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 28px; } }

.card { display: flex; flex-direction: column; gap: 8px; }

.card-poster {
    position: relative;
    aspect-ratio: 2 / 3;
    border-radius: 8px;
    overflow: hidden;
    background: #1a1a1a;
    transition: transform 0.2s;
}
.card:hover .card-poster { transform: scale(1.03); }
.card-poster img { width: 100%; height: 100%; object-fit: cover; display: block; }

.placeholder {
    width: 100%; height: 100%;
    background:
        linear-gradient(to bottom right, transparent calc(50% - 1px), #2e2e2e calc(50% - 1px), #2e2e2e calc(50% + 1px), transparent calc(50% + 1px)),
        linear-gradient(to bottom left,  transparent calc(50% - 1px), #2e2e2e calc(50% - 1px), #2e2e2e calc(50% + 1px), transparent calc(50% + 1px)),
        #181818;
}

.seen-badge {
    position: absolute; top: 8px; left: 8px;
    background: rgba(0,0,0,0.8); color: #4caf50;
    font-size: 0.75rem; font-weight: 700;
    padding: 3px 8px; border-radius: 5px; border: 1px solid #4caf50;
}

.rating-badge {
    position: absolute; top: 8px; right: 8px;
    background: rgba(0,0,0,0.8); color: #f5c518;
    font-size: 0.75rem; font-weight: 700;
    padding: 3px 8px; border-radius: 5px;
}

.card-title {
    font-size: 0.88rem;
    line-height: 1.35;
    color: #ccc;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.card-year { color: #555; }

/* Load more */
.load-more { margin-top: 48px; text-align: center; }

.btn-more {
    background: none;
    border: 1px solid #333;
    color: #888;
    padding: 14px 48px;
    border-radius: 8px;
    font-size: 0.95rem;
    transition: border-color 0.2s, color 0.2s;
}
.btn-more:hover:not(:disabled) { border-color: #666; color: #ccc; }
.btn-more:disabled { opacity: 0.5; }

.msg-error { color: #e50914; padding: 16px 0; }
.msg-empty, .msg-end { color: #444; font-size: 0.9rem; }
</style>
