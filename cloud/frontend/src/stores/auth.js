import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/client'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const isLoggedIn = computed(() => !!accessToken.value)
  const userRole = computed(() => user.value?.role || '')

  function setTokens(access, refresh) {
    accessToken.value = access
    refreshToken.value = refresh
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  function setUser(u) {
    user.value = u
    localStorage.setItem('user', JSON.stringify(u))
  }

  async function login(username, password) {
    const { data } = await api.post('/api/cloud/auth/login', { username, password })
    setTokens(data.access_token, data.refresh_token)
    setUser(data.user)
    return data
  }

  async function logout() {
    try {
      await api.post('/api/cloud/auth/logout', { refresh_token: refreshToken.value })
    } catch { /* ignore */ }
    clearAuth()
  }

  async function refresh() {
    const { data } = await api.post('/api/cloud/auth/refresh', {
      refresh_token: refreshToken.value,
    })
    accessToken.value = data.access_token
    localStorage.setItem('access_token', data.access_token)
    return data.access_token
  }

  async function fetchCurrentUser() {
    try {
      const { data } = await api.get('/api/cloud/auth/me')
      setUser(data)
      return data
    } catch {
      return user.value
    }
  }

  function clearAuth() {
    accessToken.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
  }

  return {
    accessToken, refreshToken, user,
    isLoggedIn, userRole,
    login, logout, refresh, fetchCurrentUser, clearAuth,
  }
})
