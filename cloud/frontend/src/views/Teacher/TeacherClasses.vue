<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div>
        <h3 style="margin:0">班级管理</h3>
        <div style="margin-top:6px;color:#666;font-size:13px">当前机构：{{ currentOrgName }}</div>
      </div>
      <el-button type="primary" @click="openCreate">创建班级</el-button>
    </div>

    <!-- 班级列表 -->
    <el-table :data="classes" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="班级名称" />
      <el-table-column prop="description" label="描述" show-overflow-tooltip />
      <el-table-column label="成员数" width="100">
        <template #default="{ row }">{{ row._studentCount ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="320">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="viewOverview(row)">查看概况</el-button>
          <el-button size="small" @click="viewDetail(row)">管理成员</el-button>
          <el-button size="small" type="warning" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteClass(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑班级对话框 -->
    <el-dialog v-model="showForm" :title="editingId ? '编辑班级' : '创建班级'" width="450px">
      <el-form :model="classForm" label-width="80px">
        <el-form-item label="所属机构">
          <el-input :model-value="currentOrgName" disabled />
        </el-form-item>
        <el-form-item label="班级名称">
          <el-input v-model="classForm.name" placeholder="例：2024级交通1班" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="classForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showForm = false">取消</el-button>
        <el-button type="primary" @click="saveClass" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- 班级概况对话框 -->
    <el-dialog v-model="showOverview" :title="'班级概况 — ' + (overviewClass?.name || '')" width="600px">
      <el-row :gutter="16" style="margin-bottom:20px">
        <el-col :span="6">
          <el-card shadow="hover">
            <div style="text-align:center">
              <div style="font-size:28px;color:#409eff;font-weight:600">{{ overviewStats.studentCount }}</div>
              <div style="color:#909399;margin-top:6px;font-size:13px">成员数</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <div style="text-align:center">
              <div style="font-size:28px;color:#e6a23c;font-weight:600">{{ overviewStats.submitted }}</div>
              <div style="color:#909399;margin-top:6px;font-size:13px">待批阅</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <div style="text-align:center">
              <div style="font-size:28px;color:#67c23a;font-weight:600">{{ overviewStats.graded }}</div>
              <div style="color:#909399;margin-top:6px;font-size:13px">已批阅</div>
            </div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <div style="text-align:center">
              <div style="font-size:28px;color:#909399;font-weight:600">{{ overviewStats.avgScore }}</div>
              <div style="color:#909399;margin-top:6px;font-size:13px">平均分</div>
            </div>
          </el-card>
        </el-col>
      </el-row>
      <h4 style="margin:0 0 12px 0">成员列表</h4>
      <el-table :data="overviewStudents" v-loading="loadingOverview" stripe size="small" max-height="300">
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="real_name" label="姓名" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 班级成员管理对话框 -->
    <el-dialog v-model="showStudents" :title="'班级成员 — ' + (currentClass?.name || '')" width="700px">
      <div style="margin-bottom:12px;display:flex;gap:8px">
        <el-select
          v-model="selectedStudentIds"
          multiple filterable
          placeholder="搜索并选择要添加的成员"
          style="flex:1"
        >
          <el-option
            v-for="s in availableStudents"
            :key="s.id"
            :label="s.real_name ? `${s.username} (${s.real_name})` : s.username"
            :value="s.id"
          />
        </el-select>
        <el-button type="primary" @click="addStudents" :disabled="!selectedStudentIds.length">添加</el-button>
      </div>

      <el-table :data="classStudents" v-loading="loadingStudents" stripe size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="real_name" label="姓名" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="removeStudent(row.id)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import api from '@/api/client'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const classes = ref([])
const loading = ref(false)
const showForm = ref(false)
const saving = ref(false)
const editingId = ref(null)
const classForm = reactive({ name: '', description: '', org_id: null })
const orgList = ref([])

const currentOrgName = computed(() => {
  const current = orgList.value.find(item => item.id === auth.user?.org_id)
  return current?.name || (auth.user?.org_id ? `机构 #${auth.user.org_id}` : '未绑定机构')
})

// 班级概况
const showOverview = ref(false)
const overviewClass = ref(null)
const overviewStudents = ref([])
const loadingOverview = ref(false)
const overviewStats = reactive({ studentCount: 0, submitted: 0, graded: 0, avgScore: '-' })

async function viewOverview(row) {
  overviewClass.value = row
  showOverview.value = true
  loadingOverview.value = true
  try {
    const { data: detail } = await api.get(`/api/cloud/classes/${row.id}`)
    overviewStudents.value = detail.students || []
    overviewStats.studentCount = overviewStudents.value.length
    // 获取该班级相关的报告统计
    try {
      const { data: reportData } = await api.get('/api/cloud/reports', { params: { class_id: row.id, page_size: 200 } })
      const reports = reportData.items || reportData
      overviewStats.submitted = reports.filter(r => r.status === 'submitted').length
      overviewStats.graded = reports.filter(r => r.status === 'graded').length
      const scored = reports.filter(r => r.score != null)
      overviewStats.avgScore = scored.length > 0
        ? (scored.reduce((s, r) => s + r.score, 0) / scored.length).toFixed(1)
        : '-'
    } catch {
      overviewStats.submitted = 0
      overviewStats.graded = 0
      overviewStats.avgScore = '-'
    }
  } catch {
    overviewStudents.value = []
    Object.assign(overviewStats, { studentCount: 0, submitted: 0, graded: 0, avgScore: '-' })
  } finally { loadingOverview.value = false }
}

// 成员管理
const showStudents = ref(false)
const currentClass = ref(null)
const classStudents = ref([])
const loadingStudents = ref(false)
const allStudents = ref([])
const selectedStudentIds = ref([])
const availableStudents = ref([])

function fmtDate(d) { return d ? new Date(d).toLocaleString('zh-CN') : '-' }

async function fetchClasses() {
  loading.value = true
  try {
    const { data } = await api.get('/api/cloud/classes', { params: { page_size: 50 } })
    const items = data.items || data
    // 获取每个班级的成员数
    for (const cls of items) {
      try {
        const { data: detail } = await api.get(`/api/cloud/classes/${cls.id}`)
        cls._studentCount = detail.students?.length ?? 0
      } catch { cls._studentCount = 0 }
    }
    classes.value = items
  } catch { /* ignore */ } finally { loading.value = false }
}

async function fetchOrgs() {
  try {
    const { data } = await api.get('/api/cloud/public/orgs')
    orgList.value = data
  } catch { /* ignore */ }
}

async function ensureCurrentUser() {
  try {
    await auth.fetchCurrentUser()
  } catch { /* ignore */ }
}

function openCreate() {
  if (!auth.user?.org_id) {
    ElMessage.warning('当前教师账号未绑定机构，暂无法创建班级')
    return
  }
  editingId.value = null
  classForm.name = ''
  classForm.description = ''
  classForm.org_id = auth.user?.org_id || null
  showForm.value = true
}

function openEdit(row) {
  editingId.value = row.id
  classForm.name = row.name
  classForm.description = row.description || ''
  classForm.org_id = row.org_id || auth.user?.org_id || null
  showForm.value = true
}

async function saveClass() {
  if (!classForm.name.trim()) { ElMessage.warning('请输入班级名称'); return }
  if (!auth.user?.org_id) { ElMessage.warning('当前教师账号未绑定机构'); return }
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/api/cloud/classes/${editingId.value}`, classForm)
      ElMessage.success('班级已更新')
    } else {
      await api.post('/api/cloud/classes', classForm)
      ElMessage.success('班级已创建')
    }
    showForm.value = false
    fetchClasses()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally { saving.value = false }
}

async function deleteClass(row) {
  await ElMessageBox.confirm(`确定删除班级「${row.name}」？`, '确认删除', { type: 'warning' })
  try {
    await api.delete(`/api/cloud/classes/${row.id}`)
    ElMessage.success('已删除')
    fetchClasses()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function viewDetail(row) {
  currentClass.value = row
  showStudents.value = true
  selectedStudentIds.value = []
  await Promise.all([fetchClassStudents(row.id), fetchAllStudents()])
}

async function fetchClassStudents(classId) {
  loadingStudents.value = true
  try {
    const { data } = await api.get(`/api/cloud/classes/${classId}/students`)
    classStudents.value = data
    updateAvailable()
  } catch { /* ignore */ } finally { loadingStudents.value = false }
}

async function fetchAllStudents() {
  try {
    // 分页拉取所有成员（API 上限 page_size=50）
    let all = [], page = 1
    while (true) {
      const { data } = await api.get('/api/cloud/users', { params: { role: 'student', scope: 'org', page, page_size: 50 } })
      const items = data.items || data
      all = all.concat(items)
      if (!data.pages || page >= data.pages) break
      page++
    }
    allStudents.value = all
    updateAvailable()
  } catch { /* ignore */ }
}

function updateAvailable() {
  const enrolled = new Set(classStudents.value.map(s => s.id))
  availableStudents.value = allStudents.value.filter(s => !enrolled.has(s.id))
}

async function addStudents() {
  if (!selectedStudentIds.value.length) return
  try {
    await api.post(`/api/cloud/classes/${currentClass.value.id}/students`, {
      student_ids: selectedStudentIds.value,
    })
    ElMessage.success('成员已添加')
    selectedStudentIds.value = []
    await fetchClassStudents(currentClass.value.id)
    fetchClasses()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  }
}

async function removeStudent(studentId) {
  await ElMessageBox.confirm('确定从班级中移除该成员？', '确认', { type: 'warning' })
  try {
    await api.delete(`/api/cloud/classes/${currentClass.value.id}/students`, {
      data: { student_ids: [studentId] },
    })
    ElMessage.success('已移除')
    await fetchClassStudents(currentClass.value.id)
    fetchClasses()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '移除失败')
  }
}

async function initPage() {
  await ensureCurrentUser()
  await fetchOrgs()
  await fetchClasses()
}

onMounted(initPage)
</script>
