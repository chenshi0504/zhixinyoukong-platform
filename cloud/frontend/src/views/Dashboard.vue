<template>
  <div>
    <h2 class="page-title">管理概览</h2>
    <p class="page-subtitle">平台运行状态一览</p>
    <el-alert
      v-if="pendingPasswordRequests > 0"
      class="pending-alert"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #title>
        当前有 {{ pendingPasswordRequests }} 条密码修改申请待审批。
        <el-button link type="primary" @click="goPasswordRequests">立即处理</el-button>
      </template>
    </el-alert>
    <el-row :gutter="20" style="margin-bottom:24px">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <div class="stat-card" :class="{ clickable: card.to }" @click="card.to && router.push(card.to)">
          <div class="stat-icon">{{ card.icon }}</div>
          <div class="stat-value">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/client'

const router = useRouter()
const pendingPasswordRequests = ref(0)
const cards = ref([
  { label: '总机构数', value: '-', icon: '🏢' },
  { label: '总 License 数', value: '-', icon: '🔑' },
  { label: '活跃 License', value: '-', icon: '✅' },
  { label: '总用户数', value: '-', icon: '👥' },
  { label: '待审密码申请', value: '-', icon: '🔐', to: '/password-requests' },
])

function goPasswordRequests() {
  router.push('/password-requests')
}

onMounted(async () => {
  try {
    const { data } = await api.get('/api/cloud/admin/dashboard')
    pendingPasswordRequests.value = data.pending_password_requests ?? 0
    cards.value = [
      { label: '总机构数', value: data.total_organizations, icon: '🏢' },
      { label: '总 License 数', value: data.total_licenses, icon: '🔑' },
      { label: '活跃 License', value: data.active_licenses, icon: '✅' },
      { label: '总用户数', value: data.total_users ?? '-', icon: '👥' },
      { label: '待审密码申请', value: data.pending_password_requests ?? 0, icon: '🔐', to: '/password-requests' },
    ]
  } catch { /* ignore */ }
})
</script>

<style scoped>
.page-title { color: #2C5AA0; font-size: 1.8rem; font-weight: 600; margin-bottom: 8px; }
.page-subtitle { color: #666; font-size: 1rem; margin-bottom: 24px; }
.pending-alert { margin-bottom: 18px; }
.stat-card {
  background: white; border-radius: 12px; padding: 24px; text-align: center;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08); transition: all 0.3s ease;
  border: 2px solid transparent; cursor: default;
}
.stat-card:hover {
  transform: translateY(-4px); box-shadow: 0 8px 30px rgba(0,0,0,0.12);
  border-color: #2C5AA0;
}
.stat-card.clickable { cursor: pointer; }
.stat-icon { font-size: 36px; margin-bottom: 8px; }
.stat-value { font-size: 32px; font-weight: 700; color: #2C5AA0; }
.stat-label { font-size: 14px; color: #666; margin-top: 8px; }
</style>
