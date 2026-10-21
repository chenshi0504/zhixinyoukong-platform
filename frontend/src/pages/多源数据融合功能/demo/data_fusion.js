/**
 * 多源数据融合功能 - JavaScript
 * 与实际的贝叶斯融合算法关联
 */

// API配置
const API_BASE_URL = '/api/fusion';

// 路径配置
const PATHS = {
    fusionScript: '../../../backend/algorithms/多源数据融合/运行融合_新版.bat',
    chartsScript: '../../../backend/algorithms/多源数据融合/results/生成报告.bat',
    chartsDir: '../../../backend/algorithms/多源数据融合/results/charts',
    htmlReport: '../../../backend/algorithms/多源数据融合/results/统计分析报告.html',
    inputYoloVal: '../../../backend/algorithms/多源数据融合/input/yolo/val',
    inputYoloTest: '../../../backend/algorithms/多源数据融合/input/yolo/test',
    inputPcVal: '../../../backend/algorithms/多源数据融合/input/pointcloud/val',
    inputPcTest: '../../../backend/algorithms/多源数据融合/input/pointcloud/test',
    outputVal: '../../../backend/algorithms/多源数据融合/output/fusion/val',
    outputTest: '../../../backend/algorithms/多源数据融合/output/fusion/test'
};

// 图表文件列表
const CHART_FILES = [
    { file: '1_类别融合概率对比.png', title: '类别融合概率对比' },
    { file: '2_YOLO_vs_融合概率_验证集.png', title: 'YOLO vs 融合概率（验证集）' },
    { file: '2_YOLO_vs_融合概率_测试集.png', title: 'YOLO vs 融合概率（测试集）' },
    { file: '3_熵值_vs_融合概率_验证集.png', title: '熵值 vs 融合概率（验证集）' },
    { file: '3_熵值_vs_融合概率_测试集.png', title: '熵值 vs 融合概率（测试集）' },
    { file: '4_融合概率分布箱线图.png', title: '融合概率分布箱线图' },
    { file: '5_相关性热力图_验证集.png', title: '相关性热力图（验证集）' },
    { file: '5_相关性热力图_测试集.png', title: '相关性热力图（测试集）' }
];

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    updateStatus('就绪', 'ready');
});

// 初始化事件监听器
function initializeEventListeners() {
    // 返回按钮
    document.getElementById('backBtn').addEventListener('click', function() {
        window.history.back();
    });

    // 导入数据源按钮
    document.getElementById('importDataBtn').addEventListener('click', importDataSource);

    // 开始融合计算按钮
    document.getElementById('startFusionBtn').addEventListener('click', startFusionCalculation);

    // 生成可视化图表按钮
    document.getElementById('generateChartsBtn').addEventListener('click', generateCharts);

    // 展示图表按钮
    const showChartsBtn = document.getElementById('showChartsBtn');
    if (showChartsBtn) {
        showChartsBtn.addEventListener('click', showCharts);
    }

    // 导出实验报告按钮
    document.getElementById('exportReportBtn').addEventListener('click', exportReport);

    // 图片模态框
    setupImageModal();
}

// 导入数据源（模拟过程）
function importDataSource() {
    updateStatus('正在导入数据源...', 'processing');
    updateProgress(0);

    // 模拟导入过程
    let progress = 0;
    const interval = setInterval(() => {
        progress += 10;
        updateProgress(progress);

        if (progress >= 100) {
            clearInterval(interval);
            updateStatus('数据源导入完成', 'success');
            
            // 显示数据概览
            showDataOverview();
            
            // 加载示例数据
            loadSampleData();
            
            setTimeout(() => {
                updateStatus('就绪', 'ready');
            }, 2000);
        }
    }, 200);
}

// 显示数据概览
function showDataOverview() {
    document.getElementById('yoloDataStatus').textContent = '已加载';
    document.getElementById('yoloDataStatus').style.color = '#28a745';
    
    document.getElementById('pointCloudStatus').textContent = '已加载';
    document.getElementById('pointCloudStatus').style.color = '#28a745';
}

// 加载示例数据
function loadSampleData() {
    // YOLO示例数据
    const yoloSample = {
        'Car': { mean_conf: 0.8386, count: 30 },
        'Pedestrian': { mean_conf: 0.5298, count: 30 },
        'Cyclist': { mean_conf: 0.6063, count: 6 }
    };

    // 点云熵示例数据
    const pcSample = {
        'Car': { entropy: 6.4237, count: 11 },
        'Pedestrian': { entropy: 4.8725, count: 10 },
        'Cyclist': { entropy: 4.2409, count: 3 }
    };

    // 显示YOLO数据
    displayYoloData(yoloSample);
    
    // 显示点云数据
    displayEntropyData(pcSample);
}

// 显示YOLO数据
function displayYoloData(data) {
    const container = document.getElementById('yoloResults');
    let html = '';
    
    for (const [cls, info] of Object.entries(data)) {
        html += `
            <div style="padding: 10px; border-bottom: 1px solid #eee;">
                <div style="font-weight: bold; color: #2C5AA0;">${cls}</div>
                <div style="font-size: 0.9em; color: #666;">
                    置信度: ${info.mean_conf.toFixed(4)} | 数量: ${info.count}
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
    document.getElementById('yoloResultCount').textContent = Object.keys(data).length;
}

// 显示点云熵数据
function displayEntropyData(data) {
    const container = document.getElementById('entropyResults');
    let html = '';
    
    for (const [cls, info] of Object.entries(data)) {
        html += `
            <div style="padding: 10px; border-bottom: 1px solid #eee;">
                <div style="font-weight: bold; color: #28a745;">${cls}</div>
                <div style="font-size: 0.9em; color: #666;">
                    熵值: ${info.entropy.toFixed(4)} | 数量: ${info.count}
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
    document.getElementById('entropyResultCount').textContent = Object.keys(data).length;
}

// 开始融合计算
async function startFusionCalculation() {
    // 先检查后端是否运行
    let backendRunning = false;
    try {
        const healthCheck = await fetch(`${API_BASE_URL}/health`, {
            method: 'GET',
            signal: AbortSignal.timeout(3000)
        });
        backendRunning = healthCheck.ok;
    } catch (error) {
        backendRunning = false;
    }

    if (!backendRunning) {
        alert('服务器后端服务暂不可用，暂时无法运行融合算法。请联系平台维护人员检查服务器运行状态。');
        return;
    }

    if (!confirm('确定要开始融合计算吗？\n\n这将调用后端的贝叶斯融合算法，处理150帧数据（75验证集 + 75测试集）。\n\n预计耗时：约2秒')) {
        return;
    }

    updateStatus('正在进行融合计算...', 'processing');
    updateProgress(0);

    try {
        // 调用API启动融合计算
        const response = await fetch(`${API_BASE_URL}/fusion/start`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.message);
        }
        
        // 轮询状态
        const statusInterval = setInterval(async () => {
            try {
                const statusResponse = await fetch(`${API_BASE_URL}/fusion/status`);
                const statusData = await statusResponse.json();
                
                updateProgress(statusData.progress);
                updateStatus(statusData.message, statusData.running ? 'processing' : 'success');
                
                if (!statusData.running && statusData.progress === 100) {
                    clearInterval(statusInterval);
                    
                    // 更新融合数据状态
                    document.getElementById('fusionDataStatus').textContent = '已生成';
                    document.getElementById('fusionDataStatus').style.color = '#28a745';
                    document.getElementById('fusionDataCount').textContent = '150帧';
                    
                    // 显示融合结果
                    displayFusionResults();
                    
                    showToast('融合计算完成！生成了150个融合结果文件', 'success');
                    
                    setTimeout(() => {
                        updateStatus('就绪', 'ready');
                    }, 2000);
                }
            } catch (error) {
                clearInterval(statusInterval);
                console.error('获取状态失败:', error);
            }
        }, 500);
        
    } catch (error) {
        updateStatus('调用失败', 'error');
        alert('无法连接到Web服务器！\n\n错误: ' + error.message + '\n\n请启动Web服务器后重试。');
    }
}

// 显示融合结果
function displayFusionResults() {
    const fusionSample = {
        'Car': { yolo: 0.8386, entropy: 6.4237, fused: 0.3905 },
        'Cyclist': { yolo: 0.6063, entropy: 4.2409, fused: 0.2447 },
        'Pedestrian': { yolo: 0.5298, entropy: 4.8725, fused: 0.1663 },
        'Bus': { yolo: 0.3961, entropy: 10.0, fused: 0.0407 },
        'Truck': { yolo: 0.1000, entropy: 10.0, fused: 0.0071 }
    };

    const container = document.getElementById('fusionResults');
    let html = '';
    
    for (const [cls, info] of Object.entries(fusionSample)) {
        html += `
            <div style="padding: 10px; border-bottom: 1px solid #eee;">
                <div style="font-weight: bold; color: #dc3545;">${cls}</div>
                <div style="font-size: 0.85em; color: #666;">
                    YOLO: ${info.yolo.toFixed(4)}<br>
                    熵值: ${info.entropy.toFixed(4)}<br>
                    <span style="color: #dc3545; font-weight: bold;">融合概率: ${info.fused.toFixed(4)}</span>
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
    document.getElementById('fusionResultCount').textContent = Object.keys(fusionSample).length;
}

// 生成可视化图表
async function generateCharts() {
    // 先检查后端是否运行
    let backendRunning = false;
    try {
        const healthCheck = await fetch(`${API_BASE_URL}/health`, {
            method: 'GET',
            signal: AbortSignal.timeout(3000)
        });
        backendRunning = healthCheck.ok;
    } catch (error) {
        backendRunning = false;
    }

    if (!backendRunning) {
        alert('服务器后端服务暂不可用，暂时无法生成图表。请联系平台维护人员检查服务器运行状态。');
        return;
    }

    if (!confirm('确定要生成可视化图表吗？\n\n这将调用Python脚本生成8张统计分析图表和HTML报告。\n\n预计耗时：约10秒')) {
        return;
    }

    updateStatus('正在生成可视化图表...', 'processing');
    updateProgress(0);

    try {
        // 调用API启动图表生成
        const response = await fetch(`${API_BASE_URL}/charts/start`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.message);
        }
        
        // 轮询状态
        const statusInterval = setInterval(async () => {
            try {
                const statusResponse = await fetch(`${API_BASE_URL}/charts/status`);
                const statusData = await statusResponse.json();
                
                updateProgress(statusData.progress);
                updateStatus(statusData.message, statusData.running ? 'processing' : 'success');
                
                if (!statusData.running && statusData.progress === 100) {
                    clearInterval(statusInterval);
                    
                    // 显示展示图表按钮
                    document.getElementById('showChartsBtn').style.display = 'block';
                    
                    showToast('图表生成完成！生成了8张PNG图表和HTML报告', 'success');
                    
                    setTimeout(() => {
                        updateStatus('就绪', 'ready');
                    }, 2000);
                }
            } catch (error) {
                clearInterval(statusInterval);
                console.error('获取状态失败:', error);
            }
        }, 500);
        
    } catch (error) {
        updateStatus('调用失败', 'error');
        alert('无法连接到Web服务器！\n\n错误: ' + error.message + '\n\n请启动Web服务器后重试。');
    }
}

// 展示图表
async function showCharts() {
    const chartsSection = document.getElementById('chartsSection');
    const chartsViewer = document.getElementById('chartsViewer');
    
    // 清空现有内容
    chartsViewer.innerHTML = '<p style="text-align: center; padding: 20px;">正在加载图表...</p>';
    
    try {
        // 从API获取图表列表
        const response = await fetch(`${API_BASE_URL}/charts/list`);
        const data = await response.json();
        
        if (!data.success || data.charts.length === 0) {
            chartsViewer.innerHTML = '<p style="text-align: center; padding: 20px; color: #999;">暂无图表，请先生成图表</p>';
            chartsSection.style.display = 'block';
            return;
        }
        
        // 清空加载提示
        chartsViewer.innerHTML = '';
        
        // 加载所有图表
        data.charts.forEach(chart => {
            const chartItem = document.createElement('div');
            chartItem.className = 'chart-item';
            
            // 从文件名提取标题
            let title = chart.filename.replace('.png', '');
            const titleMap = {
                '1_类别融合概率对比': '类别融合概率对比',
                '2_YOLO_vs_融合概率_验证集': 'YOLO vs 融合概率（验证集）',
                '2_YOLO_vs_融合概率_测试集': 'YOLO vs 融合概率（测试集）',
                '3_熵值_vs_融合概率_验证集': '熵值 vs 融合概率（验证集）',
                '3_熵值_vs_融合概率_测试集': '熵值 vs 融合概率（测试集）',
                '4_融合概率分布箱线图': '融合概率分布箱线图',
                '5_相关性热力图_验证集': '相关性热力图（验证集）',
                '5_相关性热力图_测试集': '相关性热力图（测试集）'
            };
            title = titleMap[title] || title;
            
            chartItem.innerHTML = `
                <h4>${title}</h4>
                <img src="${API_BASE_URL}${chart.path}" 
                     alt="${title}" 
                     onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'400\\' height=\\'300\\'%3E%3Crect fill=\\'%23f0f0f0\\' width=\\'400\\' height=\\'300\\'/%3E%3Ctext x=\\'50%25\\' y=\\'50%25\\' text-anchor=\\'middle\\' fill=\\'%23999\\' font-size=\\'16\\'%3E图表加载失败%3C/text%3E%3C/svg%3E'">
            `;
            chartsViewer.appendChild(chartItem);
        });
        
        // 显示图表区域
        chartsSection.style.display = 'block';
        
        // 滚动到图表区域
        chartsSection.scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        chartsViewer.innerHTML = '<p style="text-align: center; padding: 20px; color: #dc3545;">加载图表失败，请确保Web服务器正在运行</p>';
        chartsSection.style.display = 'block';
        console.error('加载图表失败:', error);
    }
}

// 导出实验报告
function exportReport() {
    if (!confirm('确定要导出实验报告吗？\n\n将打开HTML格式的统计分析报告，您可以在浏览器中查看并打印为PDF。')) {
        return;
    }

    // 通过API打开HTML报告
    const reportUrl = `${API_BASE_URL}/report/html`;
    window.open(reportUrl, '_blank');
    
    showToast('实验报告已在新窗口中打开', 'success');
}

// 更新状态
function updateStatus(message, type) {
    const statusElement = document.getElementById('fusionStatus');
    statusElement.textContent = message;
    
    // 移除所有状态类
    statusElement.classList.remove('status-ready', 'status-processing', 'status-success', 'status-error');
    
    // 添加对应状态类
    switch(type) {
        case 'ready':
            statusElement.classList.add('status-ready');
            statusElement.style.color = '#2C5AA0';
            break;
        case 'processing':
            statusElement.classList.add('status-processing');
            statusElement.style.color = '#ffc107';
            break;
        case 'success':
            statusElement.classList.add('status-success');
            statusElement.style.color = '#28a745';
            break;
        case 'error':
            statusElement.classList.add('status-error');
            statusElement.style.color = '#dc3545';
            break;
    }
}

// 更新进度
function updateProgress(percent) {
    const progressBar = document.getElementById('fusionProgressBar');
    const progressText = document.getElementById('progressText');
    
    progressBar.style.width = percent + '%';
    progressText.textContent = percent + '%';
}

// 设置图片模态框
function setupImageModal() {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImage');
    const closeBtn = document.querySelector('.close-modal');
    
    // 点击关闭按钮
    closeBtn.onclick = function() {
        modal.style.display = 'none';
    };
    
    // 点击模态框外部关闭
    modal.onclick = function(event) {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    };
    
    // 为图表图片添加点击事件（使用事件委托）
    document.addEventListener('click', function(e) {
        if (e.target.tagName === 'IMG' && e.target.closest('.chart-item')) {
            modal.style.display = 'block';
            modalImg.src = e.target.src;
        }
    });
}

// 工具函数：格式化数字
function formatNumber(num, decimals = 4) {
    return Number(num).toFixed(decimals);
}

// 工具函数：显示提示信息
function showToast(message, type = 'info') {
    // 创建提示元素
    const toast = document.createElement('div');
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : '#2C5AA0'};
        color: white;
        border-radius: 5px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
    `;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    // 3秒后自动移除
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 300);
    }, 3000);
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
