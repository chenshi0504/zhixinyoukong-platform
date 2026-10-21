// 教学任务管理模块JavaScript交互功能

// API配置
const API_BASE = '/api/v1';
function authHeaders() {
    return { 'Authorization': 'Bearer ' + (localStorage.getItem('token') || ''), 'Content-Type': 'application/json' };
}

// 全局变量
let tasks = [];
let students = [];
let currentView = 'list';
let selectedTaskCaseId = null;

const TASK_CASES = [
    {
        id: 'data_fusion',
        title: '多源数据融合案例',
        module: 'data',
        scenario: '路侧视频检测与点云特征融合，验证不同感知源对目标置信度的提升效果。',
        data: '基础仿真/题包：data_fusion_基础数据包.zip；输入文件：train_features.csv、test_features.csv；参考基线：baseline_predictions.csv。',
        algorithm: '平台 baseline 为贝叶斯决策级融合；学生可提交自研融合模型或权重分配策略。',
        uploads: '代码 .py；方案说明 .md/.txt/.docx；仿真过程文件 .zip/.csv/.json/.log/.txt；仿真结果 CSV，字段 frame_id、class_name、prediction_fused_prob。',
        versions: '平台 v1.0；Python 3.10+；基础题包 metadata.json；不强制安装 SUMO/CARLA/DTALite。',
        scoring: '按融合概率误差、字段完整性、方案可解释性、仿真过程可复现性和结果对比分析评分。'
    },
    {
        id: 'traffic_reconstruction',
        title: '交通流重构案例',
        module: 'prediction',
        scenario: '区域路网 OD 反推与路段交通流重构，基于观测流量恢复网络交通状态。',
        data: '基础仿真配置/题包：traffic_reconstruction_基础数据包.zip；输入文件：test_observed_counts.csv、input_link.csv、input_node.csv、input_zone.csv；基线：baseline_reconstruction.csv。',
        algorithm: '平台 baseline 为 DTALite/NEXTA ODME 与交通分配流程；学生可实现自研 OD 反推或路段流量修正算法。',
        uploads: '代码 .py；方案说明；DTALite/NEXTA 或自研仿真的过程文件；仿真结果 CSV，字段 link_id、time_interval、simulated_link_count。',
        versions: '平台 v1.0；Python 3.10+；DTALite/NEXTA 内置版；题包 metadata.json。',
        scoring: '按 RMSE/MAPE、路段守恒约束、过程文件可还原性、与 baseline 对比和报告质量评分。'
    },
    {
        id: 'traffic_prediction',
        title: '交通流预测案例',
        module: 'prediction',
        scenario: '短时交通流预测，基于历史流量、速度和时间特征预测测试样本总流量。',
        data: '基础题包：traffic_prediction_基础数据包.zip；输入文件：raw_traffic_flow.csv、train.csv、test_features.csv；模板：student_submission_template.csv。',
        algorithm: '平台 baseline 为 DecisionTreeRegressor(max_depth=10, random_state=42)；学生可使用任意监督学习或时序预测算法。',
        uploads: '代码 .py；方案说明；训练/预测过程日志或 notebook 导出文件；仿真/预测结果 CSV，字段 sample_id、prediction_total_flow。',
        versions: '平台 v1.0；Python 3.10+；scikit-learn 环境；题包 metadata.json。',
        scoring: '按 RMSE 主指标、MAE/MAPE/R2、特征处理说明、过程记录和 baseline 对比评分。'
    },
    {
        id: 'signal_optimization',
        title: '交通信号优化案例',
        module: 'control',
        scenario: '单点交叉口信号配时优化，在给定相位约束下输出周期与绿灯时间。',
        data: '基础仿真配置/题包：signal_optimization_基础数据包.zip；输入文件：scenario_config.json；基线：baseline_solution.csv。',
        algorithm: '平台 baseline 为 Webster 配时；学生可提交遗传算法、启发式搜索、强化学习或自研配时算法。',
        uploads: '代码 .py；方案说明；SUMO/算法运行过程文件；仿真结果 CSV/JSON，字段 cycle、phase_id、green_time。',
        versions: '平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+；题包 metadata.json。',
        scoring: '按绿灯时间误差、周期约束可行性、延误/排队改善、过程可复现性和方案说明评分。'
    },
    {
        id: 'path_guidance',
        title: '路径诱导案例',
        module: 'control',
        scenario: 'SiouxFalls 路网 OD 路径诱导，计算候选路径并降低拥堵路段负荷。',
        data: '基础仿真配置/题包：path_guidance_基础数据包.zip；输入文件：network_edges.csv、od_pairs.csv；基线：baseline_paths.csv。',
        algorithm: '平台 baseline 为最短路/KSP 路径诱导；学生可实现动态路径诱导、拥堵惩罚或 CAV 路径重分配策略。',
        uploads: '代码 .py；方案说明；SUMO 路径诱导过程文件或决策日志；仿真结果 CSV，字段 origin、destination、path、total_cost。',
        versions: '平台 v1.0；Python 3.10；SUMO 1.15+；题包 metadata.json。',
        scoring: '按路径合法性、平均成本比、拥堵路段缓解、CAV 改道记录和过程可复现性评分。'
    },
    {
        id: 'vehicle_speed_control',
        title: '车速控制案例',
        module: 'control',
        scenario: '车辆速度控制与跟驰稳定性评估，比较延误、速度波动和通行效率。',
        data: '基础仿真配置/题包：vehicle_speed_control_基础数据包.zip；输入文件：scenario.json；基线：baseline_metrics.csv。',
        algorithm: '平台 baseline 为 PID/规则控制；学生可提交 MPC、强化学习或自研速度控制策略。',
        uploads: '代码 .py；方案说明；SUMO/CARLA 控制过程记录；仿真结果 CSV，字段 algorithm、average_delay、avg_speed、speed_std、avg_accel、throughput。',
        versions: '平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+；可选 CARLA 0.9.13+。',
        scoring: '按平均延误、速度稳定性、吞吐量、安全约束、过程文件和结果分析评分。'
    },
    {
        id: 'coordination_control',
        title: '三层级协同优化案例',
        module: 'control',
        scenario: '信号优化、路径诱导、车速控制三层级协同，对比无协同、局部协同和全协同控制效果。',
        data: '基础仿真配置/题包：coordination_control_基础数据包.zip；输入文件：baseline_none.json、baseline_local.json、baseline_full.json；基线：baseline_full_timeseries.csv。',
        algorithm: '平台 baseline 为全协同控制；学生可组合信号配时、路径诱导和车速控制策略形成自研协同算法。',
        uploads: '代码 .py；方案说明；SUMO 协同控制过程文件与关键决策日志；仿真结果 CSV，字段 step、avg_speed、waiting_count。',
        versions: '平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+；题包 metadata.json。',
        scoring: '按平均速度 RMSE、等待车辆数、信号/路径/速度三层逻辑完整性、过程记录和 baseline 对比评分。'
    }
];

// DOM元素
const elements = {
    // 按钮
    createTaskBtn: document.getElementById('createTaskBtn'),
    assignTaskBtn: document.getElementById('assignTaskBtn'),
    progressBtn: document.getElementById('progressBtn'),
    refreshTaskBtn: document.getElementById('refreshTaskBtn'),
    studentMgmtBtn: document.getElementById('studentMgmtBtn'),
    reportMgmtBtn: document.getElementById('reportMgmtBtn'),
    helpBtn: document.getElementById('helpBtn'),
    logoutBtn: document.getElementById('logoutBtn'),
    
    // 统计数据
    totalTasks: document.getElementById('totalTasks'),
    activeTasks: document.getElementById('activeTasks'),
    completedTasks: document.getElementById('completedTasks'),
    overdueTasks: document.getElementById('overdueTasks'),
    
    // 筛选器
    statusFilter: document.getElementById('statusFilter'),
    moduleFilter: document.getElementById('moduleFilter'),
    
    // 视图控制
    viewBtns: document.querySelectorAll('.view-btn'),
    taskList: document.getElementById('taskList'),
    
    // 模态框
    createTaskModal: document.getElementById('createTaskModal'),
    assignTaskModal: document.getElementById('assignTaskModal'),
    progressModal: document.getElementById('progressModal'),
    
    // 表单
    createTaskForm: document.getElementById('createTaskForm'),
    taskCaseGrid: document.getElementById('taskCaseGrid'),
    taskCaseDetail: document.getElementById('taskCaseDetail'),
    selectTask: document.getElementById('selectTask'),
    studentList: document.getElementById('studentList'),
    progressDetails: document.getElementById('progressDetails')
};

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    // 检查登录状态
    var token = localStorage.getItem('token');
    if (!token) {
        window.location.href = '../登录界面/login.html';
        return;
    }

    // 检查用户权限
    const userRole = localStorage.getItem('userRole');
    if (userRole === 'student') {
        showPermissionDeniedPage();
        return;
    }

    // 初始化云端平台连接检测
    if (window.CloudStatusChecker) {
        window.CloudStatusChecker.createCloudStatusChecker({
            dotElement: document.getElementById('cloudStatusDot'),
            textElement: document.getElementById('cloudStatusText'),
            autoStart: true
        });
    }

    loadTasks();
    loadStudents();
    renderTaskCases();
    initializeEventListeners();
});

// 从后端加载任务列表
async function loadTasks() {
    try {
        var resp = await fetch(API_BASE + '/tasks', { headers: authHeaders() });
        if (resp.status === 401) { localStorage.removeItem('token'); window.location.href = '../登录界面/login.html'; return; }
        if (!resp.ok) throw new Error('加载任务失败');
        var data = await resp.json();
        tasks = data.map(function(t) {
            // 映射后端字段到前端字段
            var status = t.status || 'draft';
            if (status === 'published') status = 'active';
            if (status === 'closed') status = 'completed';
            // 检查是否逾期
            if (status === 'active' && t.deadline && new Date(t.deadline) < new Date()) status = 'overdue';
            var moduleId = t.module_id || t.module || '';
            return {
                id: t.id,
                title: t.title,
                description: t.description || '',
                module: moduleId,
                moduleName: getModuleName(moduleId),
                deadline: t.deadline ? t.deadline.split('T')[0] : '',
                status: status,
                createdAt: t.created_at ? t.created_at.split('T')[0] : '',
                assignedStudents: []
            };
        });
    } catch (e) {
        console.error('加载任务失败:', e);
        tasks = [];
    }
    updateStatistics();
    renderTaskList();
    updateTaskSelect();
}

// 从后端加载学生列表
async function loadStudents() {
    try {
        var resp = await fetch(API_BASE + '/users?role=student', { headers: authHeaders() });
        if (!resp.ok) throw new Error('加载学生失败');
        var data = await resp.json();
        students = data.map(function(u) {
            return { id: u.id, name: u.username, class: u.class_name || '', completedTasks: 0, totalTasks: 0 };
        });
    } catch (e) {
        console.error('加载学生列表失败:', e);
        students = [];
    }
    renderStudentList();
}

async function syncLatestCloudData() {
    try {
        var resp = await fetch(API_BASE + '/sync/pull', {
            method: 'POST',
            headers: authHeaders()
        });
        if (resp.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '../登录界面/login.html';
            return null;
        }
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('云端同步失败，回退为本地刷新:', e);
        return null;
    }
}

function setRefreshState(refreshing) {
    if (!elements.refreshTaskBtn) return;
    elements.refreshTaskBtn.disabled = refreshing;
    elements.refreshTaskBtn.classList.toggle('spinning', refreshing);
}

async function refreshTaskManagementData() {
    setRefreshState(true);
    try {
        var syncResult = await syncLatestCloudData();
        await Promise.all([loadTasks(), loadStudents()]);
        if (syncResult && syncResult.success) {
            showNotification('已刷新最新任务数据', 'success');
        } else if (syncResult && syncResult.errors && syncResult.errors.length > 0) {
            showNotification('本地列表已刷新，部分云端数据同步失败', 'warning');
        } else {
            showNotification('任务列表已刷新', 'success');
        }
    } catch (error) {
        console.error('刷新任务数据失败:', error);
        showNotification('刷新失败: ' + error.message, 'error');
    } finally {
        setRefreshState(false);
    }
}

// 事件监听器初始化
function initializeEventListeners() {
    // 主要按钮事件
    elements.createTaskBtn.addEventListener('click', showCreateTaskModal);
    elements.assignTaskBtn.addEventListener('click', showAssignTaskModal);
    elements.progressBtn.addEventListener('click', showProgressModal);
    if (elements.refreshTaskBtn) elements.refreshTaskBtn.addEventListener('click', refreshTaskManagementData);
    elements.studentMgmtBtn.addEventListener('click', navigateToStudentManagement);
    elements.reportMgmtBtn.addEventListener('click', navigateToReportManagement);
    elements.helpBtn.addEventListener('click', navigateToHelpDocumentation);
    elements.logoutBtn.addEventListener('click', handleLogout);
    
    // 筛选器事件
    elements.statusFilter.addEventListener('change', filterTasks);
    elements.moduleFilter.addEventListener('change', filterTasks);
    
    // 视图切换事件
    elements.viewBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            switchView(this.dataset.view);
        });
    });
    
    // 模态框关闭事件
    setupModalEvents();
    
    // 表单提交事件
    elements.createTaskForm.addEventListener('submit', handleCreateTask);
    document.getElementById('confirmAssignBtn').addEventListener('click', handleAssignTask);
}

function escHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function renderTaskCases() {
    if (!elements.taskCaseGrid) return;
    elements.taskCaseGrid.innerHTML = TASK_CASES.map(function(item) {
        return '<button type="button" class="task-case-card" data-case-id="' + escHtml(item.id) + '">'
            + '<strong>' + escHtml(item.title) + '</strong>'
            + '<span>场景：' + escHtml(item.scenario) + '</span>'
            + '<span>版本：' + escHtml(item.versions) + '</span>'
            + '</button>';
    }).join('');
    elements.taskCaseGrid.querySelectorAll('.task-case-card').forEach(function(card) {
        card.addEventListener('click', function() {
            selectTaskCase(this.dataset.caseId);
        });
    });
}

function buildTaskDescription(taskCase) {
    return [
        '【实验场景】' + taskCase.scenario,
        '【基础仿真配置/数据】' + taskCase.data,
        '【采用算法】' + taskCase.algorithm,
        '【需要上传】' + taskCase.uploads,
        '【软件版本】' + taskCase.versions
    ].join('\n');
}

function renderTaskCaseDetail(taskCase) {
    if (!elements.taskCaseDetail) return;
    if (!taskCase) {
        elements.taskCaseDetail.innerHTML = '<div class="empty-case-tip">请选择一个案例，平台会自动填充场景、数据、算法、上传要求和软件版本。</div>';
        return;
    }
    elements.taskCaseDetail.innerHTML = '<h4>' + escHtml(taskCase.title) + '</h4>'
        + '<div class="case-detail-grid">'
        + '<div class="case-detail-item"><b>场景</b><span>' + escHtml(taskCase.scenario) + '</span></div>'
        + '<div class="case-detail-item"><b>数据/配置</b><span>' + escHtml(taskCase.data) + '</span></div>'
        + '<div class="case-detail-item"><b>算法</b><span>' + escHtml(taskCase.algorithm) + '</span></div>'
        + '<div class="case-detail-item"><b>上传内容</b><span>' + escHtml(taskCase.uploads) + '</span></div>'
        + '<div class="case-detail-item"><b>软件版本</b><span>' + escHtml(taskCase.versions) + '</span></div>'
        + '</div>';
}

function selectTaskCase(caseId) {
    var taskCase = TASK_CASES.find(function(item) { return item.id === caseId; });
    if (!taskCase) return;
    selectedTaskCaseId = caseId;
    if (elements.taskCaseGrid) {
        elements.taskCaseGrid.querySelectorAll('.task-case-card').forEach(function(card) {
            card.classList.toggle('active', card.dataset.caseId === caseId);
        });
    }
    document.getElementById('taskTitle').value = taskCase.title;
    document.getElementById('taskDescription').value = buildTaskDescription(taskCase);
    document.getElementById('taskModule').value = taskCase.module;
    var scoring = document.getElementById('taskScoring');
    if (scoring) scoring.value = taskCase.scoring;
    renderTaskCaseDetail(taskCase);
}

// 模态框事件设置
function setupModalEvents() {
    // 创建任务模态框
    document.getElementById('closeCreateModal').addEventListener('click', hideCreateTaskModal);
    document.getElementById('cancelCreateBtn').addEventListener('click', hideCreateTaskModal);
    document.getElementById('confirmCreateBtn').addEventListener('click', handleCreateTask);
    
    // 分配任务模态框
    document.getElementById('closeAssignModal').addEventListener('click', hideAssignTaskModal);
    document.getElementById('cancelAssignBtn').addEventListener('click', hideAssignTaskModal);
    
    // 进度查看模态框
    document.getElementById('closeProgressModal').addEventListener('click', hideProgressModal);
    document.getElementById('closeProgressBtn').addEventListener('click', hideProgressModal);
    document.getElementById('exportProgressBtn').addEventListener('click', exportProgress);
    
    // 点击模态框背景关闭
    [elements.createTaskModal, elements.assignTaskModal, elements.progressModal].forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('show');
            }
        });
    });
}

// 显示创建任务模态框
function showCreateTaskModal() {
    elements.createTaskModal.classList.add('show');
    // 设置默认截止日期为一周后
    const nextWeek = new Date();
    nextWeek.setDate(nextWeek.getDate() + 7);
    document.getElementById('taskDeadline').value = nextWeek.toISOString().split('T')[0];
    selectTaskCase(selectedTaskCaseId || TASK_CASES[0].id);
}

// 隐藏创建任务模态框
function hideCreateTaskModal() {
    elements.createTaskModal.classList.remove('show');
    elements.createTaskForm.reset();
    selectedTaskCaseId = null;
    if (elements.taskCaseGrid) {
        elements.taskCaseGrid.querySelectorAll('.task-case-card').forEach(function(card) {
            card.classList.remove('active');
        });
    }
    renderTaskCaseDetail(null);
}

// 处理创建任务
async function handleCreateTask(e) {
    e.preventDefault();
    
    var title = document.getElementById('taskTitle').value;
    var description = document.getElementById('taskDescription').value;
    var module = document.getElementById('taskModule').value;
    var deadline = document.getElementById('taskDeadline').value;
    var deadlineValue = deadline ? (deadline + 'T23:59:00') : null;
    var scoring = document.getElementById('taskScoring') ? document.getElementById('taskScoring').value : '';

    try {
        var resp = await fetch(API_BASE + '/tasks', {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                title: title,
                description: description,
                module_id: module,
                deadline: deadlineValue,
                scoring_criteria: scoring
            })
        });
        if (!resp.ok) {
            var err = await resp.json().catch(function() { return null; });
            throw new Error((err && err.detail && err.detail.message) || '创建任务失败');
        }
        var created = await resp.json();
        if (created && created.id) {
            var publishResp = await fetch(API_BASE + '/tasks/' + created.id + '/publish', {
                method: 'POST',
                headers: authHeaders()
            });
            if (!publishResp.ok) {
                var publishErr = await publishResp.json().catch(function() { return null; });
                throw new Error((publishErr && publishErr.detail && publishErr.detail.message) || '任务已创建，但下发失败');
            }
        }
        hideCreateTaskModal();
        showNotification('任务已创建并下发', 'success');
        loadTasks();
    } catch (error) {
        showNotification(error.message || '创建/下发任务失败', 'error');
    }
}

// 显示分配任务模态框
function showAssignTaskModal() {
    elements.assignTaskModal.classList.add('show');
    updateTaskSelect();
    renderStudentList();
}

// 隐藏分配任务模态框
function hideAssignTaskModal() {
    elements.assignTaskModal.classList.remove('show');
    elements.selectTask.value = '';
    // 清除学生选择
    document.querySelectorAll('#studentList input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
}

// 处理任务分配
function handleAssignTask() {
    const taskId = parseInt(elements.selectTask.value);
    const selectedStudents = Array.from(document.querySelectorAll('#studentList input[type="checkbox"]:checked'))
        .map(cb => cb.value);
    
    if (!taskId || selectedStudents.length === 0) {
        showNotification('请选择任务和学生', 'error');
        return;
    }
    
    const task = tasks.find(t => t.id === taskId);
    if (task) {
        // 合并学生列表，避免重复
        const newStudents = selectedStudents.filter(s => !task.assignedStudents.includes(s));
        task.assignedStudents.push(...newStudents);
        
        renderTaskList();
        hideAssignTaskModal();
        showNotification(`任务已分配给 ${selectedStudents.length} 名学生`, 'success');
    }
}

// 显示进度查看模态框
function showProgressModal() {
    elements.progressModal.classList.add('show');
    renderProgressDetails();
}

// 隐藏进度查看模态框
function hideProgressModal() {
    elements.progressModal.classList.remove('show');
}

// 渲染进度详情
function renderProgressDetails() {
    const progressData = calculateProgress();
    
    elements.progressDetails.innerHTML = `
        <div class="progress-item">
            <span class="progress-label">总任务数</span>
            <span class="progress-value">${progressData.total}</span>
        </div>
        <div class="progress-item">
            <span class="progress-label">进行中任务</span>
            <span class="progress-value">${progressData.active}</span>
        </div>
        <div class="progress-item">
            <span class="progress-label">已完成任务</span>
            <span class="progress-value">${progressData.completed}</span>
        </div>
        <div class="progress-item">
            <span class="progress-label">逾期任务</span>
            <span class="progress-value" style="color: #f56c6c;">${progressData.overdue}</span>
        </div>
        <div class="progress-item">
            <span class="progress-label">完成率</span>
            <span class="progress-value">${progressData.completionRate}%</span>
        </div>
        <div class="progress-item">
            <span class="progress-label">平均分配学生数</span>
            <span class="progress-value">${progressData.avgStudents}</span>
        </div>
    `;
}

// 导出进度报告
function exportProgress() {
    const progressData = calculateProgress();
    const reportContent = `
教学任务管理进度报告
生成时间: ${new Date().toLocaleString()}

统计数据:
- 总任务数: ${progressData.total}
- 进行中任务: ${progressData.active}
- 已完成任务: ${progressData.completed}
- 逾期任务: ${progressData.overdue}
- 完成率: ${progressData.completionRate}%
- 平均分配学生数: ${progressData.avgStudents}

任务详情:
${tasks.map(task => `
- ${task.title}
  状态: ${getStatusText(task.status)}
  截止日期: ${task.deadline}
  分配学生: ${task.assignedStudents.join(', ') || '未分配'}
`).join('')}
    `;
    
    // 创建下载链接
    const blob = new Blob([reportContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `任务进度报告_${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showNotification('报告导出成功！', 'success');
}

// 切换视图
function switchView(view) {
    currentView = view;
    elements.viewBtns.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });
    renderTaskList();
}

// 筛选任务
function filterTasks() {
    renderTaskList();
}

// 渲染任务列表
function renderTaskList() {
    const statusFilter = elements.statusFilter.value;
    const moduleFilter = elements.moduleFilter.value;
    
    let filteredTasks = tasks.filter(task => {
        const statusMatch = statusFilter === 'all' || task.status === statusFilter;
        const moduleMatch = moduleFilter === 'all' || task.module === moduleFilter;
        return statusMatch && moduleMatch;
    });
    
    const taskListHTML = filteredTasks.map(task => `
        <div class="task-item ${currentView === 'grid' ? 'grid-view' : ''}">
            <div class="task-header">
                <h3 class="task-title">${task.title}</h3>
                <span class="task-status ${task.status}">${getStatusText(task.status)}</span>
            </div>
            <p class="task-description">${task.description}</p>
            <div class="task-meta">
                <span class="task-module">${task.moduleName}</span>
                <span class="task-deadline">截止: ${task.deadline}</span>
            </div>
            <div class="task-meta" style="margin-top: 0.5rem;">
                <span>分配学生: ${task.assignedStudents.length > 0 ? task.assignedStudents.join(', ') : '未分配'}</span>
            </div>
        </div>
    `).join('');
    
    elements.taskList.innerHTML = taskListHTML || '<div style="text-align: center; color: #999; padding: 2rem;">暂无任务数据</div>';
}

// 渲染学生列表
function renderStudentList() {
    const studentListHTML = students.map(student => `
        <div class="student-item">
            <input type="checkbox" id="student_${student.id}" value="${student.name}">
            <label for="student_${student.id}">
                ${student.name} (${student.class}) - 完成率: ${Math.round(student.completedTasks / student.totalTasks * 100)}%
            </label>
        </div>
    `).join('');
    
    elements.studentList.innerHTML = studentListHTML;
}

// 更新任务选择下拉框
function updateTaskSelect() {
    const activeTasks = tasks.filter(task => task.status === 'active');
    const optionsHTML = activeTasks.map(task => 
        `<option value="${task.id}">${task.title}</option>`
    ).join('');
    
    elements.selectTask.innerHTML = '<option value="">请选择要分配的任务</option>' + optionsHTML;
}

// 更新统计数据
function updateStatistics() {
    const stats = calculateProgress();
    
    elements.totalTasks.textContent = stats.total;
    elements.activeTasks.textContent = stats.active;
    elements.completedTasks.textContent = stats.completed;
    elements.overdueTasks.textContent = stats.overdue;
}

// 计算进度数据
function calculateProgress() {
    const total = tasks.length;
    const active = tasks.filter(t => t.status === 'active').length;
    const completed = tasks.filter(t => t.status === 'completed').length;
    const overdue = tasks.filter(t => t.status === 'overdue').length;
    const completionRate = total > 0 ? Math.round(completed / total * 100) : 0;
    const totalAssignments = tasks.reduce((sum, task) => sum + task.assignedStudents.length, 0);
    const avgStudents = total > 0 ? Math.round(totalAssignments / total * 10) / 10 : 0;
    
    return { total, active, completed, overdue, completionRate, avgStudents };
}

// 获取状态文本
function getStatusText(status) {
    const statusMap = {
        'active': '进行中',
        'completed': '已完成',
        'overdue': '逾期'
    };
    return statusMap[status] || status;
}

// 获取模块名称
function getModuleName(moduleCode) {
    const moduleMap = {
        'simulation': '仿真实验教学',
        'data': '多源数据采集与融合',
        'prediction': '交通流重构与预测',
        'control': '三层级协同优化控制',
        'integration': '车路协同虚实结合仿真'
    };
    return moduleMap[moduleCode] || moduleCode;
}

// 导航到学生管理
function navigateToStudentManagement() {
    try {
        console.log('开始导航到学生管理页面');
        
        // 优先使用父页面的导航函数（如果在iframe中）
        if (window.parent && window.parent !== window && typeof window.parent.navigateToStudentManagement === 'function') {
            console.log('使用父页面导航到学生管理');
            window.parent.navigateToStudentManagement();
        } else {
            // 如果不在iframe中，直接跳转
            console.log('直接跳转到学生管理页面');
            const targetUrl = '../1.2_学生信息管理/student_management.html';
            console.log('目标URL:', targetUrl);
            window.location.href = targetUrl;
        }
    } catch (error) {
        console.error('导航到学生管理页面失败:', error);
        showNotification('页面跳转失败: ' + error.message, 'error');
        
        // 备用跳转方案
        try {
            window.location.href = '../学生信息管理/student_management.html';
        } catch (backupError) {
            console.error('备用跳转也失败:', backupError);
        }
    }
}

// 导航到报告管理
function navigateToReportManagement() {
    try {
        console.log('开始导航到报告管理页面');
        
        // 优先使用父页面的导航函数（如果在iframe中）
        if (window.parent && window.parent !== window && typeof window.parent.navigateToReportManagement === 'function') {
            console.log('使用父页面导航到报告管理');
            window.parent.navigateToReportManagement();
        } else {
            // 如果不在iframe中，直接跳转
            console.log('直接跳转到报告管理页面');
            const targetUrl = '../1.3_实验报告管理/report_management.html';
            console.log('目标URL:', targetUrl);
            window.location.href = targetUrl;
        }
    } catch (error) {
        console.error('导航到报告管理页面失败:', error);
        showNotification('页面跳转失败: ' + error.message, 'error');
        
        // 备用跳转方案
        try {
            window.location.href = '../实验报告管理/report_management.html';
        } catch (backupError) {
            console.error('备用跳转也失败:', backupError);
        }
    }
}

// 导航到操作说明文档
function navigateToHelpDocumentation() {
    try {
        console.log('开始导航到操作说明页面');
        
        // 优先使用父页面的导航函数（如果在iframe中）
        if (window.parent && window.parent !== window && typeof window.parent.navigateToHelpDocumentation === 'function') {
            console.log('使用父页面导航到操作说明');
            window.parent.navigateToHelpDocumentation();
        } else {
            // 如果不在iframe中，直接跳转
            console.log('直接跳转到操作说明页面');
            const targetUrl = '../1.4_操作说明文档/help_documentation.html';
            console.log('目标URL:', targetUrl);
            window.location.href = targetUrl;
        }
    } catch (error) {
        console.error('导航到操作说明页面失败:', error);
        showNotification('页面跳转失败: ' + error.message, 'error');
        
        // 备用跳转方案
        try {
            window.location.href = '../操作说明文档/help_documentation.html';
        } catch (backupError) {
            console.error('备用跳转也失败:', backupError);
        }
    }
}



// 处理退出登录
function handleLogout() {
    if (confirm('确定要退出登录吗？')) {
        // 清除AI助手历史
        if (window.aiAssistant) {
            window.aiAssistant.clearHistoryAndMinimize();
        }

        localStorage.removeItem('userRole');
        localStorage.removeItem('username');
        localStorage.removeItem('loginTime');
        localStorage.removeItem('token');

        window.location.href = '../登录界面/login.html';
    }
}

// 显示通知
function showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        z-index: 2000;
        animation: slideInRight 0.3s ease;
    `;
    
    // 设置背景色
    const colors = {
        'success': '#67c23a',
        'error': '#f56c6c',
        'warning': '#e6a23c',
        'info': '#409EFF'
    };
    notification.style.backgroundColor = colors[type] || colors.info;
    
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // 3秒后自动移除
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// 显示权限拒绝页面
function showPermissionDeniedPage() {
    document.body.innerHTML = `
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            font-family: 'Microsoft YaHei', sans-serif;
            text-align: center;
            padding: 2rem;
        ">
            <div style="
                background: white;
                border-radius: 12px;
                padding: 3rem;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                max-width: 500px;
                width: 100%;
            ">
                <div style="font-size: 4rem; color: #f56c6c; margin-bottom: 1.5rem;">🚫</div>
                <h1 style="color: #333; margin-bottom: 1rem; font-size: 1.8rem;">访问受限</h1>
                <p style="color: #666; margin-bottom: 2rem; line-height: 1.6; font-size: 1.1rem;">
                    抱歉，您没有访问该功能的权限。<br>
                    教学任务管理功能仅限教师和管理员使用。
                </p>
                <div style="display: flex; gap: 1rem; justify-content: center;">
                    <button onclick="goBack()" style="
                        background: #2C5AA0;
                        color: white;
                        border: none;
                        padding: 0.75rem 2rem;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 1rem;
                        font-weight: 500;
                        transition: background-color 0.3s ease;
                    " onmouseover="this.style.backgroundColor='#1e3f73'" 
                       onmouseout="this.style.backgroundColor='#2C5AA0'">
                        返回上一页
                    </button>
                    <button onclick="goToStudentHome()" style="
                        background: #28a745;
                        color: white;
                        border: none;
                        padding: 0.75rem 2rem;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 1rem;
                        font-weight: 500;
                        transition: background-color 0.3s ease;
                    " onmouseover="this.style.backgroundColor='#1e7e34'" 
                       onmouseout="this.style.backgroundColor='#28a745'">
                        返回学生首页
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // 添加全局函数
    window.goBack = function() {
        history.back();
    };
    
    window.goToStudentHome = function() {
        window.location.href = '../../student.html';
    };
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            opacity: 0;
            transform: translateX(100%);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes slideOutRight {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
`;
document.head.appendChild(style);
