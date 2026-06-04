import { ref, computed } from 'vue'

const TOKEN_KEY = 'debridflix_token'
const USER_KEY  = 'debridflix_user'

function loadStoredToken() {
    const stored = localStorage.getItem(TOKEN_KEY)
    // Guard against a literal "undefined"/"null" string sneaking in — those are
    // truthy and would otherwise fake a logged-in state with a broken token.
    return stored && stored !== 'undefined' && stored !== 'null' ? stored : null
}

function loadStoredUser() {
    try {
        return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
    } catch {
        // Corrupted value (e.g. the literal string "undefined") would crash the
        // whole app on startup — reset it instead.
        localStorage.removeItem(USER_KEY)
        return null
    }
}

const token = ref(loadStoredToken())
const user  = ref(loadStoredUser())

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
