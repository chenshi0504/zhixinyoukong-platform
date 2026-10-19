<template>
  <div class="admin-layout">
    <header class="header">
      <div class="header-content">
        <h1 class="platform-title">智信优控 · 云端管理平台</h1>
        <div class="user-info">
          <span class="welcome-text">欢迎，{{ auth.user?.real_name || auth.user?.username }}（{{ roleLabel }}）</span>
          <button class="btn-logout" @click="handleLogout">退出登录</button>
        </div>
      </div>
    </header>
    <div class="body-wrap">
      <aside class="sidebar">
        <el-menu
          :default-active="activeMenu"
          router
          background-color="#1e2a3a"
          text-color="#a0b4c8"
          active-text-color="#fff"
        >
          <el-menu-item index="/dashboard">
            <el-icon><Odometer /></el-icon>
            <span>概览</span>
          </el-menu-item>
          <el-menu-item index="/orgs">
            <el-icon><OfficeBuilding /></el-icon>
            <span>机构管理</span>
          </el-menu-item>
          <el-menu-item index="/licenses">
            <el-icon><Key /></el-icon>
            <span>License 管理</span>
          </el-menu-item>
          <el-menu-item index="/users">
            <el-icon><User /></el-icon>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/password-requests">
            <el-icon><Key /></el-icon>
            <span class="menu-with-badge">
              密码审批
              <el-badge v-if="pendingPasswordCount > 0" :value="pendingPasswordCount" :max="99" class="menu-badge" />
            </span>
          </el-menu-item>
          <el-menu-item index="/analytics">
            <el-icon><DataAnalysis /></el-icon>
            <span>统计分析</span>
          </el-menu-item>
          <el-menu-item index="/updates">
            <el-icon><Upload /></el-icon>
            <span>版本更新</span>
          </el-menu-item>
        </el-menu>
      </aside>
      <main class="main-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import api from '@/api/client'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const pendingPasswordCount = ref(0)
let pendingTimer = null

const activeMenu = computed(() => '/' + route.path.split('/')[1])

const roleMap = { super_admin: '超级管理员', org_admin: '机构管理员', teacher: '教师' }
const roleLabel = computed(() => roleMap[auth.userRole] || auth.userRole)

async function handleLogout() {
  await auth.logout()
  localStorage.removeItem('login_mode')
  router.push('/login')
}

async function loadPendingPasswordCount() {
  try {
    const { data } = await api.get('/api/cloud/password-requests', {
      params: { page: 1, page_size: 1, status: 'pending' },
    })
    pendingPasswordCount.value = data.total || 0
  } catch {
    pendingPasswordCount.value = 0
  }
}

onMounted(() => {
  loadPendingPasswordCount()
  pendingTimer = window.setInterval(loadPendingPasswordCount, 30000)
})

onBeforeUnmount(() => {
  if (pendingTimer) window.clearInterval(pendingTimer)
})

watch(() => route.path, () => {
  if (route.path === '/password-requests' || route.path === '/dashboard') {
    loadPendingPasswordCount()
  }
})
</script>

<style scoped>
.admin-layout { height: 100vh; display: flex; flex-direction: column; font-family: 'Microsoft YaHei', sans-serif; }
.header {
  background: linear-gradient(135deg, #2C5AA0 0%, #1e3d72 100%);
  color: white; padding: 0 2rem; height: 60px; flex-shrink: 0;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}
.header-content {
  display: flex; justify-content: space-between; align-items: center;
  height: 100%; max-width: 100%;
}
.platform-title { font-size: 1.4rem; font-weight: 600; }
.user-info { display: flex; align-items: center; gap: 1rem; }
.welcome-text { font-size: 0.9rem; }
.btn-logout {
  padding: 6px 16px; background: rgba(255,255,255,0.2); color: white;
  border: 1px solid rgba(255,255,255,0.3); border-radius: 6px;
  cursor: pointer; font-size: 0.85rem; transition: all 0.3s;
}
.btn-logout:hover { background: rgba(255,255,255,0.3); }
.body-wrap { display: flex; flex: 1; overflow: hidden; }
.sidebar {
  width: 220px; background: #1e2a3a; overflow-y: auto; flex-shrink: 0;
}
.sidebar :deep(.el-menu) { border-right: none; }
.sidebar :deep(.el-menu-item) {
  height: 50px; line-height: 50px; font-size: 14px;
}
.sidebar :deep(.el-menu-item.is-active) {
  background: rgba(44,90,160,0.5) !important;
}
.menu-with-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.menu-badge :deep(.el-badge__content) {
  border: none;
  font-size: 11px;
}
.main-content {
  flex: 1; overflow-y: auto; padding: 24px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
}
</style>
