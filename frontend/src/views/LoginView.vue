<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../auth.js'

const router = useRouter()
const { setAuth } = useAuth()

const mode = ref('login')   // 'login' | 'register'
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
    if (!username.value.trim() || !password.value.trim()) {
        error.value = 'Please fill in all fields.'
        return
    }
    loading.value = true
    error.value = ''
    try {
        const endpoint = mode.value === 'login' ? '/api/auth/login' : '/api/auth/register'
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username.value.trim(), password: password.value }),
        })
        const data = await res.json()
        if (!res.ok) {
            error.value = data.detail || 'Something went wrong.'
            return
        }
        if (mode.value === 'login') {
            setAuth(data.token, data.user)
        } else {
            // After register, auto-login
            const loginRes = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username.value.trim(), password: password.value }),
            })
            const loginData = await loginRes.json()
            setAuth(loginData.token, loginData.user)
        }
        router.push('/')
    } catch {
        error.value = 'Network error.'
    } finally {
        loading.value = false
    }
}
</script>

<template>
    <div class="login-wrap">
        <div class="login-card">
            <h1 class="brand">DEBRIDFLIX DB</h1>
            <p class="subtitle">Private film portal</p>

            <div class="tab-row">
                <button class="tab" :class="{ active: mode === 'login' }" @click="mode = 'login'; error = ''">Log in</button>
                <button class="tab" :class="{ active: mode === 'register' }" @click="mode = 'register'; error = ''">Register</button>
            </div>

            <form @submit.prevent="submit">
                <input v-model="username" type="text" placeholder="Username" autocomplete="username" />
                <input v-model="password" type="password" placeholder="Password" autocomplete="current-password" />
                <p v-if="error" class="error-msg">{{ error }}</p>
                <button type="submit" class="btn-submit" :disabled="loading">
                    {{ loading ? '…' : mode === 'login' ? 'Log in' : 'Create account' }}
                </button>
            </form>
        </div>
    </div>
</template>

<style scoped>
.login-wrap {
    min-height: calc(100vh - 80px);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px 16px;
}

.login-card {
    background: #141414;
    border: 1px solid #222;
    border-radius: 14px;
    padding: 48px 40px;
    width: 100%;
    max-width: 420px;
    text-align: center;
}

.brand {
    margin: 0 0 8px;
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: 0.1em;
    color: #e50914;
}

.subtitle {
    color: #555;
    font-size: 0.85rem;
    margin: 0 0 32px;
}

.tab-row {
    display: flex;
    gap: 0;
    margin-bottom: 28px;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    overflow: hidden;
}

.tab {
    flex: 1;
    background: none;
    border: none;
    color: #666;
    font-size: 0.95rem;
    padding: 12px;
    transition: background 0.15s, color 0.15s;
}
.tab.active { background: #222; color: #e5e5e5; }

form { display: flex; flex-direction: column; gap: 14px; }

input {
    width: 100%;
    padding: 14px 16px;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    color: #e5e5e5;
    font-size: 1rem;
    outline: none;
    transition: border-color 0.2s;
}
input:focus { border-color: #e50914; }

.error-msg { color: #e50914; font-size: 0.85rem; margin: 0; text-align: left; }

.btn-submit {
    background: #e50914;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 15px;
    font-size: 1rem;
    font-weight: 600;
    transition: opacity 0.15s;
    margin-top: 4px;
}
.btn-submit:hover:not(:disabled) { opacity: 0.85; }
.btn-submit:disabled { opacity: 0.5; }
</style>
