<template>
  <div>
    <div class="page-head">
      <h3>班级消息</h3>
      <div style="display:flex;gap:12px">
        <el-button circle plain :loading="loading" title="刷新消息" @click="refreshData">
          <el-icon><Refresh /></el-icon>
        </el-button>
        <el-button type="primary" @click="openCreate">发布消息</el-button>
      </div>
    </div>

    <el-table :data="messages" v-loading="loading" stripe>
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column prop="class_name" label="班级" width="140" />
      <el-table-column prop="created_at" label="发布时间" width="180">
        <template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template>
      </el-table-column>
      <el-table-column prop="content" label="内容" show-overflow-tooltip />
    </el-table>

    <el-dialog v-model="showCreate" title="发布班级消息" width="560px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="班级">
          <el-select v-model="form.class_id" placeholder="请选择班级" style="width:100%">
            <el-option v-for="c in classes" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createMessage">发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '@/api/client'
import { ElMessage } from 'element-plus'

const messages = ref([])
const classes = ref([])
const loading = ref(false)
const creating = ref(false)
const showCreate = ref(false)
const form = reactive({ class_id: null, title: '', content: '' })

async function fetchClasses() {
  const { data } = await api.get('/api/cloud/classes', { params: { page_size: 100 } })
  classes.value = data.items || []
}

async function fetchMessages() {
  loading.value = true
  try {
    const { data } = await api.get('/api/cloud/messages', { params: { page_size: 100 } })
    messages.value = data.items || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '消息加载失败')
  } finally {
    loading.value = false
  }
}

async function refreshData() {
  await Promise.all([fetchClasses(), fetchMessages()])
}

function openCreate() {
  Object.assign(form, { class_id: null, title: '', content: '' })
  showCreate.value = true
}

async function createMessage() {
  if (!form.class_id || !form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写班级、标题和内容')
    return
  }
  creating.value = true
  try {
    await api.post('/api/cloud/messages', form)
    ElMessage.success('消息已发布')
    showCreate.value = false
    fetchMessages()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '发布失败')
  } finally {
    creating.value = false
  }
}

onMounted(refreshData)
</script>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-head h3 { margin: 0; }
</style>
