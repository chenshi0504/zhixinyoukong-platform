<template>
  <div>
    <div style="display:flex;justify-content:flex-end;margin-bottom:16px;gap:8px">
      <el-button type="primary" @click="showCreateDialog">新建用户</el-button>
      <el-upload :show-file-list="false" accept=".csv" :http-request="handleImport">
        <el-button>CSV 导入</el-button>
      </el-upload>
    </div>
    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="real_name" label="姓名" />
      <el-table-column prop="role" label="角色" width="120" />
      <el-table-column prop="org_id" label="机构ID" width="80" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button text type="warning" size="small" @click="showResetDialog(row)">重置密码</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:16px;justify-content:flex-end" v-model:current-page="page"
      :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="loadData" />

    <el-dialog v-model="createDialog" title="新建用户" width="450px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="用户名"><el-input v-model="createForm.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="createForm.password" type="password" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="createForm.real_name" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role">
            <el-option label="机构管理员" value="org_admin" />
            <el-option label="教师" value="teacher" />
          </el-select>
        </el-form-item>
        <el-form-item label="机构ID"><el-input-number v-model="createForm.org_id" :min="1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetDialog" title="重置密码" width="400px">
      <el-form label-width="80px">
        <el-form-item label="新密码"><el-input v-model="newPassword" type="password" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetDialog = false">取消</el-button>
        <el-button type="primary" @click="handleReset">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '@/api/client'
import { ElMessage } from 'element-plus'

const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const createDialog = ref(false)
const resetDialog = ref(false)
const resetUserId = ref(null)
const newPassword = ref('')
const createForm = reactive({ username: '', password: '123456', real_name: '', role: 'teacher', org_id: 1 })

async function loadData() {
  loading.value = true
  try {
    const { data } = await api.get('/api/cloud/users', { params: { page: page.value, page_size: pageSize.value } })
    items.value = data.items; total.value = data.total
  } finally { loading.value = false }
}

function showCreateDialog() { Object.assign(createForm, { username: '', password: '123456', real_name: '', role: 'teacher', org_id: 1 }); createDialog.value = true }
function showResetDialog(row) { resetUserId.value = row.id; newPassword.value = ''; resetDialog.value = true }

async function handleCreate() {
  try {
    await api.post('/api/cloud/users', createForm)
    ElMessage.success('创建成功'); createDialog.value = false; loadData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '创建失败') }
}

async function handleReset() {
  try {
    await api.post(`/api/cloud/users/${resetUserId.value}/reset-password`, { new_password: newPassword.value })
    ElMessage.success('密码已重置'); resetDialog.value = false
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

async function handleImport({ file }) {
  const fd = new FormData(); fd.append('file', file)
  try {
    const { data } = await api.post('/api/cloud/users/import', fd)
    ElMessage.success(`导入完成：创建 ${data.created} 个用户，${data.errors.length} 个错误`)
    loadData()
  } catch (e) { ElMessage.error('导入失败') }
}

onMounted(loadData)
</script>
