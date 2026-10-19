<template>
  <div>
    <h3>教学统计</h3>
    <el-row :gutter="20" style="margin-bottom:24px">
      <el-col :span="6" v-for="item in stats" :key="item.label">
        <el-card shadow="hover">
          <div style="text-align:center">
            <div style="font-size:32px;color:#67c23a;font-weight:600">{{ item.value }}</div>
            <div style="color:#909399;margin-top:8px">{{ item.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-card>
      <div ref="chartRef" style="height:360px"></div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import api from '@/api/client'
import * as echarts from 'echarts'

const stats = ref([
  { label: '发布任务数', value: 0 },
  { label: '提交人数', value: 0 },
  { label: '已提交报告', value: 0 },
  { label: '待批阅', value: 0 },
])
const chartRef = ref()
const allReports = ref([])

async function fetchStats() {
  try {
    const [tasksRes, reportsRes] = await Promise.all([
      api.get('/api/cloud/tasks', { params: { page_size: 200 } }),
      api.get('/api/cloud/reports', { params: { page_size: 200 } }),
    ])
    const tasks = tasksRes.data.items || tasksRes.data
    const reports = reportsRes.data.items || reportsRes.data
    allReports.value = reports
    stats.value[0].value = tasks.length
    stats.value[1].value = reports.length > 0 ? new Set(reports.map(r => r.student_id)).size : 0
    stats.value[2].value = reports.filter(r => r.status !== 'draft').length
    stats.value[3].value = reports.filter(r => r.status === 'submitted').length
  } catch { /* ignore */ }
}

function renderChart() {
  if (!chartRef.value) return
  const chart = echarts.init(chartRef.value)
  const dayLabels = []
  const dayCounts = []
  const now = new Date()
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 86400000)
    const key = d.toISOString().slice(0, 10)
    dayLabels.push(`${d.getMonth() + 1}/${d.getDate()}`)
    dayCounts.push(allReports.value.filter(r => r.submitted_at && r.submitted_at.slice(0, 10) === key).length)
  }
  chart.setOption({
    title: { text: '近 7 天报告提交情况', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dayLabels },
    yAxis: { type: 'value', name: '提交数' },
    series: [{ type: 'bar', data: dayCounts, color: '#67c23a' }],
  })
  window.addEventListener('resize', () => chart.resize())
}

onMounted(async () => {
  await fetchStats()
  await nextTick()
  renderChart()
})
</script>
