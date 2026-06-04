<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { useAuth } from './auth.js'

const { isLoggedIn, user, hasRdKey } = useAuth()
</script>

<template>
    <header class="topbar">
        <RouterLink to="/" class="logo">DEBRIDFLIX DB</RouterLink>
        <nav class="nav">
            <template v-if="isLoggedIn">
                <RouterLink to="/profile" class="nav-link">
                    <span class="nav-avatar">{{ user?.username?.charAt(0)?.toUpperCase() }}</span>
                    <span class="nav-username">{{ user?.username }}</span>
                    <span v-if="!hasRdKey" class="nav-warn" title="Set up Real-Debrid">!</span>
                </RouterLink>
            </template>
            <template v-else>
                <RouterLink to="/login" class="nav-login">Log in</RouterLink>
            </template>
        </nav>
    </header>
    <main class="content">
        <RouterView />
    </main>
</template>

<style>
.topbar {
    position: sticky;
    top: 0;
    z-index: 100;
    background: #111;
    border-bottom: 1px solid #222;
    padding: 18px 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.logo {
    font-size: 1.2rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: #e5e5e5;
}

.nav { display: flex; align-items: center; gap: 16px; }

.nav-link {
    display: flex; align-items: center; gap: 8px;
    color: #aaa; font-size: 0.9rem;
    transition: color 0.15s;
}
.nav-link:hover { color: #fff; }

.nav-avatar {
    width: 32px; height: 32px;
    border-radius: 50%; background: #222; border: 1px solid #333;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.85rem; font-weight: 700; color: #ccc;
}

.nav-username { font-size: 0.9rem; }

.nav-warn {
    background: #e50914; color: #fff;
    width: 18px; height: 18px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.7rem; font-weight: 700;
}

.nav-login {
    background: #e50914; color: #fff;
    padding: 8px 20px; border-radius: 6px;
    font-size: 0.9rem; font-weight: 600;
    transition: opacity 0.15s;
}
.nav-login:hover { opacity: 0.85; }

.content { padding: 0 48px 80px; }

@media (max-width: 768px) {
    .topbar { padding: 14px 20px; }
    .content { padding: 0 16px 60px; }
    .nav-username { display: none; }
}
</style>
