<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const movie = ref(null)
const loading = ref(false)
const error = ref('')

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

const names = (list) => list.map((p) => p.name).join(', ')

watch(() => route.params.id, load, { immediate: true })
</script>

<template>
    <p><RouterLink to="/">← zpět na seznam</RouterLink></p>

    <p v-if="loading">Načítání…</p>
    <p v-else-if="error" class="error">Chyba: {{ error }}</p>

    <div v-else-if="movie">
        <h2>{{ movie.title }} <span v-if="movie.release_year" class="dim">({{ movie.release_year }})</span></h2>
        <p v-if="movie.original_title && movie.original_title !== movie.title" class="dim">
            <em>{{ movie.original_title }}</em>
        </p>

        <table>
            <tr>
                <th>Hodnocení</th>
                <td>{{ movie.rating ?? 'N/A' }} / 10
                    <span v-if="movie.num_votes" class="dim">({{ movie.num_votes.toLocaleString() }} hlasů)</span>
                </td>
            </tr>
            <tr><th>Délka</th><td>{{ movie.duration ?? 'N/A' }} min</td></tr>
            <tr><th>Režie</th><td>{{ movie.directors.length ? names(movie.directors) : 'Neznámá' }}</td></tr>
            <tr><th>Scénář</th><td>{{ movie.writers.length ? names(movie.writers) : '—' }}</td></tr>
            <tr><th>Žánry</th><td>{{ movie.genres.length ? names(movie.genres) : '—' }}</td></tr>
            <tr><th>Obsazení</th><td>{{ movie.actors.length ? names(movie.actors) : '—' }}</td></tr>
        </table>
    </div>
</template>

<style scoped>
.dim { color: #888; }
.error { color: #c0392b; }
table { border-collapse: collapse; margin-top: 12px; }
th { text-align: left; padding: 4px 16px 4px 0; vertical-align: top; width: 110px; }
td { padding: 4px 0; }
</style>
