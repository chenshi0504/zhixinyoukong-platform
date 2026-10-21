<template>
  <div>
    <div style="display:flex;justify-content:flex-end;margin-bottom:16px">
      <el-button type="primary" @click="showDialog()">新建任务</el-button>
    </div>
    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="module_id" label="模块" width="160" />
      <el-table-column prop="deadline" label="截止时间" width="180" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'published' ? 'success' : 'info'" size="small">{{ row.status === 'published' ? '已发布' : '草稿' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="{ row }">
          <el-button text type="warning" size="small" @click="showDialog(row)">编辑</el-button>
          <el-button text type="success" size="small" v-if="row.status==='draft'" @click="handlePublish(row.id)">发布</el-button>
          <el-popconfirm title="确认删除？" @confirm="handleDelete(row.id)">
            <template #reference><el-button text type="danger" size="small">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:16px;justify-content:flex-end" v-model:current-page="page"
      :page-size="pageSize" :total="total" layout="total, prev, pager, next" @current-change="loadData" />

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑任务' : '新建任务'" width="550px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="实验模块">
          <el-select v-model="form.module_id" placeholder="选择模块">
            <el-option v-for="m in modules" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止时间"><el-date-picker v-model="form.deadline" type="datetime" /></el-form-item>
        <el-form-item label="满分"><el-input-number v-model="form.max_score" :min="1" :max="100" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '@/api/client'
import { ElMessage } from 'element-plus'

const modules = [
  { id: 'data_collection', name: '多源数据采集' },
  { id: 'data_fusion', name: '多源数据融合' },
  { id: 'traffic_prediction', name: '交通流预测' },
  { id: 'traffic_reconstruction', name: '交通流重构' },
  { id: 'signal_optimization', name: '交通信号优化' },
  { id: 'path_guidance', name: '路径诱导' },
  { id: 'vehicle_speed_control', name: '车速控制' },
  { id: 'three_level_control', name: '三层级协同优化' },
  { id: 'vehicle_dev_control', name: '车规级智能车辆开发' },
  { id: 'carla_simulation', name: '虚实结合仿真场景' },
]

const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const dialogVisible = ref(false)
const editing = ref(null)
const form = reactive({ title: '', description: '', module_id: '', deadline: null, max_score: 100 })

async function loadData() {
  loading.value = true
  try {
    const { data } = await api.get('/api/cloud/tasks', { params: { page: page.value, page_size: pageSize.value } })
    items.value = data.items; total.value = data.total
  } finally { loading.value = false }
}

function showDialog(task) {
  editing.value = task || null
  Object.assign(form, task || { title: '', description: '', module_id: '', deadline: null, max_score: 100 })
  dialogVisible.value = true
}

async function handleSave() {
  try {
    if (editing.value) { await api.put(`/api/cloud/tasks/${editing.value.id}`, form) }
    else { await api.post('/api/cloud/tasks', form) }
    ElMessage.success('保存成功'); dialogVisible.value = false; loadData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

async function handlePublish(id) {
  try { await api.post(`/api/cloud/tasks/${id}/publish`); ElMessage.success('已发布'); loadData() }
  catch (e) { ElMessage.error(e.response?.data?.detail || '发布失败') }
}

async function handleDelete(id) {
  try { await api.delete(`/api/cloud/tasks/${id}`); ElMessage.success('已删除'); loadData() }
  catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}

onMounted(loadData)
</script>
