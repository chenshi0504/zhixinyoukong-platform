<template>
  <div>
    <div style="display:flex;justify-content:space-between;margin-bottom:16px">
      <el-input v-model="search" placeholder="搜索机构名称" style="width:300px" clearable @clear="loadData" @keyup.enter="loadData" />
      <el-button type="primary" @click="showDialog()">新建机构</el-button>
    </div>
    <el-table :data="items" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="机构名称" />
      <el-table-column prop="contact_name" label="联系人" />
      <el-table-column prop="contact_phone" label="电话" />
      <el-table-column prop="license_quota" label="License 配额" width="120" />
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button text type="primary" @click="$router.push(`/orgs/${row.id}`)">详情</el-button>
          <el-button text type="warning" @click="showDialog(row)">编辑</el-button>
          <el-popconfirm title="确认删除？" @confirm="handleDelete(row.id)">
            <template #reference><el-button text type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:16px;justify-content:flex-end" v-model:current-page="page"
      :page-size="pageSize" :total="total" :page-sizes="[10,20,50]"
      layout="total, sizes, prev, pager, next" @size-change="s => { pageSize = s; loadData() }" @current-change="loadData" />

    <el-dialog v-model="dialogVisible" :title="editingOrg ? '编辑机构' : '新建机构'" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="机构名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="联系人"><el-input v-model="form.contact_name" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="form.contact_phone" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="form.address" /></el-form-item>
        <el-form-item label="License 配额"><el-input-number v-model="form.license_quota" :min="1" /></el-form-item>
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

const items = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const search = ref('')
const dialogVisible = ref(false)
const editingOrg = ref(null)
const form = reactive({ name: '', contact_name: '', contact_phone: '', address: '', license_quota: 10 })

async function loadData() {
  loading.value = true
  try {
    const { data } = await api.get('/api/cloud/orgs', { params: { page: page.value, page_size: pageSize.value, search: search.value } })
    items.value = data.items
    total.value = data.total
  } finally { loading.value = false }
}

function showDialog(org) {
  editingOrg.value = org || null
  Object.assign(form, org || { name: '', contact_name: '', contact_phone: '', address: '', license_quota: 10 })
  dialogVisible.value = true
}

async function handleSave() {
  try {
    if (editingOrg.value) {
      await api.put(`/api/cloud/orgs/${editingOrg.value.id}`, form)
    } else {
      await api.post('/api/cloud/orgs', form)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    loadData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

async function handleDelete(id) {
  try {
    await api.delete(`/api/cloud/orgs/${id}`)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}

onMounted(loadData)
</script>
