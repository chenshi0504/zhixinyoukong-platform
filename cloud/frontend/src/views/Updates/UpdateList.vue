<template>
  <div>
    <div style="display:flex;justify-content:space-between;margin-bottom:16px">
      <h3>版本更新管理</h3>
      <el-button type="primary" @click="showPublishDialog">发布新版本</el-button>
    </div>
    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="version" label="版本号" width="120" />
      <el-table-column prop="release_notes" label="发布说明" show-overflow-tooltip />
      <el-table-column label="强制更新" width="100">
        <template #default="{ row }">
          <el-tag :type="row.force_update ? 'danger' : 'info'" size="small">{{ row.force_update ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="file_size" label="文件大小" width="100">
        <template #default="{ row }">{{ row.file_size ? (row.file_size / 1024 / 1024).toFixed(1) + ' MB' : '-' }}</template>
      </el-table-column>
      <el-table-column prop="published_at" label="发布时间" width="180" />
    </el-table>
    <el-pagination style="margin-top:16px;justify-content:flex-end" v-model:current-page="page"
      :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="loadData" />

    <el-dialog v-model="publishDialog" title="发布新版本" width="500px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="版本号"><el-input v-model="form.version" placeholder="例如 1.2.0" /></el-form-item>
        <el-form-item label="发布说明"><el-input v-model="form.release_notes" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="下载地址"><el-input v-model="form.download_url" placeholder="https://..." /></el-form-item>
        <el-form-item label="文件大小"><el-input-number v-model="form.file_size" :min="0" placeholder="字节" /></el-form-item>
        <el-form-item label="强制更新"><el-switch v-model="form.force_update" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="publishDialog = false">取消</el-button>
        <el-button type="primary" @click="handlePublish">发布</el-button>
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
const publishDialog = ref(false)
const form = reactive({ version: '', release_notes: '', download_url: '', file_size: 0, force_update: false })

async function loadData() {
  loading.value = true
  try {
    const { data } = await api.get('/api/cloud/updates', { params: { page: page.value, page_size: pageSize.value } })
    items.value = data.items ?? data; total.value = data.total ?? items.value.length
  } finally { loading.value = false }
}

function showPublishDialog() {
  Object.assign(form, { version: '', release_notes: '', download_url: '', file_size: 0, force_update: false })
  publishDialog.value = true
}

async function handlePublish() {
  try {
    await api.post('/api/cloud/updates', form)
    ElMessage.success('发布成功'); publishDialog.value = false; loadData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '发布失败') }
}

onMounted(loadData)
</script>
