<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">实验报告管理</h3>
      <div style="display:flex;gap:12px;align-items:center">
        <el-button circle plain :loading="refreshing" title="刷新最新报告数据" @click="refreshReportData">
          <el-icon><Refresh /></el-icon>
        </el-button>
        <el-select v-model="filterTaskId" clearable placeholder="按任务筛选" style="width:200px" @change="fetchReports">
          <el-option v-for="t in taskList" :key="t.id" :label="t.title" :value="t.id" />
        </el-select>
        <el-select v-model="filterStatus" clearable placeholder="按状态筛选" style="width:140px" @change="fetchReports">
          <el-option label="待批阅" value="submitted" />
          <el-option label="已批阅" value="graded" />
        </el-select>
      </div>
    </div>

    <el-table :data="reports" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="task_title" label="所属任务" min-width="140">
        <template #default="{ row }">{{ row.task_title || '任务#' + row.task_id }}</template>
      </el-table-column>
      <el-table-column prop="student_name" label="提交人" width="120">
        <template #default="{ row }">{{ row.student_name || '成员#' + row.student_id }}</template>
      </el-table-column>
      <el-table-column prop="original_filename" label="文件名" min-width="160">
        <template #default="{ row }">{{ row.original_filename || '-' }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'graded' ? 'success' : row.status === 'submitted' ? 'warning' : 'info'" size="small">
            {{ row.status === 'graded' ? '已批阅' : row.status === 'submitted' ? '待批阅' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="score" label="成绩" width="80">
        <template #default="{ row }">{{ row.score ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="submitted_at" label="提交时间" width="180">
        <template #default="{ row }">{{ row.submitted_at ? new Date(row.submitted_at).toLocaleString('zh-CN') : '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button size="small" @click="downloadReport(row)">下载</el-button>
          <el-button v-if="row.status === 'submitted'" type="primary" size="small" @click="gradeReport(row)">批阅</el-button>
          <el-button v-else-if="row.status === 'graded'" type="success" size="small" @click="gradeReport(row)">修改评分</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showGrade" title="批阅报告" width="480px">
      <div v-if="gradeForm.studentName" style="margin-bottom:12px;color:#666">
        <strong>提交人：</strong>{{ gradeForm.studentName }}
        <span style="margin-left:16px"><strong>任务：</strong>{{ gradeForm.taskTitle }}</span>
      </div>
      <el-form label-width="60px">
        <el-form-item label="成绩">
          <el-input-number v-model="gradeForm.score" :min="0" :max="100" style="width:100%" />
        </el-form-item>
        <el-form-item label="评语">
          <el-input v-model="gradeForm.comment" type="textarea" :rows="4" placeholder="输入对该报告的评语..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGrade = false">取消</el-button>
        <el-button type="primary" @click="submitGrade" :loading="grading">提交批阅</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '@/api/client'
import { ElMessage } from 'element-plus'

const reports = ref([])
const loading = ref(false)
const showGrade = ref(false)
const grading = ref(false)
const refreshing = ref(false)
const gradeForm = reactive({ id: null, score: 80, comment: '', studentName: '', taskTitle: '' })
const filterTaskId = ref(null)
const filterStatus = ref(null)
const taskList = ref([])

async function fetchTasks() {
  try {
    const { data } = await api.get('/api/cloud/tasks', { params: { page_size: 50 } })
    taskList.value = data.items || data
    return true
  } catch {
    return false
  }
}

async function fetchReports() {
  loading.value = true
  try {
    const params = { page_size: 50 }
    if (filterTaskId.value) params.task_id = filterTaskId.value
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await api.get('/api/cloud/reports', { params })
    reports.value = data.items || data
    return true
  } catch {
    return false
  } finally { loading.value = false }
}

async function refreshReportData() {
  refreshing.value = true
  try {
    const results = await Promise.all([fetchTasks(), fetchReports()])
    if (results.every(Boolean)) ElMessage.success('已刷新最新报告数据')
    else ElMessage.warning('报告列表已刷新，部分数据获取失败')
  } finally { refreshing.value = false }
}

function gradeReport(row) {
  gradeForm.id = row.id
  gradeForm.score = row.score || 80
  gradeForm.comment = row.feedback || ''
  gradeForm.studentName = row.student_name || ''
  gradeForm.taskTitle = row.task_title || ''
  showGrade.value = true
}

async function submitGrade() {
  grading.value = true
  try {
    await api.put(`/api/cloud/reports/${gradeForm.id}/grade`, {
      score: gradeForm.score,
      feedback: gradeForm.comment,
    })
    ElMessage.success('批阅成功')
    showGrade.value = false
    fetchReports()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '批阅失败')
  } finally { grading.value = false }
}

async function downloadReport(row) {
  try {
    const response = await api.get(`/api/cloud/reports/${row.id}/download`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = row.original_filename || 'report'
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('下载失败')
  }
}

onMounted(() => { fetchTasks(); fetchReports() })
</script>
