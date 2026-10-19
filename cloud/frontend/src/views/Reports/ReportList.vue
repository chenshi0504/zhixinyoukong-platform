<template>
  <div>
    <div style="display:flex;gap:12px;margin-bottom:16px">
      <el-select v-model="statusFilter" placeholder="状态" clearable @change="loadData" style="width:140px">
        <el-option label="待评阅" value="submitted" />
        <el-option label="已评阅" value="graded" />
      </el-select>
    </div>
    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="task_id" label="任务ID" width="80" />
      <el-table-column prop="student_id" label="提交人ID" width="90" />
      <el-table-column prop="original_filename" label="文件名" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'graded' ? 'success' : 'warning'" size="small">{{ row.status === 'graded' ? '已评阅' : '待评阅' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="score" label="分数" width="80" />
      <el-table-column prop="submitted_at" label="提交时间" width="180" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="showGradeDialog(row)" v-if="row.status==='submitted'">评分</el-button>
          <el-button text size="small" @click="handleDownload(row.id)">下载</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:16px;justify-content:flex-end" v-model:current-page="page"
      :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="loadData" />

    <el-dialog v-model="gradeDialog" title="评分" width="400px">
      <el-form label-width="60px">
        <el-form-item label="分数"><el-input-number v-model="gradeForm.score" :min="0" :max="100" /></el-form-item>
        <el-form-item label="反馈"><el-input v-model="gradeForm.feedback" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="gradeDialog = false">取消</el-button>
        <el-button type="primary" @click="handleGrade">提交</el-button>
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
const statusFilter = ref('')
const gradeDialog = ref(false)
const gradingId = ref(null)
const gradeForm = reactive({ score: 80, feedback: '' })

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (statusFilter.value) params.status = statusFilter.value
    const { data } = await api.get('/api/cloud/reports', { params })
    items.value = data.items; total.value = data.total
  } finally { loading.value = false }
}

function showGradeDialog(row) { gradingId.value = row.id; gradeForm.score = 80; gradeForm.feedback = ''; gradeDialog.value = true }

async function handleGrade() {
  try {
    await api.put(`/api/cloud/reports/${gradingId.value}/grade`, gradeForm)
    ElMessage.success('评分成功'); gradeDialog.value = false; loadData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '评分失败') }
}

function handleDownload(id) { window.open(`/api/cloud/reports/${id}/download`, '_blank') }

onMounted(loadData)
</script>
