<template>
  <div class="password-page">
    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <el-tab-pane label="密码修改申请" name="requests">
        <div class="toolbar">
          <el-select v-model="statusFilter" style="width: 160px" @change="loadRequests">
            <el-option label="待审批" value="pending" />
            <el-option label="已通过" value="approved" />
            <el-option label="已拒绝" value="rejected" />
            <el-option label="全部" value="all" />
          </el-select>
          <el-button @click="loadRequests">刷新</el-button>
        </div>
        <el-table :data="requests" v-loading="requestLoading" stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="username" label="账号" min-width="130" />
          <el-table-column prop="real_name" label="姓名" min-width="110" />
          <el-table-column prop="role" label="角色" width="100" />
          <el-table-column prop="organization_name" label="机构" min-width="140" />
          <el-table-column prop="reason" label="申请说明" min-width="180" show-overflow-tooltip />
          <el-table-column prop="requested_at" label="申请时间" min-width="170">
            <template #default="{ row }">{{ formatTime(row.requested_at) }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170" fixed="right">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button text type="success" size="small" @click="review(row, 'approve')">通过</el-button>
                <el-button text type="danger" size="small" @click="review(row, 'reject')">拒绝</el-button>
              </template>
              <span v-else class="muted">已处理</span>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          style="margin-top:16px;justify-content:flex-end"
          v-model:current-page="requestPage"
          :page-size="pageSize"
          :total="requestTotal"
          layout="total, prev, pager, next"
          @current-change="loadRequests"
        />
      </el-tab-pane>

      <el-tab-pane label="账号密码审计" name="audit">
        <div class="toolbar">
          <el-select v-model="roleFilter" clearable placeholder="全部角色" style="width: 160px" @change="loadAudit">
            <el-option label="教师" value="teacher" />
            <el-option label="学生" value="student" />
            <el-option label="机构管理员" value="org_admin" />
          </el-select>
          <el-alert class="audit-note" type="info" :closable="false" show-icon>
            <template #title>系统只保存 bcrypt 哈希和修改记录，不保存或展示明文密码；需要发放新密码时请使用“用户管理”里的重置密码。</template>
          </el-alert>
          <el-button @click="loadAudit">刷新</el-button>
        </div>
        <el-table :data="auditItems" v-loading="auditLoading" stripe>
          <el-table-column prop="user_id" label="用户ID" width="80" />
          <el-table-column prop="username" label="账号" min-width="130" />
          <el-table-column prop="real_name" label="姓名" min-width="110" />
          <el-table-column prop="role" label="角色" width="110" />
          <el-table-column prop="organization_name" label="机构" min-width="140" />
          <el-table-column prop="password_history_count" label="历史记录数" width="120" />
          <el-table-column prop="pending_request_count" label="待审申请" width="110" />
          <el-table-column prop="last_password_changed_at" label="最近修改时间" min-width="170">
            <template #default="{ row }">{{ formatTime(row.last_password_changed_at) || '暂无记录' }}</template>
          </el-table-column>
          <el-table-column prop="password_storage" label="密码存储" min-width="210" />
        </el-table>
        <el-pagination
          style="margin-top:16px;justify-content:flex-end"
          v-model:current-page="auditPage"
          :page-size="pageSize"
          :total="auditTotal"
          layout="total, prev, pager, next"
          @current-change="loadAudit"
        />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="reviewDialog" :title="reviewAction === 'approve' ? '通过密码修改申请' : '拒绝密码修改申请'" width="460px">
      <div v-if="reviewRow" class="review-user">
        {{ reviewRow.real_name || reviewRow.username }}（{{ reviewRow.username }}）
      </div>
      <el-input v-model="reviewNote" type="textarea" :rows="3" placeholder="审批备注，可选" />
      <template #footer>
        <el-button @click="reviewDialog = false">取消</el-button>
        <el-button :type="reviewAction === 'approve' ? 'success' : 'danger'" :loading="reviewLoading" @click="submitReview">
          {{ reviewAction === 'approve' ? '确认通过' : '确认拒绝' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api/client'

const activeTab = ref('requests')
const statusFilter = ref('pending')
const roleFilter = ref('')
const pageSize = 20

const requestLoading = ref(false)
const requests = ref([])
const requestPage = ref(1)
const requestTotal = ref(0)

const auditLoading = ref(false)
const auditItems = ref([])
const auditPage = ref(1)
const auditTotal = ref(0)

const reviewDialog = ref(false)
const reviewLoading = ref(false)
const reviewAction = ref('approve')
const reviewRow = ref(null)
const reviewNote = ref('')

function formatTime(value) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN')
}

function statusLabel(value) {
  return { pending: '待审批', approved: '已通过', rejected: '已拒绝' }[value] || value
}

function statusType(value) {
  return { pending: 'warning', approved: 'success', rejected: 'danger' }[value] || 'info'
}

async function loadRequests() {
  requestLoading.value = true
  try {
    const { data } = await api.get('/api/cloud/password-requests', {
      params: { page: requestPage.value, page_size: pageSize, status: statusFilter.value },
    })
    requests.value = data.items
    requestTotal.value = data.total
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载申请失败')
  } finally {
    requestLoading.value = false
  }
}

async function loadAudit() {
  auditLoading.value = true
  try {
    const params = { page: auditPage.value, page_size: pageSize }
    if (roleFilter.value) params.role = roleFilter.value
    const { data } = await api.get('/api/cloud/password-requests/account-audit', { params })
    auditItems.value = data.items
    auditTotal.value = data.total
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载账号审计失败')
  } finally {
    auditLoading.value = false
  }
}

function handleTabChange(name) {
  if (name === 'audit') loadAudit()
  else loadRequests()
}

function review(row, action) {
  reviewRow.value = row
  reviewAction.value = action
  reviewNote.value = ''
  reviewDialog.value = true
}

async function submitReview() {
  if (!reviewRow.value) return
  reviewLoading.value = true
  try {
    await api.post(`/api/cloud/password-requests/${reviewRow.value.id}/${reviewAction.value}`, {
      admin_note: reviewNote.value,
    })
    ElMessage.success(reviewAction.value === 'approve' ? '已通过，用户新密码已生效' : '已拒绝申请')
    reviewDialog.value = false
    loadRequests()
    if (activeTab.value === 'audit') loadAudit()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '审批失败')
  } finally {
    reviewLoading.value = false
  }
}

onMounted(loadRequests)
</script>

<style scoped>
.password-page { min-height: 100%; }
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.audit-note { flex: 1; }
.review-user {
  margin-bottom: 12px;
  color: #303133;
  font-weight: 600;
}
.muted { color: #909399; font-size: 13px; }
</style>
