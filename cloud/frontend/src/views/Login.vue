<template>
  <div class="login-page">
    <section class="product-pane">
      <header class="brand-row">
        <div class="brand-mark">ZXYK</div>
        <div>
          <strong>智信优控</strong>
          <span>云端管理平台</span>
        </div>
      </header>

      <div class="hero-copy">
        <p class="eyebrow">Cloud Management Console</p>
        <h1>面向车路云一体化实验平台的教学与运维管理端</h1>
        <p>
          云端平台聚焦机构、教师、班级、任务、报告、License 与版本发布管理，
          为本地实验平台提供统一的组织管理、成果归档和运行统计能力。
        </p>
      </div>

      <div class="capability-grid" aria-label="平台能力">
        <div>
          <span>01</span>
          <strong>机构与账号</strong>
          <p>统一维护学校、机构管理员和教师账号，支撑跨电脑访问。</p>
        </div>
        <div>
          <span>02</span>
          <strong>教学组织</strong>
          <p>教师维护班级、发布任务、查看提交记录和批阅结果。</p>
        </div>
        <div>
          <span>03</span>
          <strong>平台运维</strong>
          <p>管理员跟踪 License、版本更新、平台使用趋势和运行状态。</p>
        </div>
      </div>
    </section>

    <section class="auth-pane">
      <div class="auth-card">
        <button v-if="mode !== 'select'" class="text-btn back-btn" type="button" @click="resetToSelect">
          返回入口
        </button>

        <div v-if="mode === 'select'">
          <p class="card-kicker">选择管理入口</p>
          <h2>登录云端管理平台</h2>
          <div class="role-grid">
            <button class="role-card" type="button" @click="openLogin('admin')">
              <span class="role-icon"><OfficeBuilding /></span>
              <strong>管理员入口</strong>
              <small>机构、账号、License、统计和版本管理</small>
            </button>
            <button class="role-card" type="button" @click="openLogin('teacher')">
              <span class="role-icon"><User /></span>
              <strong>教师入口</strong>
              <small>班级、任务、报告批阅和教学统计</small>
            </button>
          </div>
          <button class="register-link" type="button" @click="openRegister">
            教师注册
            <span><ArrowRight /></span>
          </button>
        </div>

        <div v-else-if="mode === 'login'">
          <p class="card-kicker">{{ roleLabel }}</p>
          <h2>{{ roleLabel }}登录</h2>
          <form @submit.prevent="handleLogin">
            <label>
              <span>用户名</span>
              <input v-model.trim="form.username" type="text" required autocomplete="username" />
            </label>
            <label>
              <span>密码</span>
              <input v-model="form.password" type="password" required autocomplete="current-password" />
            </label>
            <button type="submit" class="primary-btn" :disabled="loading">
              {{ loading ? '登录中...' : '登录管理端' }}
            </button>
          </form>
          <button v-if="selectedRole === 'teacher'" class="text-btn full-link" type="button" @click="openRegister">
            没有教师账号，前往注册
          </button>
        </div>

        <div v-else-if="mode === 'register'">
          <p class="card-kicker">Teacher Registration</p>
          <h2>教师注册</h2>
          <form @submit.prevent="handleRegister">
            <label>
              <span>姓名</span>
              <input v-model.trim="regForm.real_name" type="text" required />
            </label>
            <label>
              <span>所属机构</span>
              <select v-model.number="regForm.org_id" required :disabled="orgLoading">
                <option value="" disabled>{{ orgLoading ? '机构加载中...' : '请选择已创建机构' }}</option>
                <option v-for="org in orgs" :key="org.id" :value="org.id">{{ org.name }}</option>
              </select>
              <small class="field-help">机构由管理员创建，教师注册时只能选择已有机构。</small>
            </label>
            <label>
              <span>密码</span>
              <input v-model="regForm.password" type="password" required placeholder="至少6位" />
            </label>
            <label>
              <span>确认密码</span>
              <input v-model="regForm.confirmPassword" type="password" required />
            </label>
            <button type="submit" class="primary-btn" :disabled="regLoading">
              {{ regLoading ? '注册中...' : '提交注册' }}
            </button>
          </form>
        </div>

        <div v-else-if="mode === 'register-success'">
          <p class="card-kicker">Registration Complete</p>
          <h2>注册成功</h2>
          <div class="info-box">
            <div><span>账号</span><strong>{{ regResult.username }}</strong></div>
            <div><span>姓名</span><strong>{{ regResult.real_name }}</strong></div>
            <div><span>机构</span><strong>{{ regResult.org_name }}</strong></div>
          </div>
          <button class="primary-btn" type="button" @click="goLoginAfterRegister">使用该账号登录</button>
        </div>
      </div>

      <div class="status-bar">
        <span class="status-dot" :class="statusType"></span>
        <span :class="statusType">{{ statusMsg }}</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { OfficeBuilding, User, ArrowRight } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import api from '@/api/client'

const router = useRouter()
const auth = useAuthStore()

const mode = ref('select')
const selectedRole = ref('')
const loading = ref(false)
const regLoading = ref(false)
const orgLoading = ref(false)
const statusMsg = ref('')
const statusType = ref('')
const backendOnline = ref(false)
const orgs = ref([])
const regResult = ref({})

const form = reactive({ username: '', password: '' })
const regForm = reactive({ real_name: '', org_id: '', password: '', confirmPassword: '' })

const roleLabel = computed(() => ({ admin: '管理员', teacher: '教师' }[selectedRole.value] || '管理端用户'))

onMounted(async () => {
  await checkBackend()
  await loadOrgs()
})

function resetToSelect() {
  mode.value = 'select'
  selectedRole.value = ''
}

function openLogin(role) {
  selectedRole.value = role
  mode.value = 'login'
}

function openRegister() {
  selectedRole.value = 'teacher'
  Object.assign(regForm, { real_name: '', org_id: '', password: '', confirmPassword: '' })
  mode.value = 'register'
  loadOrgs()
}

async function checkBackend() {
  try {
    await api.get('/api/cloud/health')
    statusMsg.value = '后端服务已连接'
    statusType.value = 'ok'
    backendOnline.value = true
  } catch {
    statusMsg.value = '服务器后端服务暂不可用，请检查服务器运行状态'
    statusType.value = 'err'
    backendOnline.value = false
  }
}

async function loadOrgs() {
  orgLoading.value = true
  try {
    const { data } = await api.get('/api/cloud/public/orgs')
    orgs.value = data
  } catch {
    orgs.value = []
    statusMsg.value = '机构列表加载失败，请检查服务器后端服务'
    statusType.value = 'err'
  } finally {
    orgLoading.value = false
  }
}

async function handleLogin() {
  if (!backendOnline.value) {
    statusMsg.value = '服务器后端服务暂不可用，无法登录'
    statusType.value = 'err'
    return
  }
  loading.value = true
  statusMsg.value = '登录中...'
  statusType.value = ''
  try {
    const data = await auth.login(form.username, form.password)
    const role = data.user.role
    if (selectedRole.value === 'teacher' && role !== 'teacher') throw new Error('该账号不是教师角色')
    if (selectedRole.value === 'admin' && !['super_admin', 'org_admin'].includes(role)) throw new Error('该账号不是管理员角色')
    if (!['super_admin', 'org_admin', 'teacher'].includes(role)) throw new Error('该账号不属于云端管理端角色')
    localStorage.setItem('login_mode', selectedRole.value)
    statusMsg.value = '登录成功，正在跳转...'
    statusType.value = 'ok'
    setTimeout(() => {
      if (role === 'teacher') router.push('/teacher/classes')
      else router.push('/dashboard')
    }, 300)
  } catch (e) {
    auth.clearAuth()
    statusMsg.value = e.response?.data?.detail || e.message || '用户名或密码错误'
    statusType.value = 'err'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!regForm.real_name || !regForm.org_id || !regForm.password) {
    statusMsg.value = '请填写所有必填字段'
    statusType.value = 'err'
    return
  }
  if (regForm.password.length < 6) {
    statusMsg.value = '密码长度不能少于6位'
    statusType.value = 'err'
    return
  }
  if (regForm.password !== regForm.confirmPassword) {
    statusMsg.value = '两次密码输入不一致'
    statusType.value = 'err'
    return
  }

  regLoading.value = true
  statusMsg.value = '注册中...'
  statusType.value = ''
  try {
    const { data } = await api.post('/api/cloud/auth/register', {
      real_name: regForm.real_name,
      org_id: regForm.org_id,
      password: regForm.password,
    })
    regResult.value = data
    mode.value = 'register-success'
  } catch (e) {
    statusMsg.value = e.response?.data?.detail || '注册失败'
    statusType.value = 'err'
  } finally {
    regLoading.value = false
  }
}

function goLoginAfterRegister() {
  selectedRole.value = 'teacher'
  form.username = regResult.value.username || ''
  mode.value = 'login'
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(520px, 1.05fr) minmax(430px, 0.95fr);
  font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
  background: #f4f7fb;
  color: #172033;
}
.product-pane {
  position: relative;
  min-height: 100vh;
  padding: 46px 58px;
  color: #fff;
  background:
    linear-gradient(118deg, rgba(9, 22, 42, 0.92), rgba(19, 59, 86, 0.72)),
    url('/bg.jpg') center/cover;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.brand-row {
  display: flex;
  align-items: center;
  gap: 14px;
}
.brand-mark {
  width: 46px;
  height: 46px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.24);
  font-weight: 800;
}
.brand-row strong,
.brand-row span {
  display: block;
}
.brand-row strong { font-size: 18px; }
.brand-row span { margin-top: 2px; color: rgba(255, 255, 255, 0.72); font-size: 13px; }
.hero-copy { width: min(760px, 100%); padding: 64px 0; }
.eyebrow {
  margin: 0 0 16px;
  color: #f2b94b;
  font-weight: 800;
  font-size: 13px;
  text-transform: uppercase;
}
.hero-copy h1 {
  margin: 0;
  font-size: 54px;
  line-height: 1.14;
  letter-spacing: 0;
}
.hero-copy p:last-child {
  width: min(700px, 100%);
  margin: 24px 0 0;
  color: rgba(255, 255, 255, 0.82);
  font-size: 17px;
  line-height: 1.8;
}
.capability-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.capability-grid div {
  min-height: 150px;
  padding: 18px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.18);
}
.capability-grid span {
  color: #f2b94b;
  font-size: 12px;
  font-weight: 800;
}
.capability-grid strong {
  display: block;
  margin-top: 12px;
  font-size: 16px;
}
.capability-grid p {
  margin: 8px 0 0;
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.65;
  font-size: 13px;
}
.auth-pane {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 42px;
}
.auth-card {
  position: relative;
  width: min(480px, 100%);
  padding: 38px;
  background: #fff;
  border: 1px solid #dce5ef;
  border-radius: 8px;
  box-shadow: 0 22px 54px rgba(24, 42, 68, 0.14);
}
.card-kicker {
  margin: 0 0 8px;
  color: #1f7a67;
  font-size: 13px;
  font-weight: 800;
}
.auth-card h2 {
  margin: 0 0 24px;
  color: #172033;
  font-size: 28px;
}
.role-grid {
  display: grid;
  gap: 14px;
}
.role-card {
  min-height: 104px;
  display: grid;
  grid-template-columns: 44px 1fr;
  grid-template-rows: auto auto;
  column-gap: 14px;
  text-align: left;
  padding: 18px;
  border: 1px solid #dce5ef;
  border-radius: 8px;
  background: #f8fbff;
  cursor: pointer;
}
.role-card:hover {
  border-color: #2864a8;
  background: #f1f7ff;
}
.role-icon {
  grid-row: 1 / 3;
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  color: #2864a8;
  background: #e7f0fa;
  border-radius: 8px;
}
.role-icon svg,
.register-link svg {
  width: 18px;
  height: 18px;
}
.role-card strong {
  color: #172033;
  font-size: 17px;
}
.role-card small {
  margin-top: 5px;
  color: #657487;
  line-height: 1.55;
}
form {
  display: grid;
  gap: 16px;
}
label {
  display: grid;
  gap: 7px;
  color: #526174;
  font-size: 14px;
}
.field-help {
  color: #6e7c8f;
  font-size: 12px;
  line-height: 1.5;
}
input,
select {
  height: 46px;
  padding: 0 12px;
  border: 1px solid #cbd7e4;
  border-radius: 8px;
  font: inherit;
  background: #fff;
}
input:focus,
select:focus {
  outline: none;
  border-color: #2864a8;
  box-shadow: 0 0 0 3px rgba(40, 100, 168, 0.12);
}
.primary-btn {
  height: 48px;
  border: none;
  border-radius: 8px;
  background: #2864a8;
  color: #fff;
  font-weight: 800;
  cursor: pointer;
}
.primary-btn:hover { background: #1f558f; }
.primary-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.text-btn,
.register-link {
  border: none;
  background: transparent;
  color: #2864a8;
  cursor: pointer;
  font: inherit;
}
.back-btn {
  position: absolute;
  top: 18px;
  right: 22px;
  font-size: 13px;
}
.full-link,
.register-link {
  margin-top: 18px;
}
.register-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
}
.info-box {
  display: grid;
  gap: 10px;
  margin-bottom: 22px;
}
.info-box div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 13px;
  background: #f4f8fc;
  border-radius: 8px;
}
.info-box span { color: #617186; }
.status-bar {
  width: min(480px, 100%);
  margin-top: 14px;
  color: #778398;
  font-size: 13px;
}
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #b6c2d0;
  margin-right: 6px;
}
.ok { color: #238348; }
.status-dot.ok { background: #238348; }
.err { color: #c0392b; }
.status-dot.err { background: #c0392b; }
@media (max-width: 980px) {
  .login-page { grid-template-columns: 1fr; }
  .product-pane { min-height: auto; gap: 42px; }
  .auth-pane { min-height: auto; }
}
@media (max-width: 640px) {
  .product-pane,
  .auth-pane { padding: 30px 20px; }
  .hero-copy h1 { font-size: 38px; }
  .capability-grid { grid-template-columns: 1fr; }
  .auth-card { padding: 30px 22px; }
}
</style>
