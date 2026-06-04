<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../auth.js'

const router = useRouter()
const { user, isLoggedIn, hasRdKey, authFetch, clearAuth, setAuth } = useAuth()

const rdKey = ref('')
const saving = ref(false)
const saveMsg = ref('')
const saveError = ref('')

async function saveRdKey() {
    saving.value = true
    saveMsg.value = ''
    saveError.value = ''
    try {
        const res = await authFetch('/api/profile', {
            method: 'PUT',
            body: JSON.stringify({ rd_api_key: rdKey.value.trim() }),
        })
        const data = await res.json()
        if (!res.ok) {
            saveError.value = data.detail || 'Failed to save.'
            return
        }
        // Update cached user
        setAuth(localStorage.getItem('debridflix_token'), { ...user.value, has_rd_key: data.has_rd_key })
        saveMsg.value = data.has_rd_key ? 'Real-Debrid key saved and verified.' : 'Key removed.'
        rdKey.value = ''
    } catch {
        saveError.value = 'Network error.'
    } finally {
        saving.value = false
    }
}

async function logout() {
    clearAuth()
    router.push('/')
}

onMounted(() => {
    if (!isLoggedIn.value) router.push('/login')
})
</script>

<template>
    <div class="profile-wrap">
        <RouterLink to="/" class="back-link">← Back</RouterLink>

        <div class="profile-card">
            <div class="avatar">{{ user?.username?.charAt(0)?.toUpperCase() }}</div>
            <h2 class="username">{{ user?.username }}</h2>

            <div class="section">
                <h3 class="section-title">Real-Debrid</h3>

                <div class="rd-status" :class="hasRdKey ? 'connected' : 'disconnected'">
                    <span class="rd-dot"></span>
                    {{ hasRdKey ? 'Connected' : 'Not connected' }}
                </div>

                <p class="hint">
                    Get your API key at
                    <a href="https://real-debrid.com/apitoken" target="_blank" rel="noopener" class="ext-link">
                        real-debrid.com/apitoken ↗
                    </a>
                </p>

                <form @submit.prevent="saveRdKey" class="key-form">
                    <input
                        v-model="rdKey"
                        type="password"
                        :placeholder="hasRdKey ? 'Enter new key to replace…' : 'Paste your API key…'"
                    />
                    <button type="submit" class="btn-save" :disabled="saving || !rdKey.trim()">
                        {{ saving ? '…' : 'Save & verify' }}
                    </button>
                </form>

                <button v-if="hasRdKey" class="btn-remove" @click="rdKey = ''; saveRdKey()">
                    Remove key
                </button>

                <p v-if="saveMsg" class="msg-ok">{{ saveMsg }}</p>
                <p v-if="saveError" class="msg-err">{{ saveError }}</p>
            </div>

            <button class="btn-logout" @click="logout">Log out</button>
        </div>
    </div>
</template>

<style scoped>
.profile-wrap {
    padding-top: 32px;
    max-width: 500px;
}

.back-link {
    display: inline-block; color: #aaa; font-size: 1rem;
    margin-bottom: 32px; transition: color 0.15s;
}
.back-link:hover { color: #fff; }

.profile-card {
    background: #141414;
    border: 1px solid #222;
    border-radius: 14px;
    padding: 48px 40px;
    text-align: center;
}

.avatar {
    width: 80px; height: 80px;
    border-radius: 50%;
    background: #222;
    border: 2px solid #333;
    display: flex; align-items: center; justify-content: center;
    font-size: 2rem; font-weight: 700; color: #aaa;
    margin: 0 auto 16px;
}

.username { margin: 0 0 36px; font-size: 1.4rem; font-weight: 700; }

.section { text-align: left; margin-bottom: 32px; }

.section-title {
    font-size: 0.72rem; text-transform: uppercase;
    letter-spacing: 0.1em; color: #555;
    margin: 0 0 14px; font-weight: 600;
}

.rd-status {
    display: flex; align-items: center; gap: 8px;
    font-size: 0.9rem; margin-bottom: 12px;
}
.rd-dot {
    width: 8px; height: 8px; border-radius: 50%;
}
.connected .rd-dot { background: #4caf50; }
.disconnected .rd-dot { background: #555; }
.connected { color: #4caf50; }
.disconnected { color: #666; }

.hint { font-size: 0.82rem; color: #555; margin: 0 0 16px; }

.ext-link { color: #888; border-bottom: 1px solid #333; transition: color 0.15s; }
.ext-link:hover { color: #ccc; }

.key-form { display: flex; gap: 10px; margin-bottom: 10px; }

.key-form input {
    flex: 1;
    padding: 12px 14px;
    background: #1a1a1a; border: 1px solid #2a2a2a;
    border-radius: 8px; color: #e5e5e5; font-size: 0.9rem;
    outline: none; transition: border-color 0.2s;
}
.key-form input:focus { border-color: #e50914; }

.btn-save {
    background: #e50914; color: #fff; border: none;
    border-radius: 8px; padding: 12px 20px;
    font-size: 0.9rem; font-weight: 600;
    white-space: nowrap; transition: opacity 0.15s;
}
.btn-save:disabled { opacity: 0.4; }
.btn-save:hover:not(:disabled) { opacity: 0.85; }

.btn-remove {
    background: none; border: 1px solid #333; color: #666;
    border-radius: 6px; padding: 8px 16px; font-size: 0.82rem;
    transition: border-color 0.15s, color 0.15s;
}
.btn-remove:hover { border-color: #e50914; color: #e50914; }

.msg-ok  { color: #4caf50; font-size: 0.85rem; margin: 10px 0 0; }
.msg-err { color: #e50914; font-size: 0.85rem; margin: 10px 0 0; }

.btn-logout {
    background: none; border: 1px solid #333; color: #666;
    border-radius: 8px; padding: 12px 32px;
    font-size: 0.9rem; transition: border-color 0.15s, color 0.15s;
}
.btn-logout:hover { border-color: #888; color: #ccc; }
</style>
