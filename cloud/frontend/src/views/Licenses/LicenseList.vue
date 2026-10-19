<template>
  <div>
    <div style="display:flex;justify-content:flex-end;margin-bottom:16px">
      <el-button type="primary" @click="genDialog = true">生成 License</el-button>
    </div>
    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column label="License Key" width="220">
        <template #default="{ row }">
          <el-text copyable>{{ row.license_key }}</el-text>
        </template>
      </el-table-column>
      <el-table-column prop="license_type" label="类型" width="100" />
      <el-table-column prop="org_id" label="机构ID" width="80" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">{{ row.is_active ? '活跃' : '已吊销' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="machine_id" label="机器码" show-overflow-tooltip />
      <el-table-column prop="expires_at" label="到期时间" width="180" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-popconfirm title="确认吊销？" @confirm="handleRevoke(row.id)" v-if="row.is_active">
            <template #reference><el-button text type="danger" size="small">吊销</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:16px;justify-content:flex-end" v-model:current-page="page"
      :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="loadData" />

    <el-dialog v-model="genDialog" title="生成 License" width="400px">
      <el-form :model="genForm" label-width="80px">
        <el-form-item label="机构 ID"><el-input-number v-model="genForm.org_id" :min="1" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="genForm.license_type">
            <el-option label="试用 (30天)" value="trial" />
            <el-option label="教育 (180天)" value="education" />
            <el-option label="永久" value="permanent" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="genDialog = false">取消</el-button>
        <el-button type="primary" @click="handleGenerate">生成</el-button>
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
const genDialog = ref(false)
const genForm = reactive({ org_id: 1, license_type: 'education' })

async function loadData() {
  loading.value = true
  try {
    const { data } = await api.get('/api/cloud/licenses', { params: { page: page.value, page_size: pageSize.value } })
    items.value = data.items; total.value = data.total
  } finally { loading.value = false }
}

async function handleGenerate() {
  try {
    const { data } = await api.post('/api/cloud/licenses/generate', genForm)
    ElMessage.success(`License 已生成: ${data.license_key}`)
    genDialog.value = false; loadData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '生成失败') }
}

async function handleRevoke(id) {
  try {
    await api.put(`/api/cloud/licenses/${id}/revoke`)
    ElMessage.success('已吊销'); loadData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

onMounted(loadData)
</script>
