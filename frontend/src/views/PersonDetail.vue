<script setup>
import { ref, watch, computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const person = ref(null)
const loading = ref(false)
const error = ref('')

const type = computed(() => route.params.type)

async function load() {
    loading.value = true
    error.value = ''
    person.value = null
    try {
        const res = await fetch(`/api/${type.value}/${route.params.id}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        person.value = await res.json()
        fetchMissingPosters(person.value.movies)
    } catch (e) {
        error.value = e.message
    } finally {
        loading.value = false
    }
}

async function fetchMissingPosters(list) {
    const missing = list.filter(m => !m.poster_url)
    const BATCH = 4
    for (let i = 0; i < missing.length; i += BATCH) {
        await Promise.all(
            missing.slice(i, i + BATCH).map(async (m) => {
                try {
                    const res = await fetch(`/api/movie/${m.id}`)
                    if (!res.ok) return
                    const detail = await res.json()
                    if (detail.poster_url) {
                        const idx = person.value.movies.findIndex(x => x.id === m.id)
                        if (idx !== -1) person.value.movies[idx] = { ...person.value.movies[idx], poster_url: detail.poster_url }
                    }
                } catch { /* silent */ }
            })
        )
    }
}

const typeLabel = computed(() =>
    type.value === 'actor' ? 'Actor' : type.value === 'director' ? 'Director' : 'Writer'
)

watch([() => route.params.type, () => route.params.id], load, { immediate: true })
</script>

<template>
    <div v-if="loading" class="state-msg">Loading…</div>
    <div v-else-if="error" class="state-msg error">Error: {{ error }}</div>

    <div v-else-if="person" class="person">
        <RouterLink to="/" class="back-link">← Back</RouterLink>

        <div class="person-hero">
            <div class="person-photo-wrap">
                <img v-if="person.photo_url" :src="person.photo_url" :alt="person.name" class="person-photo" />
                <div v-else class="person-photo-placeholder">{{ person.name.charAt(0) }}</div>
            </div>
            <div class="person-info">
                <div class="person-header">
                    <h2 class="person-name">{{ person.name }}</h2>
                    <span class="person-type">{{ typeLabel }}</span>
                </div>
                <p v-if="person.bio" class="person-bio">{{ person.bio }}</p>
                <p class="movie-count">{{ person.movies.length }} movie{{ person.movies.length !== 1 ? 's' : '' }}</p>
            </div>
        </div>

        <div class="grid">
            <RouterLink v-for="m in person.movies" :key="m.id" :to="`/movie/${m.id}`" class="card">
                <div class="card-poster">
                    <img v-if="m.poster_url" :src="m.poster_url" :alt="m.title" />
                    <div v-else class="placeholder"></div>
                    <span v-if="m.rating" class="rating-badge">★ {{ m.rating }}</span>
                </div>
                <div class="card-title">
                    {{ m.title }}
                    <span v-if="m.release_year" class="card-year"> {{ m.release_year }}</span>
                </div>
            </RouterLink>
        </div>
    </div>
</template>

<style scoped>
.state-msg { padding: 60px 0; color: #888; font-size: 1.1rem; }
.state-msg.error { color: #e50914; }

.person { padding: 32px 0 80px; }

.back-link {
    display: inline-block; color: #aaa; font-size: 1rem;
    margin-bottom: 36px; transition: color 0.15s;
}
.back-link:hover { color: #fff; }

.person-hero {
    display: flex;
    gap: 32px;
    align-items: flex-start;
    margin-bottom: 48px;
}

.person-photo-wrap {
    flex-shrink: 0;
    width: 120px; height: 120px;
    border-radius: 50%;
    overflow: hidden;
    background: #1a1a1a;
    border: 3px solid #2a2a2a;
}
@media (min-width: 1024px) { .person-photo-wrap { width: 160px; height: 160px; } }
@media (min-width: 1440px) { .person-photo-wrap { width: 200px; height: 200px; } }
@media (min-width: 1920px) { .person-photo-wrap { width: 240px; height: 240px; } }

.person-photo { width: 100%; height: 100%; object-fit: cover; display: block; }

.person-photo-placeholder {
    width: 100%; height: 100%;
    display: flex; align-items: center; justify-content: center;
    font-size: 2.5rem; font-weight: 700; color: #444;
}

.person-info { flex: 1; min-width: 0; }

.person-header { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }

.person-name { margin: 0; font-size: 1.8rem; font-weight: 700; }
@media (min-width: 1440px) { .person-name { font-size: 2.2rem; } }
@media (min-width: 1920px) { .person-name { font-size: 2.6rem; } }

.person-type {
    font-size: 0.78rem; color: #888;
    background: #1a1a1a; border: 1px solid #333;
    padding: 4px 14px; border-radius: 24px;
}

.person-bio {
    font-size: 0.95rem; line-height: 1.7; color: #aaa;
    margin: 0 0 14px;
    max-width: 900px;
    display: -webkit-box;
    -webkit-line-clamp: 5;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
@media (min-width: 1920px) { .person-bio { font-size: 1rem; max-width: 1100px; } }

.movie-count { color: #555; font-size: 0.85rem; margin: 0 0 0; }

/* Grid — same breakpoints as MovieList */
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
    position: relative; aspect-ratio: 2 / 3;
    border-radius: 8px; overflow: hidden; background: #1a1a1a;
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

.rating-badge {
    position: absolute; top: 8px; right: 8px;
    background: rgba(0,0,0,0.8); color: #f5c518;
    font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 5px;
}

.card-title {
    font-size: 0.88rem; line-height: 1.35; color: #ccc;
    overflow: hidden; display: -webkit-box;
    -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.card-year { color: #555; }
</style>
