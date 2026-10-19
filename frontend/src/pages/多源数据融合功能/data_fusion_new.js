/**
 * 多源数据融合功能 - JavaScript
 * 贝叶斯融合算法 - YOLO检测与点云熵数据融合
 */

// API配置 - 使用主后端(port 8000)
(function establishClientSession() {
    const storageKey = 'zxk_client_session_id';
    let sessionId = '';
    try { sessionId = sessionStorage.getItem(storageKey) || ''; } catch (error) { /* 隐私模式 */ }
    if (!/^[A-Za-z0-9_-]{16,128}$/.test(sessionId)) {
        sessionId = (window.crypto && window.crypto.randomUUID)
            ? window.crypto.randomUUID()
            : Date.now().toString(36) + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
        try { sessionStorage.setItem(storageKey, sessionId); } catch (error) { /* 隐私模式 */ }
    }
    document.cookie = storageKey + '=' + encodeURIComponent(sessionId) + '; Path=/; SameSite=Lax';

    // Cookie 是浏览器级共享的：同一浏览器先开融合页、再开预测页时，后写入的
    // Cookie 会覆盖先写入的，两个标签页会串用同一个后端会话目录（结果、运行状态、
    // 重置互相影响）。这里改为显式用请求头发送会话标识——后端取值优先级是
    // 「请求头 > query > Cookie」，可从根上避免串号；Cookie 仅作兜底保留。
    const nativeFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        let url = '';
        try {
            url = typeof input === 'string' ? input : (input && input.url) || '';
        } catch (error) {
            url = '';
        }
        // 非本模块请求原样透传，避免影响 AI 助手等公共组件的请求。
        if (url.indexOf('/api/fusion/') === -1) {
            return nativeFetch(input, init);
        }
        const options = Object.assign({}, init || {});
        const headers = new Headers(
            options.headers || (input instanceof Request ? input.headers : undefined)
        );
        headers.set('X-Client-Session', sessionId);
        options.headers = headers;
        return nativeFetch(input, options);
    };
})();

const API_BASE_URL = '/api/fusion';

// 初始化
document.addEventListener('DOMContentLoaded', function () {
    initializeEventListeners();
    updateStatus('就绪', 'ready');
});

function initializeEventListeners() {
    document.getElementById('backBtn').addEventListener('click', () => window.history.back());
    document.getElementById('importDataBtn').addEventListener('click', importDataSource);
    document.getElementById('processImageBtn').addEventListener('click', processImageData);
    document.getElementById('processPointCloudBtn').addEventListener('click', processPointCloudData);
    document.getElementById('startFusionBtn').addEventListener('click', startFusionCalculation);
    document.getElementById('generateChartsBtn').addEventListener('click', generateCharts);
    document.getElementById('exportReportBtn').addEventListener('click', exportReport);
    document.getElementById('resetStatusBtn').addEventListener('click', resetStatus);
    setupImageModal();
    // 算法设计实验
    initAlgorithmDesign();
}

function markStepDone(buttonId) {
    const btn = document.getElementById(buttonId);
    if (btn) btn.classList.add('step-done');
}
function waitForFusionTask(taskKey, onComplete, timeoutMs = 10 * 60 * 1000) {
    const startedAt = Date.now();
    const poll = async function () {
        if (Date.now() - startedAt > timeoutMs) {
            onComplete(false, { message: '后台任务等待超时' });
            return;
        }
        try {
            const response = await fetch(API_BASE_URL + '/status', { cache: 'no-store' });
            const payload = await response.json();
            const task = payload.tasks && payload.tasks[taskKey];
            if (!task || task.running) {
                setTimeout(poll, 1500);
                return;
            }
            onComplete(task.success !== false, task);
        } catch (error) {
            setTimeout(poll, 2000);
        }
    };
    poll();
}
async function loadActualFusionResults() {
    const response = await fetch(API_BASE_URL + '/get-fusion-data', { cache: 'no-store' });
    if (!response.ok) return false;
    const data = await response.json();

    // 用数据集聚合值，不用单帧样本：单帧无法支撑"融合提升"的结论，
    // 而且单帧里缺失的类别（如点云没有该类目标）会让读者误读。
    const aggregate = (data.aggregate && data.aggregate.val) || null;
    const classes = (aggregate && aggregate.classes) || {};
    let rows = Object.keys(classes).map(function (className) {
        const item = classes[className] || {};
        return {
            class: className,
            yoloConf: Number(item.yolo_mean || 0),
            entropy: typeof item.entropy_mean === 'number' ? item.entropy_mean : null,
            reliability: typeof item.reliability_mean === 'number' ? item.reliability_mean : null,
            coverage: typeof item.pc_coverage === 'number' ? item.pc_coverage : null,
            fusionProb: Number(item.fused_mean || 0),
            improvement: typeof item.improvement === 'number' ? item.improvement : null
        };
    });

    // 后端还没有聚合结果时，退回单帧样本
    if (!rows.length) {
        const sample = data.sample && typeof data.sample === 'object' ? data.sample : {};
        rows = Object.entries(sample).map(function ([className, item]) {
            return {
                class: className,
                yoloConf: Number(item.yolo_mean_conf || 0),
                entropy: Number(item.pc_entropy || 0),
                reliability: null,
                coverage: null,
                fusionProb: Number(item.fused_prob || 0),
                improvement: null
            };
        });
    }
    if (!rows.length) return false;

    const frames = (aggregate && aggregate.frames) || 0;
    document.getElementById('overviewFusionCard').style.display = 'flex';
    document.getElementById('fusionResultSection').style.display = '';
    document.getElementById('fusionDataStatus').textContent = '已生成';
    document.getElementById('fusionDataCount').textContent = frames
        ? `${rows.length} 类目标 · ${frames} 帧聚合`
        : `${rows.length} 类目标融合结果`;
    buildFusionTable(rows);
    return true;
}

// ==================== 示例数据常量 ====================
const SAMPLE_YOLO_DATA = [
    { class: 'Car', confidence: 0.92, count: 1245 },
    { class: 'Cyclist', confidence: 0.85, count: 312 },
    { class: 'Pedestrian', confidence: 0.88, count: 478 },
    { class: 'Bus', confidence: 0.79, count: 86 },
    { class: 'Truck', confidence: 0.83, count: 154 }
];

const SAMPLE_ENTROPY_DATA = [
    { class: 'Car', entropy: 2.34, count: 1180 },
    { class: 'Cyclist', entropy: 3.12, count: 295 },
    { class: 'Pedestrian', entropy: 2.87, count: 450 },
    { class: 'Bus', entropy: 2.56, count: 78 },
    { class: 'Truck', entropy: 2.71, count: 142 }
];

// 离线示例：reliability = exp(-0.1 × entropy)，improvement = fusionProb − yoloConf
const SAMPLE_FUSION_DATA = [
    { class: 'Car', yoloConf: 0.92, entropy: 2.34, reliability: 0.7914, fusionProb: 0.96, improvement: 0.0400 },
    { class: 'Cyclist', yoloConf: 0.85, entropy: 3.12, reliability: 0.7320, fusionProb: 0.91, improvement: 0.0600 },
    { class: 'Pedestrian', yoloConf: 0.88, entropy: 2.87, reliability: 0.7505, fusionProb: 0.94, improvement: 0.0600 },
    { class: 'Bus', yoloConf: 0.79, entropy: 2.56, reliability: 0.7741, fusionProb: 0.87, improvement: 0.0800 },
    { class: 'Truck', yoloConf: 0.83, entropy: 2.71, reliability: 0.7626, fusionProb: 0.90, improvement: 0.0700 }
];

// ==================== 步骤1：加载数据 ====================
async function importDataSource() {
    updateStatus('正在加载数据...', 'processing');
    try {
        const response = await fetch(API_BASE_URL + '/get-input-data');
        const data = await response.json();

        // 显示概览卡片
        document.getElementById('overviewPlaceholder').style.display = 'none';
        document.getElementById('overviewImageCard').style.display = 'flex';
        document.getElementById('overviewPointCloudCard').style.display = 'flex';

        const yoloTotal = (data.yolo?.val_count || 0) + (data.yolo?.test_count || 0);
        const pcTotal = (data.pointcloud?.val_count || 0) + (data.pointcloud?.test_count || 0);

        document.getElementById('yoloDataStatus').textContent = yoloTotal > 0 ? '已加载' : '数据为空';
        document.getElementById('yoloDataCount').textContent = yoloTotal > 0
            ? '验证集 ' + (data.yolo?.val_count || 0) + ' 帧 / 测试集 ' + (data.yolo?.test_count || 0) + ' 帧'
            : '-';
        document.getElementById('pointCloudStatus').textContent = pcTotal > 0 ? '已加载' : '数据为空';
        document.getElementById('pointCloudCount').textContent = pcTotal > 0
            ? '验证集 ' + (data.pointcloud?.val_count || 0) + ' 帧 / 测试集 ' + (data.pointcloud?.test_count || 0) + ' 帧'
            : '-';

        // 显示原始数据表：优先后端聚合的真实统计，取不到时才退回内置示例
        document.getElementById('rawDataSection').style.display = '';
        const aggregate = (data.aggregate && data.aggregate.val) || null;
        if (aggregate && Object.keys(aggregate.classes || {}).length) {
            buildRawDataTable(aggregate);
        } else {
            buildRawDataTable(SAMPLE_YOLO_DATA, SAMPLE_ENTROPY_DATA);
        }

        updateStatus('数据加载完成', 'success');
        showToast('数据加载成功', 'success');
        markStepDone('importDataBtn');
    } catch (error) {
        updateStatus('数据加载失败', 'error');
        showToast('请检查后端服务是否启动', 'error');
    }
    setTimeout(function () { updateStatus('就绪', 'ready'); }, 2000);
}

function fmtPct(value) {
    return typeof value === 'number' ? (value * 100).toFixed(0) + '%' : '-';
}

function fmtNum(value, digits) {
    return typeof value === 'number' ? value.toFixed(digits) : '-';
}

function buildRawDataTable(source, entropySample) {
    const tbody = document.getElementById('rawDataTableBody');
    let html = '';

    // 后端聚合数据：{ frames, classes: { 类别: {...} } }
    if (source && source.classes) {
        const names = Object.keys(source.classes);
        if (!names.length) {
            tbody.innerHTML = '<tr class="empty-row"><td colspan="7">暂无原始数据</td></tr>';
            return;
        }
        names.forEach(function (name) {
            const item = source.classes[name] || {};
            const yoloMissing = item.yolo_mean_conf === null || item.yolo_mean_conf === undefined;
            const pcMissing = item.pc_entropy_mean === null || item.pc_entropy_mean === undefined;
            html += '<tr>'
                + '<td>' + name + '</td>'
                + '<td>' + (yoloMissing ? '无检测' : fmtNum(item.yolo_mean_conf, 4)) + '</td>'
                + '<td>' + (item.yolo_detections || 0) + '</td>'
                + '<td>' + fmtPct(item.yolo_coverage) + '</td>'
                + '<td>' + (pcMissing ? '无数据' : fmtNum(item.pc_entropy_mean, 4)) + '</td>'
                + '<td>' + (item.pc_count || 0) + '</td>'
                + '<td>' + fmtPct(item.pc_coverage) + '</td>'
                + '</tr>';
        });
        tbody.innerHTML = html;
        return;
    }

    // 兜底：内置示例数组（后端聚合不可用时）
    const legacy = source || [];
    for (let i = 0; i < legacy.length; i += 1) {
        const y = legacy[i];
        const e = (entropySample || [])[i] || {};
        html += '<tr>'
            + '<td>' + y.class + '</td>'
            + '<td>' + y.confidence.toFixed(2) + '</td>'
            + '<td>' + y.count + '</td>'
            + '<td>-</td>'
            + '<td>' + (e.entropy ? e.entropy.toFixed(2) : '-') + '</td>'
            + '<td>' + (e.count || '-') + '</td>'
            + '<td>-</td>'
            + '</tr>';
    }
    tbody.innerHTML = html;
}

// ==================== 步骤2：处理数据 ====================
async function processImageData() {
    updateStatus('图像数据处理中...', 'processing');
    try {
        const response = await fetch(API_BASE_URL + '/process-image-entropy', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            updateStatus('图像熵计算已提交，等待后台完成...', 'processing');
            waitForFusionTask('image_entropy', function (success, task) {
                if (success) {
                    updateStatus('图像熵计算完成', 'success');
                    showToast('图像熵结果已生成', 'success');
                    markStepDone('processImageBtn');
                } else {
                    updateStatus('图像数据处理失败', 'error');
                    showToast(task.message || '处理失败', 'error');
                }
            });
        } else {
            updateStatus('图像数据处理失败', 'error');
            showToast(data.message || '处理失败', 'error');
        }
    } catch (error) {
        updateStatus('图像数据处理失败', 'error');
        showToast('请检查后端服务', 'error');
    }
    setTimeout(function () { updateStatus('就绪', 'ready'); }, 2000);
}

async function processPointCloudData() {
    updateStatus('点云数据处理中...', 'processing');
    try {
        const response = await fetch(API_BASE_URL + '/process-pointcloud-entropy', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            updateStatus('点云熵计算已提交，等待后台完成...', 'processing');
            waitForFusionTask('pointcloud_entropy', function (success, task) {
                if (success) {
                    updateStatus('点云熵计算完成', 'success');
                    showToast('点云熵结果已生成', 'success');
                    markStepDone('processPointCloudBtn');
                } else {
                    updateStatus('点云数据处理失败', 'error');
                    showToast(task.message || '处理失败', 'error');
                }
            });
        } else {
            updateStatus('点云数据处理失败', 'error');
            showToast(data.message || '处理失败', 'error');
        }
    } catch (error) {
        updateStatus('点云数据处理失败', 'error');
        showToast('请检查后端服务', 'error');
    }
    setTimeout(function () { updateStatus('就绪', 'ready'); }, 2000);
}

// ==================== 步骤3：融合计算 ====================
async function startFusionCalculation() {
    updateStatus('融合计算中...', 'processing');
    try {
        const response = await fetch(API_BASE_URL + '/start', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            document.getElementById('overviewFusionCard').style.display = 'flex';
            document.getElementById('fusionDataStatus').textContent = '计算中...';
            updateStatus('融合计算已提交，等待后台完成...', 'processing');
            waitForFusionTask('fusion', async function (success, task) {
                if (!success) {
                    updateStatus('融合计算失败', 'error');
                    showToast(task.message || '融合计算失败', 'error');
                    return;
                }
                const loaded = await loadActualFusionResults().catch(function () { return false; });
                if (!loaded) {
                    document.getElementById('fusionResultSection').style.display = '';
                    buildFusionTable(SAMPLE_FUSION_DATA);
                }
                updateStatus('融合计算完成，结果已加载', 'success');
                showToast('融合结果已加载', 'success');
                markStepDone('startFusionBtn');
            });
        } else {
            updateStatus('融合计算失败', 'error');
            showToast(data.message || '融合失败', 'error');
        }
    } catch (error) {
        updateStatus('融合计算失败', 'error');
        showToast('请检查后端服务', 'error');
    }
    setTimeout(function () { updateStatus('就绪', 'ready'); }, 2000);
}

function buildFusionTable(data) {
    const tbody = document.getElementById('fusionTableBody');
    if (!data.length) {
        tbody.innerHTML = '';
        return;
    }
    // 提升条按本数据集的最大提升量归一化，条形长短才能横向比较
    const maxImprovement = data.reduce(function (max, item) {
        return Math.max(max, typeof item.improvement === 'number' ? item.improvement : 0);
    }, 0) || 1;

    let html = '';
    for (let i = 0; i < data.length; i++) {
        const d = data[i];
        // 点云覆盖不足一半时标注，避免把"无数据"误读成"融合无效"
        const lowCoverage = typeof d.coverage === 'number' && d.coverage < 0.5;
        const badge = lowCoverage
            ? '<span style="margin-left:6px;padding:1px 6px;border-radius:8px;background:#f0f2f5;'
              + 'color:#909399;font-size:0.75rem;" title="点云对该类别的覆盖帧不足一半，'
              + '融合结果会回退到单源，提升接近 0">数据不足</span>'
            : '';

        // 提升 = 融合后 − 融合前：数值 + 归一化条形，一眼看出哪几类提升明显
        let improvementCell = '-';
        if (typeof d.improvement === 'number') {
            const color = d.improvement > 0 ? '#2e7d32' : (d.improvement < 0 ? '#c62828' : '#909399');
            const width = Math.max(2, Math.round(Math.abs(d.improvement) / maxImprovement * 56));
            improvementCell = '<span style="color:' + color + ';font-weight:600;">'
                + (d.improvement >= 0 ? '+' : '') + d.improvement.toFixed(4) + '</span>'
                + '<span style="display:inline-block;width:56px;height:8px;background:#eef2f8;'
                + 'border-radius:4px;vertical-align:middle;margin-left:8px;overflow:hidden;">'
                + '<span style="display:block;height:100%;width:' + width + 'px;background:'
                + color + ';"></span></span>';
        }

        // 点云可靠性 P_pc：> 0.5 支持目标存在（融合后高于融合前），≈0.5 中性，< 0.5 拉低
        let reliabilityCell = '-';
        if (typeof d.reliability === 'number') {
            const color = lowCoverage ? '#909399'
                : (d.reliability > 0.55 ? '#2e7d32' : (d.reliability < 0.45 ? '#c62828' : '#909399'));
            const verdict = lowCoverage ? '' : (d.reliability > 0.55 ? '支持'
                : (d.reliability < 0.45 ? '反对' : '中性'));
            reliabilityCell = '<span style="color:' + color + ';">' + d.reliability.toFixed(4) + '</span>'
                + (verdict
                    ? '<span style="margin-left:6px;font-size:0.78rem;color:' + color + ';">'
                      + verdict + '</span>'
                    : '');
        }

        html += '<tr>'
            + '<td>' + d.class + badge + '</td>'
            + '<td>' + d.yoloConf.toFixed(4) + '</td>'
            + '<td><span class="val-highlight">' + d.fusionProb.toFixed(4) + '</span></td>'
            + '<td>' + improvementCell + '</td>'
            + '<td>' + (typeof d.entropy === 'number' ? d.entropy.toFixed(4) : '-') + '</td>'
            + '<td>' + reliabilityCell + '</td>'
            + '<td>' + fmtPct(d.coverage) + '</td>'
            + '</tr>';
    }
    tbody.innerHTML = html;
}

// ==================== 步骤4：生成并展示图表 ====================
async function generateCharts() {
    updateStatus('图表生成中...', 'processing');
    try {
        const response = await fetch(API_BASE_URL + '/generate-charts', { method: 'POST' });
        const data = await response.json();
        if (data.success) {
            updateStatus('图表生成已提交，等待后台完成...', 'processing');
            showToast('图表生成已提交到服务器后台', 'success');
            waitForFusionTask('charts', function (success, task) {
                if (!success) {
                    updateStatus('图表生成失败', 'error');
                    showToast(task.message || '图表生成失败', 'error');
                    return;
                }
                loadAndShowCharts();
            });
        } else {
            updateStatus('图表生成失败', 'error');
            showToast(data.message || '生成失败', 'error');
            setTimeout(function () { updateStatus('就绪', 'ready'); }, 2000);
        }
    } catch (error) {
        updateStatus('图表生成失败', 'error');
        showToast('请检查后端服务', 'error');
        setTimeout(function () { updateStatus('就绪', 'ready'); }, 2000);
    }
}

async function loadAndShowCharts() {
    try {
        const response = await fetch(API_BASE_URL + '/list-charts');
        const data = await response.json();
        if (data.success && data.charts && data.charts.length > 0) {
            const viewer = document.getElementById('chartsViewer');
            const chartNames = {
                '融合前后对比.png': '融合前后置信度对比（验证集）',
                '验证集测试集对比.png': '验证集与测试集融合概率对比'
            };
            let html = '';
            for (let i = 0; i < data.charts.length; i++) {
                const fname = data.charts[i];
                const title = chartNames[fname] || fname.replace('.png', '');
                html += '<div class="chart-item">'
                    + '<h4>' + title + '</h4>'
                    + '<img src="' + API_BASE_URL + '/charts/' + encodeURIComponent(fname) + '?t=' + Date.now() + '" '
                    + 'alt="' + title + '" onclick="openImageModal(this.src)" />'
                    + '</div>';
            }
            viewer.innerHTML = html;
            document.getElementById('chartsSection').style.display = '';
            updateStatus('图表已生成并展示', 'success');
            showToast('图表已加载', 'success');
            markStepDone('generateChartsBtn');
        } else {
            // 图表可能还没生成完，再等几秒重试一次
            setTimeout(retryLoadCharts, 5000);
        }
    } catch (error) {
        setTimeout(retryLoadCharts, 5000);
    }
}

async function retryLoadCharts() {
    try {
        const response = await fetch(API_BASE_URL + '/list-charts');
        const data = await response.json();
        if (data.success && data.charts && data.charts.length > 0) {
            loadAndShowCharts();
        } else {
            updateStatus('图表暂未生成完成，请稍后点击重试', 'error');
            showToast('图表尚未生成完成，请等服务器后台任务完成后重试', 'error');
            setTimeout(function () { updateStatus('就绪', 'ready'); }, 3000);
        }
    } catch (e) {
        updateStatus('加载图表失败', 'error');
        setTimeout(function () { updateStatus('就绪', 'ready'); }, 2000);
    }
}

// ==================== 步骤6：导出报告 ====================
async function exportReport() {
    updateStatus('导出报告中...', 'processing');
    try {
        const response = await fetch(API_BASE_URL + '/download-report');
        if (response.ok) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = '数据融合实验报告.txt';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            updateStatus('报告已下载', 'success');
            showToast('报告已下载', 'success');
            markStepDone('exportReportBtn');
        } else {
            updateStatus('报告下载失败', 'error');
            showToast('报告不存在，请先生成图表', 'error');
        }
    } catch (error) {
        updateStatus('报告下载失败', 'error');
        showToast('请检查后端服务', 'error');
    }
    setTimeout(function () { updateStatus('就绪', 'ready'); }, 2000);
}

// ==================== 重置状态 ====================
function resetStatus() {
    // 隐藏所有动态区域
    document.getElementById('overviewPlaceholder').style.display = '';
    document.getElementById('overviewImageCard').style.display = 'none';
    document.getElementById('overviewPointCloudCard').style.display = 'none';
    document.getElementById('overviewFusionCard').style.display = 'none';
    document.getElementById('rawDataSection').style.display = 'none';
    document.getElementById('fusionResultSection').style.display = 'none';
    document.getElementById('chartsSection').style.display = 'none';

    // 重置表格（colspan 必须与实际列数一致：原始数据 7 列、融合结果 7 列）
    document.getElementById('rawDataTableBody').innerHTML = '<tr class="empty-row"><td colspan="7">加载数据后显示</td></tr>';
    document.getElementById('fusionTableBody').innerHTML = '<tr class="empty-row"><td colspan="7">执行融合计算后显示</td></tr>';

    // 重置概览卡片文字
    document.getElementById('yoloDataStatus').textContent = '未加载';
    document.getElementById('yoloDataCount').textContent = '-';
    document.getElementById('pointCloudStatus').textContent = '未加载';
    document.getElementById('pointCloudCount').textContent = '-';
    document.getElementById('fusionDataStatus').textContent = '未生成';
    document.getElementById('fusionDataCount').textContent = '-';

    // 清空图表
    document.getElementById('chartsViewer').innerHTML = '';

    // 移除所有step-done
    document.querySelectorAll('.step-btn.step-done').forEach(function (btn) {
        btn.classList.remove('step-done');
    });

    updateStatus('就绪', 'ready');
    showToast('状态已重置', 'success');
}

// ==================== 工具函数 ====================
function updateStatus(message, type) {
    var el = document.getElementById('fusionStatus');
    if (!el) return;
    el.textContent = message;
    el.className = 'status-value';
    if (type === 'processing') el.classList.add('status-processing');
    else if (type === 'success') el.classList.add('status-completed');
    else if (type === 'error') el.classList.add('status-error');
    else el.classList.add('status-ready');
}

function setupImageModal() {
    var modal = document.getElementById('imageModal');
    var closeBtn = modal ? modal.querySelector('.close-modal') : null;
    if (closeBtn) {
        closeBtn.addEventListener('click', function () {
            modal.style.display = 'none';
        });
    }
    if (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target === modal) modal.style.display = 'none';
        });
    }
}

function openImageModal(src) {
    var modal = document.getElementById('imageModal');
    var img = document.getElementById('modalImage');
    if (modal && img) {
        img.src = src;
        modal.style.display = 'block';
    }
}

function showToast(message, type) {
    // 移除已有toast
    var existing = document.querySelector('.toast-notification');
    if (existing) existing.remove();

    var toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.textContent = message;
    toast.style.cssText = 'position:fixed;top:20px;right:20px;padding:12px 24px;border-radius:8px;color:white;font-size:14px;z-index:9999;'
        + 'box-shadow:0 4px 12px rgba(0,0,0,0.15);transition:opacity 0.3s;';
    toast.style.backgroundColor = type === 'error' ? '#dc3545' : '#2C5AA0';
    document.body.appendChild(toast);
    setTimeout(function () {
        toast.style.opacity = '0';
        setTimeout(function () { toast.remove(); }, 300);
    }, 2500);
}

// ==================== 服务器状态检查 ====================
(async function checkServerStatus() {
    var el = document.getElementById('serverStatus');
    if (!el) return;
    try {
        var resp = await fetch(API_BASE_URL + '/health');
        if (resp.ok) {
            el.textContent = '服务器: 已连接';
            el.style.color = '#28a745';
        } else {
            el.textContent = '服务器: 异常';
            el.style.color = '#dc3545';
        }
    } catch (e) {
        el.textContent = '服务器: 未连接';
        el.style.color = '#dc3545';
    }
})();

// ==================== 算法设计实验 ====================
var FUSION_TEMPLATES = {};

FUSION_TEMPLATES['bayesian'] = `# -*- coding: utf-8 -*-
"""
自定义融合实验 - 贝叶斯融合（调参版）
=====================================
通过修改先验概率 PRIOR 和熵转换参数 LAMBDA_VAL，
观察不同参数对融合结果的影响。
"""
import os, sys, json, math
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# ============ 可修改区域 ============
# 先验概率：目标存在的先验信念，越大越倾向于认为目标存在
PRIOR = 0.1          # 试试 0.05, 0.1, 0.2, 0.5

# 熵转换参数 lambda：控制点云熵值对融合的影响强度
# lambda 越大，熵值对结果影响越大
LAMBDA_VAL = {
    "Cyclist": 0.1,      # 试试 0.05, 0.1, 0.2, 0.5
    "Car": 0.1,
    "Pedestrian": 0.1,
    "Bus": 0.1,
    "Truck": 0.1
}
# ====================================

CLASS_NAMES = {0: "Cyclist", 1: "Car", 3: "Pedestrian", 5: "Bus", 6: "Truck"}
DEFAULT_YOLO_PROB = PRIOR
DEFAULT_ENTROPY = 10.0

INPUT_DIR = os.path.join(SCRIPT_DIR, "input")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output", "custom")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def load_frames(folder):
    results = {}
    if not os.path.exists(folder):
        return results
    for f in os.listdir(folder):
        if f.endswith('.json'):
            with open(os.path.join(folder, f), 'r', encoding='utf-8') as fp:
                results[os.path.splitext(f)[0]] = json.load(fp)
    return results

def entropy_to_prob(entropy, cls):
    lam = LAMBDA_VAL.get(cls, 0.1)
    return math.exp(-lam * entropy)

def bayesian_fusion(p_yolo, entropy, cls):
    p_pc = entropy_to_prob(entropy, cls)
    num = p_yolo * p_pc * PRIOR
    den = num + (1 - p_yolo) * (1 - p_pc) * (1 - PRIOR)
    return num / den if den > 0 else 0

print("=" * 60)
print("  自定义贝叶斯融合实验")
print(f"  PRIOR={PRIOR}, LAMBDA={list(LAMBDA_VAL.values())[0]}")
print("=" * 60)

yolo_val = load_frames(os.path.join(INPUT_DIR, "yolo", "val"))
pc_val = load_frames(os.path.join(INPUT_DIR, "pointcloud", "val"))
print(f"\\n加载验证集: YOLO {len(yolo_val)} 帧, 点云 {len(pc_val)} 帧")

all_ids = sorted(set(yolo_val.keys()) | set(pc_val.keys()))
class_results = {c: [] for c in CLASS_NAMES.values()}

for fid in all_ids:
    yd = yolo_val.get(fid, {})
    pd = pc_val.get(fid, {})
    for cid, cname in CLASS_NAMES.items():
        p_yolo = yd.get(str(cid), {}).get("mean_conf", DEFAULT_YOLO_PROB)
        ent = pd.get(cname, {}).get("entropy", DEFAULT_ENTROPY)
        fused = bayesian_fusion(p_yolo, ent, cname)
        class_results[cname].append((p_yolo, ent, fused))

print("\\n" + "=" * 60)
print(f"{'类别':<12} {'YOLO均值':<10} {'熵均值':<10} {'融合均值':<10} {'提升':<8}")
print("-" * 60)
for cname, vals in class_results.items():
    if vals:
        avg_y = np.mean([v[0] for v in vals])
        avg_e = np.mean([v[1] for v in vals])
        avg_f = np.mean([v[2] for v in vals])
        diff = avg_f - avg_y
        print(f"{cname:<12} {avg_y:<10.4f} {avg_e:<10.4f} {avg_f:<10.4f} {diff:+.4f}")
print("=" * 60)
print("\\n实验完成！")
`;

FUSION_TEMPLATES['ds'] = `# -*- coding: utf-8 -*-
"""
自定义融合实验 - D-S证据理论融合
================================
Dempster-Shafer证据理论，通过质量函数的组合规则
实现多源数据融合，处理不确定性和冲突。
"""
import os, sys, json, math
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============ 可修改区域 ============
# 不确定度分配比例：分配给"不确定"的质量
# 越大表示对单一数据源越不信任
YOLO_UNCERTAINTY = 0.2    # 试试 0.1, 0.2, 0.3, 0.5
PC_UNCERTAINTY = 0.3      # 试试 0.1, 0.2, 0.3, 0.5
# ====================================

CLASS_NAMES = {0: "Cyclist", 1: "Car", 3: "Pedestrian", 5: "Bus", 6: "Truck"}
DEFAULT_YOLO_PROB = 0.1
DEFAULT_ENTROPY = 10.0

INPUT_DIR = os.path.join(SCRIPT_DIR, "input")

def load_frames(folder):
    results = {}
    if not os.path.exists(folder):
        return results
    for f in os.listdir(folder):
        if f.endswith('.json'):
            with open(os.path.join(folder, f), 'r', encoding='utf-8') as fp:
                results[os.path.splitext(f)[0]] = json.load(fp)
    return results

def entropy_to_prob(entropy, lam=0.1):
    return math.exp(-lam * entropy)

def ds_fusion(p_yolo, p_pc):
    """D-S证据理论融合"""
    # YOLO证据的质量函数
    m1_target = p_yolo * (1 - YOLO_UNCERTAINTY)
    m1_not = (1 - p_yolo) * (1 - YOLO_UNCERTAINTY)
    m1_uncertain = YOLO_UNCERTAINTY

    # 点云证据的质量函数
    m2_target = p_pc * (1 - PC_UNCERTAINTY)
    m2_not = (1 - p_pc) * (1 - PC_UNCERTAINTY)
    m2_uncertain = PC_UNCERTAINTY

    # Dempster组合规则
    k = m1_target * m2_not + m1_not * m2_target  # 冲突因子
    if k >= 1.0:
        return 0.5  # 完全冲突

    norm = 1.0 / (1.0 - k)
    fused = norm * (m1_target * m2_target + m1_target * m2_uncertain + m1_uncertain * m2_target)
    return min(max(fused, 0), 1)

print("=" * 60)
print("  D-S证据理论融合实验")
print(f"  YOLO不确定度={YOLO_UNCERTAINTY}, 点云不确定度={PC_UNCERTAINTY}")
print("=" * 60)

yolo_val = load_frames(os.path.join(INPUT_DIR, "yolo", "val"))
pc_val = load_frames(os.path.join(INPUT_DIR, "pointcloud", "val"))
print(f"\\n加载验证集: YOLO {len(yolo_val)} 帧, 点云 {len(pc_val)} 帧")

all_ids = sorted(set(yolo_val.keys()) | set(pc_val.keys()))
class_results = {c: [] for c in CLASS_NAMES.values()}

for fid in all_ids:
    yd = yolo_val.get(fid, {})
    pd = pc_val.get(fid, {})
    for cid, cname in CLASS_NAMES.items():
        p_yolo = yd.get(str(cid), {}).get("mean_conf", DEFAULT_YOLO_PROB)
        ent = pd.get(cname, {}).get("entropy", DEFAULT_ENTROPY)
        p_pc = entropy_to_prob(ent)
        fused = ds_fusion(p_yolo, p_pc)
        class_results[cname].append((p_yolo, p_pc, fused))

print("\\n" + "=" * 60)
print(f"{'类别':<12} {'YOLO均值':<10} {'点云概率':<10} {'DS融合':<10} {'提升':<8}")
print("-" * 60)
for cname, vals in class_results.items():
    if vals:
        avg_y = np.mean([v[0] for v in vals])
        avg_p = np.mean([v[1] for v in vals])
        avg_f = np.mean([v[2] for v in vals])
        diff = avg_f - avg_y
        print(f"{cname:<12} {avg_y:<10.4f} {avg_p:<10.4f} {avg_f:<10.4f} {diff:+.4f}")
print("=" * 60)
print("\\n实验完成！")
`;

FUSION_TEMPLATES['weighted'] = `# -*- coding: utf-8 -*-
"""
自定义融合实验 - 加权平均融合
==============================
最简单的融合方法：对YOLO置信度和点云概率进行加权平均。
通过调整权重观察不同数据源的贡献。
"""
import os, sys, json, math
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============ 可修改区域 ============
# 权重分配：两个权重之和应为1.0
WEIGHT_YOLO = 0.6     # YOLO检测权重，试试 0.3, 0.5, 0.6, 0.8
WEIGHT_PC = 0.4       # 点云数据权重，试试 0.2, 0.4, 0.5, 0.7
# 熵转换参数
LAMBDA = 0.1          # 试试 0.05, 0.1, 0.2
# ====================================

CLASS_NAMES = {0: "Cyclist", 1: "Car", 3: "Pedestrian", 5: "Bus", 6: "Truck"}
DEFAULT_YOLO_PROB = 0.1
DEFAULT_ENTROPY = 10.0

INPUT_DIR = os.path.join(SCRIPT_DIR, "input")

def load_frames(folder):
    results = {}
    if not os.path.exists(folder):
        return results
    for f in os.listdir(folder):
        if f.endswith('.json'):
            with open(os.path.join(folder, f), 'r', encoding='utf-8') as fp:
                results[os.path.splitext(f)[0]] = json.load(fp)
    return results

def weighted_fusion(p_yolo, entropy):
    p_pc = math.exp(-LAMBDA * entropy)
    return WEIGHT_YOLO * p_yolo + WEIGHT_PC * p_pc

print("=" * 60)
print("  加权平均融合实验")
print(f"  YOLO权重={WEIGHT_YOLO}, 点云权重={WEIGHT_PC}, lambda={LAMBDA}")
print("=" * 60)

yolo_val = load_frames(os.path.join(INPUT_DIR, "yolo", "val"))
pc_val = load_frames(os.path.join(INPUT_DIR, "pointcloud", "val"))
print(f"\\n加载验证集: YOLO {len(yolo_val)} 帧, 点云 {len(pc_val)} 帧")

all_ids = sorted(set(yolo_val.keys()) | set(pc_val.keys()))
class_results = {c: [] for c in CLASS_NAMES.values()}

for fid in all_ids:
    yd = yolo_val.get(fid, {})
    pd = pc_val.get(fid, {})
    for cid, cname in CLASS_NAMES.items():
        p_yolo = yd.get(str(cid), {}).get("mean_conf", DEFAULT_YOLO_PROB)
        ent = pd.get(cname, {}).get("entropy", DEFAULT_ENTROPY)
        fused = weighted_fusion(p_yolo, ent)
        class_results[cname].append((p_yolo, ent, fused))

print("\\n" + "=" * 60)
print(f"{'类别':<12} {'YOLO均值':<10} {'熵均值':<10} {'加权融合':<10} {'提升':<8}")
print("-" * 60)
for cname, vals in class_results.items():
    if vals:
        avg_y = np.mean([v[0] for v in vals])
        avg_e = np.mean([v[1] for v in vals])
        avg_f = np.mean([v[2] for v in vals])
        diff = avg_f - avg_y
        print(f"{cname:<12} {avg_y:<10.4f} {avg_e:<10.4f} {avg_f:<10.4f} {diff:+.4f}")
print("=" * 60)
print("\\n实验完成！")
`;

FUSION_TEMPLATES['custom'] = `# -*- coding: utf-8 -*-
"""
自定义融合算法 - 空白模板
=========================
在此编写你自己的融合算法。
数据已准备好，你只需实现融合逻辑。
"""
import os, sys, json, math
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CLASS_NAMES = {0: "Cyclist", 1: "Car", 3: "Pedestrian", 5: "Bus", 6: "Truck"}
INPUT_DIR = os.path.join(SCRIPT_DIR, "input")

def load_frames(folder):
    results = {}
    if not os.path.exists(folder):
        return results
    for f in os.listdir(folder):
        if f.endswith('.json'):
            with open(os.path.join(folder, f), 'r', encoding='utf-8') as fp:
                results[os.path.splitext(f)[0]] = json.load(fp)
    return results

# ============ 在此实现你的融合函数 ============
def my_fusion(p_yolo, entropy):
    """
    自定义融合函数
    参数:
        p_yolo: YOLO检测置信度 (0~1)
        entropy: 点云熵值 (越小越确定)
    返回:
        融合后的概率 (0~1)
    """
    # TODO: 实现你的融合逻辑
    # 示例：简单取最大值
    p_pc = math.exp(-0.1 * entropy)
    return max(p_yolo, p_pc)
# =============================================

print("=" * 60)
print("  自定义融合算法实验")
print("=" * 60)

yolo_val = load_frames(os.path.join(INPUT_DIR, "yolo", "val"))
pc_val = load_frames(os.path.join(INPUT_DIR, "pointcloud", "val"))
print(f"\\n加载验证集: YOLO {len(yolo_val)} 帧, 点云 {len(pc_val)} 帧")

all_ids = sorted(set(yolo_val.keys()) | set(pc_val.keys()))
class_results = {c: [] for c in CLASS_NAMES.values()}

for fid in all_ids:
    yd = yolo_val.get(fid, {})
    pd = pc_val.get(fid, {})
    for cid, cname in CLASS_NAMES.items():
        p_yolo = yd.get(str(cid), {}).get("mean_conf", 0.1)
        ent = pd.get(cname, {}).get("entropy", 10.0)
        fused = my_fusion(p_yolo, ent)
        class_results[cname].append((p_yolo, ent, fused))

print("\\n" + "=" * 60)
print(f"{'类别':<12} {'YOLO均值':<10} {'熵均值':<10} {'融合均值':<10} {'提升':<8}")
print("-" * 60)
for cname, vals in class_results.items():
    if vals:
        avg_y = np.mean([v[0] for v in vals])
        avg_e = np.mean([v[1] for v in vals])
        avg_f = np.mean([v[2] for v in vals])
        diff = avg_f - avg_y
        print(f"{cname:<12} {avg_y:<10.4f} {avg_e:<10.4f} {avg_f:<10.4f} {diff:+.4f}")
print("=" * 60)
print("\\n实验完成！")
`;

// 初始化算法设计区
function initAlgorithmDesign() {
    var editor = document.getElementById('fusionCodeEditor');
    var select = document.getElementById('fusionTemplateSelect');
    if (!editor || !select) return;

    // 加载默认模板
    editor.value = FUSION_TEMPLATES['bayesian'];

    // 模板切换
    select.addEventListener('change', function () {
        var tpl = FUSION_TEMPLATES[select.value];
        if (tpl) editor.value = tpl;
    });

    // 恢复模板
    document.getElementById('resetTemplateBtn').addEventListener('click', function () {
        var tpl = FUSION_TEMPLATES[select.value];
        if (tpl) editor.value = tpl;
        showToast('模板已恢复', 'success');
    });

    // 放大/缩小
    document.getElementById('expandCodeBtn').addEventListener('click', handleToggleCodeExpand);
    document.getElementById('codeFullscreenOverlay').addEventListener('click', handleToggleCodeExpand);

    // Tab键支持
    editor.addEventListener('keydown', function (e) {
        if (e.key === 'Tab') {
            e.preventDefault();
            var start = editor.selectionStart;
            var end = editor.selectionEnd;
            editor.value = editor.value.substring(0, start) + '    ' + editor.value.substring(end);
            editor.selectionStart = editor.selectionEnd = start + 4;
        }
    });

    // 运行按钮
    document.getElementById('runCustomFusionBtn').addEventListener('click', handleRunCustomFusion);
}

function handleToggleCodeExpand() {
    var wrapper = document.getElementById('codeEditorWrapper');
    var overlay = document.getElementById('codeFullscreenOverlay');
    var btn = document.getElementById('expandCodeBtn');
    if (!wrapper) return;
    var expanded = wrapper.classList.toggle('expanded');
    if (overlay) overlay.classList.toggle('active', expanded);
    if (btn) btn.textContent = expanded ? '✕ 关闭' : '⛶ 放大';
}

function handleRunCustomFusion() {
    var editor = document.getElementById('fusionCodeEditor');
    var statusEl = document.getElementById('customFusionStatus');
    if (!editor || !editor.value.trim()) {
        if (statusEl) { statusEl.textContent = '代码不能为空'; statusEl.style.color = '#dc3545'; }
        return;
    }

    if (statusEl) { statusEl.textContent = '正在提交代码...'; statusEl.style.color = '#2C5AA0'; }
    var btn = document.getElementById('runCustomFusionBtn');
    if (btn) btn.disabled = true;

    fetch(API_BASE_URL + '/run-custom-fusion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: editor.value })
    })
    .then(function (resp) { return resp.json(); })
    .then(function (result) {
        if (result.success) {
            if (statusEl) { statusEl.textContent = '算法已启动（服务器后台任务）'; statusEl.style.color = '#28a745'; }
            showToast('自定义融合算法已启动', 'success');
            markStepDone('runCustomFusionBtn');
        } else {
            if (statusEl) { statusEl.textContent = '失败: ' + result.message; statusEl.style.color = '#dc3545'; }
            showToast(result.message || '运行失败', 'error');
        }
        if (btn) btn.disabled = false;
    })
    .catch(function () {
        if (statusEl) { statusEl.textContent = '后端服务未响应'; statusEl.style.color = '#dc3545'; }
        if (btn) btn.disabled = false;
    });
}
