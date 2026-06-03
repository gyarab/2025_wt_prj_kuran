<script setup>
    import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
    <header>
        <RouterLink to="/">
            <h1>Debridflix DB</h1>
        </RouterLink>
    </header>
    <main>
        <RouterView />
    </main>
</template>