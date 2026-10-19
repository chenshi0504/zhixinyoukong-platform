<template>
  <div v-loading="loading">
    <el-page-header @back="$router.push('/orgs')" :content="org?.name || ''" />
    <el-descriptions :column="3" border style="margin-top:20px" v-if="org">
      <el-descriptions-item label="机构名称">{{ org.name }}</el-descriptions-item>
      <el-descriptions-item label="联系人">{{ org.contact_name }}</el-descriptions-item>
      <el-descriptions-item label="电话">{{ org.contact_phone }}</el-descriptions-item>
      <el-descriptions-item label="地址">{{ org.address }}</el-descriptions-item>
      <el-descriptions-item label="License 总数">{{ org.license_count }}</el-descriptions-item>
      <el-descriptions-item label="活跃 License">{{ org.active_license_count }}</el-descriptions-item>
      <el-descriptions-item label="用户数">{{ org.user_count }}</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/api/client'

const route = useRoute()
const org = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get(`/api/cloud/orgs/${route.params.id}`)
    org.value = data
  } finally { loading.value = false }
})
</script>
