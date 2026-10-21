<template>
  <div class="teacher-layout">
    <header class="header">
      <div class="header-content">
        <h1 class="platform-title">智信优控 · 教师工作台</h1>
        <div class="user-info">
          <span class="welcome-text">欢迎，{{ auth.user?.real_name || auth.user?.username }}（教师）</span>
          <button class="btn-action" @click="showPwdDialog = true">修改密码</button>
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
          <el-menu-item index="/teacher/classes">
            <el-icon><School /></el-icon>
            <span>班级管理</span>
          </el-menu-item>
          <el-menu-item index="/teacher/tasks">
            <el-icon><Document /></el-icon>
            <span>教学任务</span>
          </el-menu-item>
          <el-menu-item index="/teacher/messages">
            <el-icon><Message /></el-icon>
            <span>班级消息</span>
          </el-menu-item>
          <el-menu-item index="/teacher/reports">
            <el-icon><Files /></el-icon>
            <span>实验报告</span>
          </el-menu-item>
          <el-menu-item index="/teacher/self-algorithms">
            <el-icon><Cpu /></el-icon>
            <span>自研算法</span>
          </el-menu-item>
          <el-menu-item index="/teacher/analytics">
            <el-icon><DataAnalysis /></el-icon>
            <span>教学统计</span>
          </el-menu-item>
        </el-menu>
      </aside>
      <main class="main-content">
        <router-view />
      </main>
    </div>

    <!-- 修改密码申请对话框 -->
    <el-dialog v-model="showPwdDialog" title="提交密码修改申请" width="430px" :close-on-click-modal="false">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="教师密码修改需由管理员审批，通过后新密码才会生效。"
        style="margin-bottom: 14px"
      />
      <el-form :model="pwdForm" label-width="80px">
        <el-form-item label="原密码">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少6位" />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password />
        </el-form-item>
        <el-form-item label="申请说明">
          <el-input v-model="pwdForm.reason" type="textarea" :rows="2" placeholder="可选，说明修改原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPwdDialog = false">取消</el-button>
        <el-button type="primary" @click="changePassword" :loading="pwdLoading">提交申请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import api from '@/api/client'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => {
  const parts = route.path.split('/')
  return '/' + parts[1] + '/' + parts[2]
})

const showPwdDialog = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '', reason: '' })

async function changePassword() {
  if (!pwdForm.old_password || !pwdForm.new_password) {
    ElMessage.warning('请填写所有字段'); return
  }
  if (pwdForm.new_password.length < 6) {
    ElMessage.warning('新密码长度不能少于6位'); return
  }
  if (pwdForm.new_password !== pwdForm.confirm) {
    ElMessage.warning('两次密码输入不一致'); return
  }
  pwdLoading.value = true
  try {
    await api.post('/api/cloud/auth/change-password', {
      old_password: pwdForm.old_password,
      new_password: pwdForm.new_password,
      reason: pwdForm.reason,
    })
    ElMessage.success('密码修改申请已提交，等待管理员审批')
    showPwdDialog.value = false
    Object.assign(pwdForm, { old_password: '', new_password: '', confirm: '', reason: '' })
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally { pwdLoading.value = false }
}

async function handleLogout() {
  await auth.logout()
  localStorage.removeItem('login_mode')
  router.push('/login')
}
</script>

<style scoped>
.teacher-layout { height: 100vh; display: flex; flex-direction: column; font-family: 'Microsoft YaHei', sans-serif; }
.header {
  background: linear-gradient(135deg, #2C5AA0 0%, #1e3d72 100%);
  color: white; padding: 0 2rem; height: 60px; flex-shrink: 0;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}
.header-content { display: flex; justify-content: space-between; align-items: center; height: 100%; }
.platform-title { font-size: 1.4rem; font-weight: 600; }
.user-info { display: flex; align-items: center; gap: 1rem; }
.welcome-text { font-size: 0.9rem; }
.btn-action, .btn-logout {
  padding: 6px 16px; background: rgba(255,255,255,0.2); color: white;
  border: 1px solid rgba(255,255,255,0.3); border-radius: 6px;
  cursor: pointer; font-size: 0.85rem; transition: all 0.3s;
}
.btn-action:hover, .btn-logout:hover { background: rgba(255,255,255,0.3); }
.body-wrap { display: flex; flex: 1; overflow: hidden; }
.sidebar { width: 220px; background: #1e2a3a; overflow-y: auto; flex-shrink: 0; }
.sidebar :deep(.el-menu) { border-right: none; }
.sidebar :deep(.el-menu-item) { height: 50px; line-height: 50px; font-size: 14px; }
.sidebar :deep(.el-menu-item.is-active) { background: rgba(44,90,160,0.5) !important; }
.main-content {
  flex: 1; overflow-y: auto; padding: 24px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
}
</style>
