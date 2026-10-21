<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px">
      <h3 style="margin:0">自研算法提交</h3>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <el-select v-model="filterClassId" clearable placeholder="按班级筛选" style="width:180px" @change="handleClassChange">
          <el-option v-for="c in classes" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-select v-model="filterStudentId" clearable placeholder="按学生筛选" style="width:180px" @change="fetchSubmissions">
          <el-option v-for="s in students" :key="s.id" :label="s.real_name || s.username" :value="s.id" />
        </el-select>
        <el-select v-model="filterType" clearable placeholder="按算法类型筛选" style="width:220px" @change="fetchSubmissions">
          <el-option v-for="p in packs" :key="p.algorithm_type" :label="p.label" :value="p.algorithm_type" />
        </el-select>
        <el-select v-model="filterTaskId" clearable placeholder="按任务筛选" style="width:220px" @change="fetchSubmissions">
          <el-option v-for="t in tasks" :key="t.id" :label="t.title" :value="t.id" />
        </el-select>
        <el-button circle plain :loading="loading" title="刷新提交记录" @click="refreshAll">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="这里展示学生按代码、方案说明、仿真过程、仿真结果四类文件提交的自研算法记录，教师可下载文件并查看平台自动生成的 baseline 对比分析。"
      style="margin-bottom:16px"
    />

    <el-table :data="submissions" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="算法类型" min-width="160">
        <template #default="{ row }">{{ labelOf(row.algorithm_type) }}</template>
      </el-table-column>
      <el-table-column label="关联任务" min-width="190">
        <template #default="{ row }">{{ row.task_title || (row.task_id ? ('任务#' + row.task_id) : '未关联任务') }}</template>
      </el-table-column>
      <el-table-column label="班级" min-width="130">
        <template #default="{ row }">{{ row.class_name || ('班级#' + row.class_id) }}</template>
      </el-table-column>
      <el-table-column label="学生" width="130">
        <template #default="{ row }">{{ row.student_name || ('学生#' + row.student_id) }}</template>
      </el-table-column>
      <el-table-column label="提交文件" min-width="220">
        <template #default="{ row }">
          <div class="file-line">代码：{{ row.code_original_filename || '-' }}</div>
          <div class="file-line">方案：{{ row.spec_original_filename || '-' }}</div>
          <div class="file-line">过程：{{ row.process_original_filename || '-' }}</div>
          <div class="file-line">结果：{{ row.result_original_filename || '-' }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="提交时间" width="180">
        <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}</template>
      </el-table-column>
      <el-table-column label="分析摘要" min-width="260">
        <template #default="{ row }">
          <div class="analysis-summary">{{ row.analysis?.summary || row.analysis_text || '暂无分析' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openAnalysis(row)">分析</el-button>
          <el-dropdown @command="(kind) => downloadFile(row, kind)">
            <el-button size="small" type="primary">下载<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="code">代码</el-dropdown-item>
                <el-dropdown-item command="spec">方案说明</el-dropdown-item>
                <el-dropdown-item command="process" :disabled="!row.process_original_filename">仿真过程</el-dropdown-item>
                <el-dropdown-item command="result">仿真结果</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showAnalysis" title="智能分析详情" width="720px">
      <div v-if="currentRow">
        <div style="margin-bottom:12px;color:#606266">
          {{ labelOf(currentRow.algorithm_type) }} · {{ currentRow.class_name || ('班级#' + currentRow.class_id) }} ·
          {{ currentRow.student_name || ('学生#' + currentRow.student_id) }}
        </div>
        <pre class="analysis-box">{{ currentRow.analysis_text || currentRow.analysis?.summary || '暂无分析' }}</pre>
        <el-table v-if="currentRow.analysis?.comparisons?.length" :data="currentRow.analysis.comparisons" size="small" style="margin-top:14px">
          <el-table-column prop="metric" label="指标" />
          <el-table-column prop="baseline" label="Baseline" />
          <el-table-column prop="student" label="学生结果" />
          <el-table-column prop="diff_percent" label="差异%" />
          <el-table-column prop="judgement" label="判断">
            <template #default="{ row }">
              <el-tag :type="row.judgement === 'advantage' ? 'success' : 'warning'" size="small">
                {{ row.judgement === 'advantage' ? '优势' : '劣势/风险' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="showAnalysis = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api/client'
import { ElMessage } from 'element-plus'

const packs = ref([])
const classes = ref([])
const students = ref([])
const tasks = ref([])
const submissions = ref([])
const loading = ref(false)
const filterClassId = ref(null)
const filterStudentId = ref(null)
const filterType = ref(null)
const filterTaskId = ref(null)
const showAnalysis = ref(false)
const currentRow = ref(null)

function labelOf(type) {
  return packs.value.find((item) => item.algorithm_type === type)?.label || type
}

async function fetchPacks() {
  const { data } = await api.get('/api/cloud/self-algorithms/packs')
  packs.value = data || []
}

async function fetchClasses() {
  const { data } = await api.get('/api/cloud/classes', { params: { page_size: 50 } })
  classes.value = data.items || data || []
}

async function fetchTasks() {
  const { data } = await api.get('/api/cloud/tasks', { params: { page_size: 100, status: 'published' } })
  tasks.value = data.items || data || []
}

async function fetchStudents() {
  if (!filterClassId.value) {
    students.value = []
    filterStudentId.value = null
    return
  }
  const { data } = await api.get(`/api/cloud/classes/${filterClassId.value}/students`)
  students.value = data || []
}

async function fetchSubmissions() {
  loading.value = true
  try {
    const params = { page_size: 100 }
    if (filterType.value) params.algorithm_type = filterType.value
    if (filterClassId.value) params.class_id = filterClassId.value
    if (filterStudentId.value) params.student_id = filterStudentId.value
    if (filterTaskId.value) params.task_id = filterTaskId.value
    const { data } = await api.get('/api/cloud/self-algorithms/submissions', { params })
    submissions.value = data.items || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载自研算法提交失败')
  } finally {
    loading.value = false
  }
}

async function handleClassChange() {
  filterStudentId.value = null
  await fetchStudents()
  await fetchSubmissions()
}

async function refreshAll() {
  try {
    await Promise.all([fetchPacks(), fetchClasses()])
    await fetchTasks()
    if (filterClassId.value) await fetchStudents()
    await fetchSubmissions()
    ElMessage.success('已刷新自研算法提交记录')
  } catch {
    ElMessage.warning('部分数据刷新失败')
  }
}

function openAnalysis(row) {
  currentRow.value = row
  showAnalysis.value = true
}

async function downloadFile(row, kind) {
  try {
    const response = await api.get(`/api/cloud/self-algorithms/submissions/${row.id}/download/${kind}`, { responseType: 'blob' })
    const names = {
      code: row.code_original_filename || 'algorithm.py',
      spec: row.spec_original_filename || '方案说明',
      process: row.process_original_filename || '仿真过程',
      result: row.result_original_filename || 'result',
    }
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = names[kind]
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('下载失败')
  }
}

onMounted(refreshAll)
</script>

<style scoped>
.file-line { color:#606266; font-size:13px; line-height:1.7; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.analysis-summary {
  color:#606266; font-size:13px; line-height:1.6;
  display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;
}
.analysis-box {
  margin:0; white-space:pre-wrap; line-height:1.8; color:#333; background:#f7fbff;
  border:1px solid #d8e7f8; border-radius:8px; padding:12px; font-family:inherit;
}
</style>
