<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h3 style="margin:0">教学任务管理</h3>
      <div style="display:flex;gap:12px;align-items:center">
        <el-button circle plain :loading="refreshing" title="刷新最新任务数据" @click="refreshTaskData">
          <el-icon><Refresh /></el-icon>
        </el-button>
        <el-button type="primary" @click="openCreate">发布任务</el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      type="warning"
      :closable="false"
      show-icon
      :title="loadError"
      style="margin-bottom: 12px"
    />

    <el-table :data="displayTasks" v-loading="loading" stripe>
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="task-requirement">
            <div v-for="item in parseDescription(row.description)" :key="item.label" class="requirement-row">
              <b>{{ item.label }}</b>
              <span>{{ item.value }}</span>
            </div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="id" label="ID" width="90">
        <template #default="{ row }">{{ row.isTemplate ? '案例' : row.id }}</template>
      </el-table-column>
      <el-table-column prop="title" label="任务标题" min-width="220" />
      <el-table-column label="分发班级" width="140">
        <template #default="{ row }">{{ classMap[row.class_id] || row.class_name || '未指定' }}</template>
      </el-table-column>
      <el-table-column prop="module_id" label="实验模块" width="150">
        <template #default="{ row }">{{ moduleLabel(row.module_id) }}</template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.isTemplate ? 'warning' : row.status === 'published' ? 'success' : 'info'" size="small">
            {{ row.isTemplate ? '待下发案例' : row.status === 'published' ? '已发布' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="deadline" label="截止时间" width="180">
        <template #default="{ row }">{{ row.deadline ? new Date(row.deadline).toLocaleString('zh-CN') : '-' }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button v-if="row.status==='draft'" size="small" type="success" @click="publishTask(row)">发布</el-button>
          <el-button v-else-if="row.isTemplate" size="small" type="primary" @click="openCreate(row.module_id)">下发</el-button>
          <span v-else style="color:#909399">已同步</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建任务对话框 -->
    <el-dialog v-model="showCreate" title="选择案例并发布任务" width="880px">
      <el-form :model="newTask" label-width="80px">
        <el-form-item label="案例模板">
          <div class="case-grid">
            <button
              v-for="item in taskCases"
              :key="item.id"
              type="button"
              class="case-card"
              :class="{ active: selectedCaseId === item.id }"
              @click="selectCase(item.id)"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.scenario }}</span>
              <em>{{ item.versions }}</em>
            </button>
          </div>
        </el-form-item>
        <el-form-item v-if="selectedCase" label="案例信息">
          <div class="case-detail">
            <div><b>场景</b><span>{{ selectedCase.scenario }}</span></div>
            <div><b>数据/配置</b><span>{{ selectedCase.data }}</span></div>
            <div><b>算法</b><span>{{ selectedCase.algorithm }}</span></div>
            <div><b>上传内容</b><span>{{ selectedCase.uploads }}</span></div>
            <div><b>软件版本</b><span>{{ selectedCase.versions }}</span></div>
          </div>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="newTask.title" placeholder="请输入任务标题" />
        </el-form-item>
        <el-form-item label="分发班级">
          <el-select v-model="newTask.class_id" placeholder="选择班级" style="width:100%">
            <el-option v-for="c in classList" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newTask.description" type="textarea" :rows="7" />
        </el-form-item>
        <el-form-item label="模块">
          <el-select v-model="newTask.module_id" placeholder="选择模块" style="width:100%">
            <el-option label="多源数据融合" value="data_fusion" />
            <el-option label="交通流重构" value="traffic_reconstruction" />
            <el-option label="交通流预测" value="traffic_prediction" />
            <el-option label="交通信号优化" value="signal_optimization" />
            <el-option label="路径诱导" value="path_guidance" />
            <el-option label="车速控制" value="vehicle_speed_control" />
            <el-option label="三层级协同优化" value="coordination_control" />
          </el-select>
        </el-form-item>
        <el-form-item label="满分">
          <el-input-number v-model="newTask.max_score" :min="1" :max="200" />
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker v-model="newTask.deadline" type="datetime" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createTask" :loading="creating">创建并发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/api/client'
import { ElMessage } from 'element-plus'

const tasks = ref([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const refreshing = ref(false)
const classList = ref([])
const selectedCaseId = ref(null)
const loadError = ref('')
const newTask = reactive({ title: '', description: '', module_id: '', class_id: null, max_score: 100, deadline: null })

const taskCases = [
  {
    id: 'data_fusion',
    title: '多源数据融合案例',
    module: 'data_fusion',
    scenario: '路侧视频检测与点云特征融合，验证不同感知源对目标置信度的提升效果。',
    data: 'data_fusion_基础数据包.zip；train_features.csv、test_features.csv；baseline_predictions.csv。',
    algorithm: '平台 baseline 为贝叶斯决策级融合；学生提交自研融合模型或权重策略。',
    uploads: '代码 .py；方案说明；仿真过程文件；结果 CSV：frame_id、class_name、prediction_fused_prob。',
    versions: '平台 v1.0；Python 3.10+；基础题包 metadata.json。'
  },
  {
    id: 'traffic_reconstruction',
    title: '交通流重构案例',
    module: 'traffic_reconstruction',
    scenario: '区域路网 OD 反推与路段交通流重构，基于观测流量恢复网络交通状态。',
    data: 'traffic_reconstruction_基础数据包.zip；test_observed_counts.csv、input_link.csv、input_node.csv、input_zone.csv。',
    algorithm: '平台 baseline 为 DTALite/NEXTA ODME 与交通分配；学生提交自研 OD 反推或修正算法。',
    uploads: '代码 .py；方案说明；DTALite/NEXTA 过程文件；结果 CSV：link_id、time_interval、simulated_link_count。',
    versions: '平台 v1.0；Python 3.10+；DTALite/NEXTA 内置版。'
  },
  {
    id: 'traffic_prediction',
    title: '交通流预测案例',
    module: 'traffic_prediction',
    scenario: '短时交通流预测，基于历史流量、速度和时间特征预测测试样本总流量。',
    data: 'traffic_prediction_基础数据包.zip；raw_traffic_flow.csv、train.csv、test_features.csv。',
    algorithm: '平台 baseline 为 DecisionTreeRegressor(max_depth=10, random_state=42)。',
    uploads: '代码 .py；方案说明；训练/预测过程日志；结果 CSV：sample_id、prediction_total_flow。',
    versions: '平台 v1.0；Python 3.10+；scikit-learn 环境。'
  },
  {
    id: 'signal_optimization',
    title: '交通信号优化案例',
    module: 'signal_optimization',
    scenario: '单点交叉口信号配时优化，在给定相位约束下输出周期与绿灯时间。',
    data: 'signal_optimization_基础数据包.zip；scenario_config.json；baseline_solution.csv。',
    algorithm: '平台 baseline 为 Webster 配时；学生可提交遗传算法、启发式搜索或自研配时算法。',
    uploads: '代码 .py；方案说明；SUMO/算法运行过程文件；结果 CSV/JSON：cycle、phase_id、green_time。',
    versions: '平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+。'
  },
  {
    id: 'path_guidance',
    title: '路径诱导案例',
    module: 'path_guidance',
    scenario: 'SiouxFalls 路网 OD 路径诱导，计算候选路径并降低拥堵路段负荷。',
    data: 'path_guidance_基础数据包.zip；network_edges.csv、od_pairs.csv；baseline_paths.csv。',
    algorithm: '平台 baseline 为最短路/KSP；学生实现动态路径诱导、拥堵惩罚或 CAV 重分配策略。',
    uploads: '代码 .py；方案说明；SUMO 路径诱导过程文件；结果 CSV：origin、destination、path、total_cost。',
    versions: '平台 v1.0；Python 3.10；SUMO 1.15+。'
  },
  {
    id: 'vehicle_speed_control',
    title: '车速控制案例',
    module: 'vehicle_speed_control',
    scenario: '车辆速度控制与跟驰稳定性评估，比较延误、速度波动和通行效率。',
    data: 'vehicle_speed_control_基础数据包.zip；scenario.json；baseline_metrics.csv。',
    algorithm: '平台 baseline 为 PID/规则控制；学生提交 MPC、强化学习或自研速度控制策略。',
    uploads: '代码 .py；方案说明；SUMO/CARLA 控制过程记录；结果 CSV：algorithm、average_delay、avg_speed、speed_std、avg_accel、throughput。',
    versions: '平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+；可选 CARLA 0.9.13+。'
  },
  {
    id: 'coordination_control',
    title: '三层级协同优化案例',
    module: 'coordination_control',
    scenario: '信号优化、路径诱导、车速控制三层级协同，对比无协同、局部协同和全协同。',
    data: 'coordination_control_基础数据包.zip；baseline_none.json、baseline_local.json、baseline_full.json。',
    algorithm: '平台 baseline 为全协同控制；学生组合信号配时、路径诱导和车速控制策略。',
    uploads: '代码 .py；方案说明；SUMO 协同控制过程文件与决策日志；结果 CSV：step、avg_speed、waiting_count。',
    versions: '平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+。'
  }
]

const selectedCase = computed(() => taskCases.find((item) => item.id === selectedCaseId.value))

const displayTasks = computed(() => {
  if (tasks.value.length) return tasks.value
  const now = new Date().toISOString()
  return taskCases.map((item, index) => ({
    id: `case-${index + 1}`,
    title: item.title.replace('案例', '自研算法任务'),
    description: buildDescription(item),
    module_id: item.module,
    class_name: classList.value[0]?.name || '交通工程2024级1班',
    status: 'template',
    created_at: now,
    deadline: null,
    isTemplate: true,
  }))
})

const classMap = computed(() => {
  const m = {}
  classList.value.forEach(c => { m[c.id] = c.name })
  return m
})

async function fetchTasks() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get('/api/cloud/tasks', { params: { page_size: 50 } })
    tasks.value = Array.isArray(data.items) ? data.items : Array.isArray(data) ? data : []
    return true
  } catch (e) {
    tasks.value = []
    loadError.value = e.response?.data?.detail || '任务接口暂时不可用，已展示默认教学任务案例。'
    return false
  } finally { loading.value = false }
}

async function fetchClasses() {
  try {
    const { data } = await api.get('/api/cloud/classes', { params: { page_size: 50 } })
    classList.value = Array.isArray(data.items) ? data.items : Array.isArray(data) ? data : []
    return true
  } catch {
    classList.value = []
    return false
  }
}

async function refreshTaskData() {
  refreshing.value = true
  try {
    const results = await Promise.all([fetchTasks(), fetchClasses()])
    if (results.every(Boolean)) ElMessage.success('已刷新最新任务数据')
    else ElMessage.warning('任务列表已刷新，部分数据获取失败')
  } finally { refreshing.value = false }
}

function openCreate(caseId = null) {
  Object.assign(newTask, { title: '', description: '', module_id: '', class_id: null, max_score: 100, deadline: null })
  if (classList.value.length) newTask.class_id = classList.value[0].id
  showCreate.value = true
  selectCase(caseId || selectedCaseId.value || taskCases[0].id)
}

function buildDescription(item) {
  return [
    `【实验场景】${item.scenario}`,
    `【基础仿真配置/数据】${item.data}`,
    `【采用算法】${item.algorithm}`,
    `【需要上传】${item.uploads}`,
    `【软件版本】${item.versions}`,
    `【下载链接】/api/v1/self-algorithms/packs/${item.id}/download`
  ].join('\n')
}

function parseDescription(description) {
  const labels = ['实验场景', '基础仿真配置/数据', '采用算法', '需要上传', '软件版本', '下载链接']
  const result = labels.map((label) => ({ label, value: '' }))
  String(description || '').split(/\r?\n/).forEach((line) => {
    const match = line.match(/^【(.+?)】(.+)$/)
    if (!match) return
    const target = result.find((item) => item.label === match[1])
    if (target) target.value = match[2]
  })
  return result.filter((item) => item.value)
}

function moduleLabel(id) {
  const map = {
    data_fusion: '多源数据融合',
    traffic_reconstruction: '交通流重构',
    traffic_prediction: '交通流预测',
    signal_optimization: '交通信号优化',
    path_guidance: '路径诱导',
    vehicle_speed_control: '车速控制',
    coordination_control: '三层级协同优化',
  }
  return map[id] || id || '-'
}

function selectCase(id) {
  const item = taskCases.find((caseItem) => caseItem.id === id)
  if (!item) return
  selectedCaseId.value = id
  newTask.title = item.title
  newTask.description = buildDescription(item)
  newTask.module_id = item.module
}

async function createTask() {
  if (!newTask.title.trim()) { ElMessage.warning('请输入任务标题'); return }
  if (!newTask.class_id) { ElMessage.warning('请选择分发班级'); return }
  creating.value = true
  try {
    const { data } = await api.post('/api/cloud/tasks', newTask)
    if (data?.id) await api.post(`/api/cloud/tasks/${data.id}/publish`)
    ElMessage.success('任务已创建并发布')
    showCreate.value = false
    fetchTasks()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  } finally { creating.value = false }
}

async function publishTask(row) {
  try {
    await api.post(`/api/cloud/tasks/${row.id}/publish`)
    ElMessage.success('任务已发布')
    fetchTasks()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '发布失败')
  }
}

onMounted(() => { fetchTasks(); fetchClasses() })
</script>

<style scoped>
.case-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
  width: 100%;
}
.case-card {
  border: 1px solid #dcdfe6;
  background: #fff;
  border-radius: 8px;
  padding: 10px;
  text-align: left;
  cursor: pointer;
  min-height: 112px;
}
.case-card.active {
  border-color: #2c5aa0;
  background: #ecf5ff;
}
.case-card strong,
.case-card span,
.case-card em {
  display: block;
}
.case-card strong {
  color: #2c5aa0;
  margin-bottom: 5px;
}
.case-card span,
.case-card em {
  color: #606266;
  font-size: 12px;
  line-height: 1.45;
  font-style: normal;
}
.case-detail {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  width: 100%;
  padding: 12px;
  border: 1px solid #d8e7f8;
  border-radius: 8px;
  background: #f7fbff;
}
.case-detail div {
  background: #fff;
  border: 1px solid #e4edf8;
  border-radius: 6px;
  padding: 8px;
}
.case-detail b {
  display: block;
  color: #303133;
  margin-bottom: 4px;
}
.case-detail span {
  color: #606266;
  font-size: 13px;
  line-height: 1.55;
}
.task-requirement {
  display: grid;
  gap: 8px;
  padding: 10px 24px;
  background: #f8fbff;
}
.requirement-row {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 12px;
  line-height: 1.7;
}
.requirement-row b {
  color: #2c5aa0;
}
.requirement-row span {
  color: #303133;
}
</style>
