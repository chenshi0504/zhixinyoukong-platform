<template>
  <div>
    <h3 style="margin-bottom:20px">统计分析</h3>
    <el-row :gutter="20" style="margin-bottom:20px">
      <el-col :span="8" v-for="card in overviewCards" :key="card.label">
        <el-card shadow="hover">
          <div class="stat-card">
            <div class="stat-value">{{ card.value }}</div>
            <div class="stat-label">{{ card.label }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="14">
        <el-card>
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>使用趋势</span>
              <el-date-picker v-model="dateRange" type="daterange" range-separator="至"
                start-placeholder="开始日期" end-placeholder="结束日期" value-format="YYYY-MM-DD"
                @change="loadTrends" style="width:280px" />
            </div>
          </template>
          <div ref="trendChartRef" style="height:360px"></div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card>
          <template #header><span>模块使用排名</span></template>
          <div ref="moduleChartRef" style="height:360px"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import api from '@/api/client'

const overviewCards = ref([
  { label: '活跃机构', value: '-' },
  { label: '近30天活跃用户', value: '-' },
  { label: '总实验次数', value: '-' },
])

const dateRange = ref([])
const trendChartRef = ref(null)
const moduleChartRef = ref(null)
let trendChart = null
let moduleChart = null

async function loadOverview() {
  try {
    const { data } = await api.get('/api/cloud/analytics/overview')
    overviewCards.value = [
      { label: '活跃机构', value: data.total_active_orgs ?? 0 },
      { label: '近30天活跃用户', value: data.active_users_last_30d ?? 0 },
      { label: '总实验次数', value: data.total_experiments ?? 0 },
    ]
  } catch { /* ignore */ }
}

async function loadTrends() {
  try {
    const params = {}
    if (dateRange.value?.length === 2) {
      params.start = dateRange.value[0]
      params.end = dateRange.value[1]
    } else {
      const end = new Date()
      const start = new Date()
      start.setDate(end.getDate() - 30)
      params.start = start.toISOString().slice(0, 10)
      params.end = end.toISOString().slice(0, 10)
    }
    const { data } = await api.get('/api/cloud/analytics/trends', { params })
    const rows = data.data || []
    const dates = rows.map(d => d.report_date)
    const users = rows.map(d => d.active_users)
    const experiments = rows.map(d => d.experiment_count)
    trendChart?.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['活跃用户', '实验次数'] },
      xAxis: { type: 'category', data: dates },
      yAxis: { type: 'value' },
      series: [
        { name: '活跃用户', type: 'line', data: users, smooth: true },
        { name: '实验次数', type: 'line', data: experiments, smooth: true },
      ],
    })
  } catch { /* ignore */ }
}

async function loadModules() {
  try {
    const { data } = await api.get('/api/cloud/analytics/modules')
    const rows = data.data || []
    const names = rows.map(d => d.module_id)
    const counts = rows.map(d => d.total_count)
    moduleChart?.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: names, axisLabel: { rotate: 30, fontSize: 11 } },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: counts, itemStyle: { color: '#409eff' } }],
    })
  } catch { /* ignore */ }
}

onMounted(async () => {
  await nextTick()
  trendChart = echarts.init(trendChartRef.value)
  moduleChart = echarts.init(moduleChartRef.value)
  loadOverview()
  loadTrends()
  loadModules()
})

onBeforeUnmount(() => {
  trendChart?.dispose()
  moduleChart?.dispose()
})
</script>

<style scoped>
.stat-card { text-align: center; padding: 10px 0; }
.stat-value { font-size: 32px; font-weight: 700; color: #409eff; }
.stat-label { font-size: 14px; color: #909399; margin-top: 8px; }
</style>
