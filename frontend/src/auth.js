import { ref, computed } from 'vue'

const TOKEN_KEY = 'debridflix_token'
const USER_KEY  = 'debridflix_user'

const token = ref(localStorage.getItem(TOKEN_KEY) || null)
const user  = ref(JSON.parse(localStorage.getItem(USER_KEY) || 'null'))

export function useAuth() {
    const isLoggedIn = computed(() => !!token.value)
    const hasRdKey   = computed(() => user.value?.has_rd_key ?? false)

    function setAuth(newToken, newUser) {
        token.value = newToken
        user.value  = newUser
        localStorage.setItem(TOKEN_KEY, newToken)
        localStorage.setItem(USER_KEY, JSON.stringify(newUser))
    }

    function clearAuth() {
        token.value = null
        user.value  = null
        localStorage.removeItem(TOKEN_KEY)
        localStorage.removeItem(USER_KEY)
    }

    function authFetch(url, options = {}) {
        return fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...(token.value ? { Authorization: `Bearer ${token.value}` } : {}),
                ...(options.headers || {}),
            },
        })
    }

    return { token, user, isLoggedIn, hasRdKey, setAuth, clearAuth, authFetch }
}
