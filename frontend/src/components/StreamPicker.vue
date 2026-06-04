<script setup>
import { ref, computed, watch } from 'vue'
import { useAuth } from '../auth.js'

const props  = defineProps({ movieId: Number, movieTitle: String })
const emit   = defineEmits(['play', 'close'])
const { authFetch } = useAuth()

// ── State ──────────────────────────────────────────────────────────────
const streams      = ref([])
const loadingList  = ref(false)
const listError    = ref('')

const qualityFilter  = ref('any')
const audioFilter    = ref('any')
const subtitleLang   = ref('none')
const selectedHash   = ref(null)

const subtitles     = ref([])
const loadingSubs   = ref(false)
const selectedSubId = ref(null)

const playing    = ref(false)
const playError  = ref('')

// ── Filters ────────────────────────────────────────────────────────────
const QUALITIES = ['any', '4K', '1080p', '720p', 'SD']
const LANGS     = [
  { code: 'any', label: 'Any'     },
  { code: 'cs',  label: 'Czech'   },
  { code: 'sk',  label: 'Slovak'  },
  { code: 'en',  label: 'English' },
]
const SUB_LANGS = [
  { code: 'none', label: 'None'    },
  { code: 'cs',   label: 'Czech'   },
  { code: 'sk',   label: 'Slovak'  },
  { code: 'en',   label: 'English' },
]

const filtered = computed(() => streams.value.filter(s => {
  if (qualityFilter.value !== 'any' && s.quality !== qualityFilter.value) return false
  if (audioFilter.value  !== 'any' && !s.languages.includes(audioFilter.value)) return false
  return true
}))

// Auto-select best cached stream when filter changes
watch(filtered, (list) => {
  const best = list.find(s => s.cached) || list[0] || null
  selectedHash.value = best?.info_hash ?? null
})

// ── Load streams ───────────────────────────────────────────────────────
async function loadStreams() {
  loadingList.value = true
  listError.value   = ''
  try {
    const res  = await authFetch(`/api/movie/${props.movieId}/streams`)
    const data = await res.json()
    if (!res.ok) { listError.value = data.detail || 'Failed to load streams.'; return }
    streams.value = data
  } catch {
    listError.value = 'Network error.'
  } finally {
    loadingList.value = false
  }
}

// ── Load subtitles ─────────────────────────────────────────────────────
watch(subtitleLang, async (lang) => {
  if (lang === 'none') { subtitles.value = []; selectedSubId.value = null; return }
  loadingSubs.value = true
  try {
    const res  = await fetch(`/api/movie/${props.movieId}/subtitles?language=${lang}`)
    const data = await res.json()
    subtitles.value    = Array.isArray(data) ? data : []
    selectedSubId.value = subtitles.value[0]?.id ?? null
  } catch {
    subtitles.value = []
  } finally {
    loadingSubs.value = false
  }
})

// ── Play ───────────────────────────────────────────────────────────────
async function play() {
  const stream = streams.value.find(s => s.info_hash === selectedHash.value)
  if (!stream) return
  playing.value   = true
  playError.value = ''

  try {
    const res  = await authFetch(`/api/movie/${props.movieId}/stream`, {
      method: 'POST',
      body:   JSON.stringify({ info_hash: stream.info_hash, file_ids: stream.file_ids }),
    })
    const data = await res.json()
    if (!res.ok) { playError.value = data.detail || 'Stream failed.'; return }

    // Resolve subtitle proxy URL if selected
    let subUrl = null
    if (selectedSubId.value) {
      const sub = subtitles.value.find(s => s.id === selectedSubId.value)
      if (sub?.url) {
        subUrl = `/api/movie/${props.movieId}/subtitle-proxy?url=${encodeURIComponent(sub.url)}`
      }
    }

    emit('play', { ...data, quality: stream.quality, subtitleUrl: subUrl, subtitleLang: subUrl ? subtitleLang.value : '' })
  } catch {
    playError.value = 'Network error.'
  } finally {
    playing.value = false
  }
}

loadStreams()
</script>

<template>
  <div class="picker-overlay" @click.self="emit('close')">
    <div class="picker">
      <div class="picker-header">
        <span class="picker-title">Choose stream</span>
        <button class="picker-close" @click="emit('close')">✕</button>
      </div>

      <!-- Quality filter -->
      <div class="filter-row">
        <span class="filter-label">Quality</span>
        <div class="chips">
          <button v-for="q in QUALITIES" :key="q" class="chip"
            :class="{ active: qualityFilter === q }"
            @click="qualityFilter = q; selectedHash = null">
            {{ q === 'any' ? 'Any' : q }}
          </button>
        </div>
      </div>

      <!-- Audio language filter -->
      <div class="filter-row">
        <span class="filter-label">Audio</span>
        <div class="chips">
          <button v-for="l in LANGS" :key="l.code" class="chip"
            :class="{ active: audioFilter === l.code }"
            @click="audioFilter = l.code; selectedHash = null">
            {{ l.label }}
          </button>
        </div>
      </div>

      <!-- Stream list -->
      <div class="stream-list-wrap">
        <p v-if="loadingList" class="hint">Loading streams…</p>
        <p v-else-if="listError" class="hint error">{{ listError }}</p>
        <p v-else-if="!filtered.length" class="hint">No streams match these filters.</p>

        <div v-else class="stream-list">
          <label v-for="s in filtered" :key="s.info_hash"
            class="stream-row" :class="{ selected: selectedHash === s.info_hash, uncached: !s.cached }">
            <input type="radio" :value="s.info_hash" v-model="selectedHash" class="sr-only" />

            <div class="stream-badges">
              <span class="badge-quality">{{ s.quality }}</span>
              <span v-for="lang in s.languages" :key="lang" class="badge-lang">{{ lang.toUpperCase() }}</span>
              <span class="badge-cache" :class="s.cached ? 'cached' : 'not-cached'">
                {{ s.cached ? '⚡ Instant' : '⏳ Slow' }}
              </span>
            </div>
            <span class="stream-title">{{ s.title }}</span>
          </label>
        </div>
      </div>

      <!-- Subtitle selector -->
      <div class="filter-row">
        <span class="filter-label">Subtitles</span>
        <div class="chips">
          <button v-for="l in SUB_LANGS" :key="l.code" class="chip"
            :class="{ active: subtitleLang === l.code }"
            @click="subtitleLang = l.code">
            {{ l.label }}
          </button>
        </div>
      </div>

      <div v-if="subtitleLang !== 'none'" class="sub-list-wrap">
        <p v-if="loadingSubs" class="hint">Loading subtitles…</p>
        <p v-else-if="!subtitles.length" class="hint">No subtitles found.</p>
        <select v-else v-model="selectedSubId" class="sub-select">
          <option v-for="s in subtitles" :key="s.id" :value="s.id">
            {{ s.name }} (↓{{ Number(s.downloads).toLocaleString() }})
          </option>
        </select>
      </div>

      <!-- Play button -->
      <p v-if="playError" class="hint error">{{ playError }}</p>
      <button class="btn-play" :disabled="!selectedHash || playing" @click="play">
        <span v-if="playing" class="spinner"></span>
        <span v-else>▶ Play{{ selectedHash ? '' : ' (select a stream)' }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.picker-overlay {
  position: fixed; inset: 0; z-index: 900;
  background: rgba(0,0,0,0.85);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}

.picker {
  background: #141414;
  border: 1px solid #2a2a2a;
  border-radius: 14px;
  width: 100%; max-width: 680px;
  max-height: 90vh;
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 20px;
  padding: 28px;
}

.picker-header {
  display: flex; align-items: center; justify-content: space-between;
}
.picker-title { font-size: 1.1rem; font-weight: 700; }
.picker-close { background: none; border: none; color: #666; font-size: 1.1rem; padding: 4px 8px; transition: color 0.15s; }
.picker-close:hover { color: #fff; }

.filter-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.filter-label { font-size: 0.75rem; color: #555; text-transform: uppercase; letter-spacing: 0.08em; flex-shrink: 0; width: 68px; }

.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  background: #1a1a1a; border: 1px solid #2a2a2a; color: #777;
  font-size: 0.82rem; padding: 6px 14px; border-radius: 20px;
  transition: border-color 0.15s, color 0.15s;
}
.chip:hover { border-color: #555; color: #ccc; }
.chip.active { border-color: #e50914; color: #e5e5e5; }

/* Stream list */
/* Scroll the list inside its own box. Without this it's a flex item that gets
   squeezed below its content height and the rows spill over the subtitle
   controls and the Play button beneath it. */
.stream-list-wrap { min-height: 80px; max-height: 45vh; overflow-y: auto; }
.hint { color: #555; font-size: 0.85rem; margin: 4px 0; }
.hint.error { color: #e50914; }

.stream-list { display: flex; flex-direction: column; gap: 6px; }

.stream-row {
  display: flex; flex-direction: column; gap: 6px;
  padding: 12px 14px;
  border: 1px solid #222; border-radius: 8px;
  cursor: pointer; transition: border-color 0.15s, background 0.15s;
}
.stream-row:hover { border-color: #444; background: #1a1a1a; }
.stream-row.selected { border-color: #e50914; background: #1a0000; }
.stream-row.uncached { opacity: 0.65; }

.stream-badges { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }

.badge-quality {
  font-size: 0.75rem; font-weight: 700;
  background: #222; color: #e5e5e5;
  padding: 2px 8px; border-radius: 4px;
}
.badge-lang {
  font-size: 0.72rem; font-weight: 700;
  background: #1e3a1e; color: #4caf50;
  border: 1px solid #2a4a2a;
  padding: 2px 7px; border-radius: 4px;
}
.badge-cache {
  font-size: 0.72rem; padding: 2px 8px; border-radius: 4px;
}
.badge-cache.cached     { background: #1e2a1e; color: #4caf50; }
.badge-cache.not-cached { background: #2a2a1e; color: #888; }

.stream-title {
  font-size: 0.8rem; color: #777;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* Subtitle selector */
.sub-list-wrap { margin-top: -8px; }

.sub-select {
  width: 100%;
  background: #1a1a1a; border: 1px solid #2a2a2a;
  color: #ccc; padding: 10px 12px;
  border-radius: 8px; font-size: 0.85rem;
  outline: none;
}
.sub-select:focus { border-color: #e50914; }

/* Play button */
.btn-play {
  background: #e50914; color: #fff; border: none;
  border-radius: 8px; padding: 16px;
  font-size: 1rem; font-weight: 600; width: 100%;
  transition: opacity 0.15s;
}
.btn-play:hover:not(:disabled) { opacity: 0.85; }
.btn-play:disabled { opacity: 0.5; }

.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }

.spinner {
  display: inline-block; width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: spin 0.7s linear infinite; vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
