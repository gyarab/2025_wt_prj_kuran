<script setup>
import { ref, onMounted } from 'vue'

const movies = ref([])
const query = ref('')
const loading = ref(false)
const error = ref('')

async function load() {
    loading.value = true
    error.value = ''
    try {
        const params = new URLSearchParams({ limit: '50' })
        if (query.value.trim()) params.set('q', query.value.trim())
        const res = await fetch(`/api/movie?${params}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        movies.value = await res.json()
    } catch (e) {
        error.value = e.message
    } finally {
        loading.value = false
    }
}

onMounted(load)
</script>

<template>
    <h2>Filmy</h2>

    <form class="search" @submit.prevent="load">
        <input v-model="query" type="text" placeholder="Hledat podle názvu…" />
        <button type="submit">Hledat</button>
    </form>

    <p v-if="loading">Načítání…</p>
    <p v-else-if="error" class="error">Chyba: {{ error }}</p>
    <ul v-else-if="movies.length" class="movies">
        <li v-for="m in movies" :key="m.id">
            <RouterLink :to="`/movie/${m.id}`">{{ m.title }}</RouterLink>
            <span v-if="m.release_year" class="dim"> ({{ m.release_year }})</span>
            <span v-if="m.rating" class="dim"> ⭐ {{ m.rating }}</span>
        </li>
    </ul>
    <p v-else>Žádné filmy nenalezeny.</p>
</template>

<style scoped>
.search { margin: 12px 0; display: flex; gap: 8px; }
.search input { flex: 1; padding: 6px; }
.movies { line-height: 1.8; }
.dim { color: #888; }
.error { color: #c0392b; }
</style>
