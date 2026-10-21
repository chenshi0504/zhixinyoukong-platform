/**
 * 交通流重构功能JavaScript
 */

// 重构结果数据
let reconstructionResults = [];
let currentChart = null;

/**
 * 兼容层：早期版本依赖 Element Plus 的 Message / Loading 与自定义 TrafficAPI，
 * 当前页面并未引入这些依赖。缺失时调用会抛 ReferenceError，导致"出错提示"这条
 * 路径本身崩溃、真正的错误被吞掉。这里用页面已有的提示通道补齐同名对象，
 * 保持原有调用点不变。
 */
const Message = {
    error: function (text) { updateStatus(text, 'error'); },
    success: function (text) { updateStatus(text, 'success'); },
    info: function (text) { updateStatus(text, 'info'); }
};

const Loading = {
    show: function () { showProgress(5); },
    hide: function () { hideProgress(); }
};

const TrafficAPI = {
    // 当前后端未提供"保存重构结果"接口，明确失败好过静默崩溃
    saveReconstruction: function () {
        return Promise.reject(new Error('当前版本未提供保存重构结果接口，请改用导出功能保存结果'));
    }
};

/**
 * 标记步骤按钮完成：按钮从蓝底变为白底蓝边
 */
function markStepDone(buttonId) {
    const btn = document.getElementById(buttonId);
    if (btn && !btn.classList.contains('step-done')) {
        btn.classList.add('step-done');
    }
}
/**
 * 重置所有步骤按钮样式（恢复为蓝底）
 */
function resetAllStepButtons() {
    ['importDataBtn', 'runNEXTABtn', 'showResultsBtn', 'exportCSVBtn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.classList.remove('step-done');
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    console.log('页面加载完成，开始初始化...');
    
    // 绑定事件
    bindEvents();
    // 局域网访问同样可以启动 DTALite / NEXTA：后端会在运行平台的本机弹出 CMD
    // 窗口执行，状态与结果通过 /api/reconstruction/dtalite-status 轮询反馈。
    
    console.log('事件绑定完成');
});

/**
 * 初始化页面
 */
async function initPage() {
    // 简化初始化，不依赖外部对象
    console.log('页面初始化完成');
}

/**
 * 绑定事件
 */
function bindEvents() {
    // 返回按钮
    const backBtn = document.getElementById('backBtn');
    if (backBtn) {
        backBtn.addEventListener('click', () => window.history.back());
    }

    // 数据一键导入按钮
    const importDataBtn = document.getElementById('importDataBtn');
    if (importDataBtn) {
        importDataBtn.addEventListener('click', importData);
    }

    // 运行NEXTA重构按钮
    const runNEXTABtn = document.getElementById('runNEXTABtn');
    if (runNEXTABtn) {
        runNEXTABtn.addEventListener('click', runNEXTAReconstruction);
    }

    // 查看结果按钮
    const showResultsBtn = document.getElementById('showResultsBtn');
    if (showResultsBtn) {
        showResultsBtn.addEventListener('click', showResults);
    }

    // 导出CSV按钮
    const exportCSVBtn = document.getElementById('exportCSVBtn');
    if (exportCSVBtn) {
        exportCSVBtn.addEventListener('click', exportCSV);
    }

    // 生成OD分析图表按钮
    const generateODAnalysisBtn = document.getElementById('generateODAnalysisBtn');
    if (generateODAnalysisBtn) {
        generateODAnalysisBtn.addEventListener('click', generateODAnalysis);
    }

    // 下载OD数据CSV按钮
    const downloadODCSVBtn = document.getElementById('downloadODCSVBtn');
    if (downloadODCSVBtn) {
        downloadODCSVBtn.addEventListener('click', downloadODCSV);
    }

    // 下载分析报告按钮
    const downloadReportBtn = document.getElementById('downloadReportBtn');
    if (downloadReportBtn) {
        downloadReportBtn.addEventListener('click', downloadReport);
    }

    // 重置按钮
    const resetBtn = document.getElementById('resetBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetStatus);
    }

    // 保存参数按钮
    const saveParamsBtn = document.getElementById('saveParamsBtn');
    if (saveParamsBtn) {
        saveParamsBtn.addEventListener('click', saveParameters);
    }

    // 启动NEXTA路网编辑器按钮
    const launchNEXTABtn = document.getElementById('launchNEXTABtn');
    if (launchNEXTABtn) {
        launchNEXTABtn.addEventListener('click', launchNEXTA);
    }

    // 导出路网编辑文档按钮
    const exportNetworkDocBtn = document.getElementById('exportNetworkDocBtn');
    if (exportNetworkDocBtn) {
        exportNetworkDocBtn.addEventListener('click', exportNetworkDoc);
    }

    // 算法选择
    const algorithmSelect = document.getElementById('algorithmSelect');
    if (algorithmSelect) {
        algorithmSelect.addEventListener('change', onAlgorithmChange);
    }

    // 参数滑块实时更新
    bindParameterSliders();
}

/**
 * 加载重构历史
 */
async function loadReconstructionHistory() {
    try {
        // 暂时使用模拟数据，不依赖后端API
        reconstructionResults = [];
        console.log('历史记录加载完成');
    } catch (error) {
        console.error('加载历史失败:', error);
    }
}

/**
 * 显示最近结果
 */
function displayRecentResults() {
    const container = document.getElementById('recentResults');
    if (!container || reconstructionResults.length === 0) return;

    container.innerHTML = reconstructionResults.map(result => `
        <div class="result-item" onclick="loadResult(${result.id})">
            <div class="result-algorithm">${result.algorithm}</div>
            <div class="result-time">${DateFormatter.format(result.created_at)}</div>
            <div class="result-metrics">MAE: ${result.metrics.mae}</div>
        </div>
    `).join('');
}

/**
 * 开始重构
 */
async function startReconstruction() {
    try {
        // 获取配置
        const algorithm = document.getElementById('algorithm')?.value;
        const dataSourceIds = getSelectedDataSources();

        if (!algorithm) {
            Message.error('请选择重构算法');
            return;
        }

        if (dataSourceIds.length === 0) {
            Message.error('请选择至少一个数据源');
            return;
        }

        Loading.show('正在进行交通流重构...');

        // 模拟重构过程
        await simulateReconstruction(algorithm, dataSourceIds);

        Message.success('交通流重构完成');
    } catch (error) {
        console.error('重构失败:', error);
        Message.error('重构失败: ' + error.message);
    } finally {
        Loading.hide();
    }
}

/**
 * 模拟重构过程
 */
async function simulateReconstruction(algorithm, dataSourceIds) {
    // 模拟延迟
    await new Promise(resolve => setTimeout(resolve, 2000));

    // 生成模拟数据
    const reconstructedFlow = Array.from({length: 24}, () => 
        Math.floor(Math.random() * 100 + 50)
    );

    // 显示结果图表
    displayReconstructionChart(reconstructedFlow);

    // 更新统计信息
    updateStatistics({
        mae: (Math.random() * 5 + 1).toFixed(2),
        rmse: (Math.random() * 7 + 2).toFixed(2),
        mape: (Math.random() * 0.1).toFixed(3)
    });
}

/**
 * 显示重构图表
 */
function displayReconstructionChart(data) {
    const chartContainer = document.getElementById('reconstructionChart');
    if (!chartContainer) return;

    // 如果已有图表，先销毁
    if (currentChart) {
        currentChart.dispose();
    }

    // 创建新图表
    currentChart = echarts.init(chartContainer);

    const option = {
        title: {
            text: '交通流重构结果',
            left: 'center'
        },
        tooltip: {
            trigger: 'axis'
        },
        xAxis: {
            type: 'category',
            data: Array.from({length: 24}, (_, i) => `${i}:00`)
        },
        yAxis: {
            type: 'value',
            name: '流量(辆/小时)'
        },
        series: [{
            name: '重构流量',
            type: 'line',
            data: data,
            smooth: true,
            lineStyle: {
                color: '#2C5AA0',
                width: 2
            },
            areaStyle: {
                color: {
                    type: 'linear',
                    x: 0,
                    y: 0,
                    x2: 0,
                    y2: 1,
                    colorStops: [{
                        offset: 0,
                        color: 'rgba(44, 90, 160, 0.3)'
                    }, {
                        offset: 1,
                        color: 'rgba(44, 90, 160, 0.05)'
                    }]
                }
            }
        }]
    };

    currentChart.setOption(option);
}

/**
 * 更新统计信息
 */
function updateStatistics(metrics) {
    const maeElement = document.getElementById('maeValue');
    const rmseElement = document.getElementById('rmseValue');
    const mapeElement = document.getElementById('mapeValue');

    if (maeElement) maeElement.textContent = metrics.mae;
    if (rmseElement) rmseElement.textContent = metrics.rmse;
    if (mapeElement) mapeElement.textContent = metrics.mape;
}

/**
 * 保存重构结果
 */
async function saveReconstructionResult() {
    try {
        const algorithm = document.getElementById('algorithm')?.value;
        
        if (!algorithm) {
            Message.error('没有可保存的结果');
            return;
        }

        Loading.show('保存结果...');

        // 构建结果数据
        const resultData = {
            algorithm: algorithm,
            input_data: {
                source_ids: getSelectedDataSources(),
                time_range: getTimeRange()
            },
            result: {
                reconstructed_flow: getCurrentReconstructedFlow(),
                confidence: 0.95
            },
            metrics: {
                mae: parseFloat(document.getElementById('maeValue')?.textContent || 0),
                rmse: parseFloat(document.getElementById('rmseValue')?.textContent || 0),
                mape: parseFloat(document.getElementById('mapeValue')?.textContent || 0)
            }
        };

        // 保存到后端
        await TrafficAPI.saveReconstruction(resultData);
        
        Message.success('重构结果保存成功');

        // 重新加载历史
        await loadReconstructionHistory();
    } catch (error) {
        console.error('保存失败:', error);
        Message.error('保存失败: ' + error.message);
    } finally {
        Loading.hide();
    }
}

/**
 * 获取选中的数据源
 */
function getSelectedDataSources() {
    const checkboxes = document.querySelectorAll('input[name="dataSource"]:checked');
    return Array.from(checkboxes).map(cb => parseInt(cb.value));
}

/**
 * 获取时间范围
 */
function getTimeRange() {
    const startTime = document.getElementById('startTime')?.value;
    const endTime = document.getElementById('endTime')?.value;
    return `${startTime} - ${endTime}`;
}

/**
 * 获取当前重构流量数据
 */
function getCurrentReconstructedFlow() {
    if (!currentChart) return [];
    const option = currentChart.getOption();
    return option.series[0].data || [];
}

/**
 * 绑定参数滑块
 */
function bindParameterSliders() {
    // 收敛阈值滑块
    const thresholdSlider = document.getElementById('threshold');
    const thresholdValue = document.getElementById('thresholdValue');
    if (thresholdSlider && thresholdValue) {
        thresholdSlider.addEventListener('input', (e) => {
            thresholdValue.textContent = e.target.value;
        });
    }

    // 正则化参数滑块
    const regularizationSlider = document.getElementById('regularization');
    const regularizationValue = document.getElementById('regularizationValue');
    if (regularizationSlider && regularizationValue) {
        regularizationSlider.addEventListener('input', (e) => {
            regularizationValue.textContent = e.target.value;
        });
    }

    // 学习率滑块
    const learningRateSlider = document.getElementById('learningRate');
    const learningRateValue = document.getElementById('learningRateValue');
    if (learningRateSlider && learningRateValue) {
        learningRateSlider.addEventListener('input', (e) => {
            learningRateValue.textContent = e.target.value;
        });
    }
}

/**
 * 数据一键导入 - 调用后端获取真实数据文件信息
 */
async function importData() {
    try {
        updateStatus('正在导入OD数据...', 'processing');
        showProgress(0);

        // 更新导入卡片为加载中
        const importCard = document.getElementById('odImportCard');
        if (importCard) {
            importCard.style.borderLeftColor = '#ffc107';
            document.getElementById('odImportStatus').innerHTML = '<span class="loading-spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></span> 正在导入...';
        }

        // 模拟进度条
        let progress = 0;
        const interval = setInterval(() => {
            progress += 10;
            showProgress(Math.min(progress, 90));
        }, 250);

        // 调用后端获取真实数据统计
        let importInfo = { fileCount: 0, odPairCount: '--', status: '未知' };
        try {
            const resp = await fetch(`${RECONSTRUCTION_API}/import-data`, { method: 'POST' });
            const data = await resp.json();
            if (data.success) {
                importInfo = data;
            }
        } catch (e) {
            console.warn('后端导入接口调用失败:', e);
        }

        clearInterval(interval);
        showProgress(100);

        // 更新隐藏数据字段
        document.getElementById('fileCount').textContent = String(importInfo.fileCount || 0);
        document.getElementById('dataPoints').textContent = String(importInfo.odPairCount || '--');
        document.getElementById('missingRate').textContent = importInfo.status || '已就绪';

        // 更新导入卡片为完成
        if (importCard) {
            importCard.style.borderLeftColor = '#28a745';
            importCard.querySelector('div:first-child').textContent = '✅';
            document.getElementById('odImportStatus').innerHTML = 'output_ODMOE.csv<br>OD对 ' + (importInfo.odPairCount || '--') + ' · 已就绪';
            document.getElementById('odImportStatus').style.color = '#333';
        }

        updateStatus('OD数据导入完成', 'success');
        markStepDone('importDataBtn');
        hideProgress();
        return Number(importInfo.fileCount || 0) > 0;

    } catch (error) {
        console.error('导入数据失败:', error);
        updateStatus('导入失败', 'error');
        hideProgress();
        return false;
    }
}

// 交通流重构后端API地址
const RECONSTRUCTION_API = '/api/reconstruction';

/**
 * 运行NEXTA重构 - 调用后端DTALite（后端在运行平台的本机弹出 CMD 窗口执行）
 */
async function runNEXTAReconstruction() {
    try {
        let fileCount = document.getElementById('fileCount').textContent;
        if (fileCount === '0') {
            updateStatus('正在检查并导入数据...', 'processing');
            const ready = await importData();
            fileCount = document.getElementById('fileCount').textContent;
            if (!ready || fileCount === '0') {
                updateStatus('数据文件未就绪，无法启动DTALite', 'error');
                return;
            }
        }

        updateStatus('正在启动DTALite重构...', 'processing');

        // 显示运行中状态
        showDTALiteRunning();

        // 调用后端API启动DTALite（异步，立即返回）
        try {
            const response = await fetch(`${RECONSTRUCTION_API}/run-dtalite`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                if (result.async) {
                    // 异步模式：DTALite 在后端电脑弹出 CMD 窗口运行，轮询状态取回结果
                    updateStatus('DTALite正在运行中（已在后端电脑弹出 CMD 窗口）...', 'processing');
                    console.log('DTALite已启动，开始轮询状态...');
                    pollDTALiteStatus();
                } else {
                    // 同步模式（模拟模式）：延迟显示结果，模拟运行过程
                    updateStatus('DTALite正在运行中...', 'processing');
                    console.log('同步/演示模式，延迟5秒后显示结果...');
                    setTimeout(() => {
                        onDTALiteComplete(result);
                    }, 5000);
                }
            } else {
                updateStatus('重构失败: ' + result.message, 'error');
                showDTALiteWaiting();
            }
        } catch (apiError) {
            console.error('服务器后端服务不可用:', apiError);
            updateStatus('后端服务未响应，请检查服务是否正常启动', 'error');
            showDTALiteWaiting();
        }

    } catch (error) {
        console.error('重构失败:', error);
        updateStatus('重构失败', 'error');
        showDTALiteWaiting();
    }
}

/**
 * 显示DTALite运行中状态
 */
function showDTALiteRunning() {
    const reconstructCard = document.getElementById('odReconstructCard');
    if (reconstructCard) {
        reconstructCard.style.borderLeftColor = '#ffc107';
        reconstructCard.querySelector('div:first-child').textContent = '⏳';
        document.getElementById('odReconstructStatus').innerHTML = '<span class="loading-spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></span> DTALite 运行中...<br><span style="font-size:11px;color:#999;">执行过程在后端电脑弹出的 CMD 窗口可见</span>';
    }
    // 隐藏指标卡片
    const metricsCard = document.getElementById('odMetricsCard');
    if (metricsCard) metricsCard.style.display = 'none';
}

/**
 * 恢复DTALite等待状态
 */
function showDTALiteWaiting() {
    const reconstructCard = document.getElementById('odReconstructCard');
    if (reconstructCard) {
        reconstructCard.style.borderLeftColor = '#dcdfe6';
        reconstructCard.querySelector('div:first-child').textContent = '🔄';
        document.getElementById('odReconstructStatus').innerHTML = '等待执行';
        document.getElementById('odReconstructStatus').style.color = '#999';
    }
}

/**
 * 轮询DTALite执行状态
 */
function pollDTALiteStatus() {
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`${RECONSTRUCTION_API}/dtalite-status`);
            const status = await response.json();
            
            if (status.running) {
                // 还在运行，保持运行中状态
                updateStatus('DTALite正在运行中...', 'processing');
            } else {
                // 运行结束
                clearInterval(pollInterval);
                if (status.success) {
                    onDTALiteComplete(status);
                } else {
                    updateStatus('重构失败: ' + status.message, 'error');
                    showDTALiteWaiting();
                }
            }
        } catch (e) {
            // 网络错误，继续轮询
            console.warn('轮询状态失败:', e);
        }
    }, 2000); // 每2秒查一次
}

/**
 * DTALite执行完成后的处理
 */
function onDTALiteComplete(result) {
    // 从后端返回的 metrics 对象中读取真实数据
    const m = result.metrics || {};
    const reconstructedData = {
        accuracy: m.accuracy || '--',
        rmse: m.rmse || '--',
        processingTime: m.processingTime || '--',
        odPairCount: m.odPairCount || '--',
        avgTripTime: m.avgTripTime || '--',
        avgDistance: m.avgDistance || '--',
        totalVehicles: m.totalVehicles || '--',
        avgSpeed: m.avgSpeed || '--',
    };
    console.log('DTALite执行成功，真实指标:', reconstructedData);
    
    // 显示结果
    displayReconstructionResults(reconstructedData);
    displayReconstructedDataChart(reconstructedData);
    updateStatus('重构完成', 'success');
    // 标记运行NEXTA重构按钮完成
    markStepDone('runNEXTABtn');
}

/**
 * 结果分析 - 调用Python脚本生成验证分析图表
 */
async function showResults() {
    const accuracy = document.getElementById('reconstructionAccuracy').textContent;
    if (accuracy === '--') {
        updateStatus('请先运行NEXTA重构', 'error');
        return;
    }

    updateStatus('正在生成验证分析图表...', 'processing');

    try {
        const response = await fetch(`${RECONSTRUCTION_API}/run-validation-analysis`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (result.success) {
            updateStatus('验证分析完成', 'success');
            // 标记结果分析按钮完成
            markStepDone('showResultsBtn');
            
            // 显示生成的验证分析图表
            displayValidationCharts();
            
            // 滚动到结果区域
            const resultSection = document.querySelector('.result-output-section');
            if (resultSection) {
                resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        } else {
            updateStatus('分析失败: ' + result.message, 'error');
        }
    } catch (apiError) {
        console.error('服务器后端服务不可用:', apiError);
        updateStatus('服务器后端服务暂不可用', 'error');
    }
}

/**
 * 显示验证分析图表 - 展示4张验证分析图
 */
function displayValidationCharts() {
    const resultDisplay = document.getElementById('resultDisplay');
    if (!resultDisplay) return;
    
    const chartsAPI = RECONSTRUCTION_API + '/validation-chart/';
    
    // 定义要显示的4张验证分析图及其说明
    const validationCharts = [
        {
            file: '01_link_flow_timeseries.png',
            name: '图1：主要路段流量时序变化',
            desc: '展示5个主要路段的交通流量随时间的变化趋势，反映不同路段的流量特征和时变规律'
        },
        {
            file: '02_link_flow_distribution.png',
            name: '图2：各路段总流量统计',
            desc: '统计所有路段的总交通流量分布，识别路网中的关键路段和流量瓶颈'
        },
        {
            file: '03_observed_vs_simulated_scatter.png',
            name: '图3：观测流量 vs 反推流量对比',
            desc: '对比输入约束（observed）与矩阵分配结果（simulated）的路段流量，评估重构算法的准确性'
        },
        {
            file: '04_error_distribution.png',
            name: '图4：路段流量误差分布',
            desc: '展示反推流量与观测流量的误差分布情况，红色表示低估，绿色表示高估，评估算法性能'
        }
    ];
    
    let html = `
        <div style="margin-bottom: 15px;">
            <h4 style="color: #2C5AA0; margin: 0 0 10px 0;">📊 交通流重构验证分析</h4>
            <p style="color: #666; font-size: 13px; margin: 0;">基于 debug_validation_results.csv 数据生成的验证分析图表</p>
        </div>
        <div style="display: flex; flex-direction: column; gap: 20px;">
    `;
    
    validationCharts.forEach(chart => {
        const imgUrl = chartsAPI + chart.file;
        html += `
            <div style="background: white; border-radius: 8px; padding: 15px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                    <div style="flex: 1;">
                        <p style="font-size: 14px; font-weight: bold; color: #2C5AA0; margin: 0 0 6px 0;">${chart.name}</p>
                        <p style="font-size: 12px; color: #666; margin: 0; line-height: 1.5;">${chart.desc}</p>
                    </div>
                    <button onclick="window.open('${imgUrl}', '_blank')" 
                            style="background: #2C5AA0; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; white-space: nowrap; margin-left: 10px;">
                        查看大图
                    </button>
                </div>
                <img src="${imgUrl}" 
                     alt="${chart.name}" 
                     style="width: 100%; border-radius: 4px; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
                     onclick="window.open(this.src, '_blank')"
                     onerror="this.parentElement.innerHTML='<div style=\\'padding: 20px; text-align: center; color: #999;\\'>图表加载失败</div>'">
            </div>
        `;
    });
    
    html += '</div>';
    resultDisplay.innerHTML = html;
}

/**
 * 显示分析图表 - 只显示图1、图7、图10、图12（保留旧功能）
 */
function displayAnalysisCharts(charts) {
    const resultDisplay = document.getElementById('resultDisplay');
    if (!resultDisplay) return;
    
    const chartsPath = '../../../backend/algorithms/交通流重构/Output_management/charts/';
    
    // 定义要显示的4张图及其说明
    const selectedCharts = [
        {
            file: '01_output_ODMOE.png',
            name: '图1：OD矩阵重构结果',
            desc: '展示各起讫点对之间的出行需求分布，反映区域交通流的空间分布特征'
        },
        {
            file: '07_output_LinkMOE.png',
            name: '图7：路段性能指标',
            desc: '显示各路段的流量、速度、密度等关键性能指标统计'
        },
        {
            file: '10_output_NetworkTDMOE.png',
            name: '图10：路网时变性能',
            desc: '展示路网整体性能随时间的变化趋势，包括总流量和平均速度'
        },
        {
            file: '12_output_trip.png',
            name: '图12：出行统计分析',
            desc: '统计出行时间、出行距离等指标的分布情况'
        }
    ];
    
    let html = `
        <div style="margin-bottom: 15px;">
            <h4 style="color: #2C5AA0; margin: 0 0 10px 0;">📊 DTALite输出分析图表</h4>
        </div>
        <div style="display: flex; flex-direction: column; gap: 20px;">
    `;
    
    selectedCharts.forEach(chart => {
        html += `
            <div style="background: white; border-radius: 8px; padding: 15px; box-shadow: 0 2px 6px rgba(0,0,0,0.1);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                    <div>
                        <p style="font-size: 14px; font-weight: bold; color: #2C5AA0; margin: 0 0 4px 0;">${chart.name}</p>
                        <p style="font-size: 12px; color: #666; margin: 0; line-height: 1.4;">${chart.desc}</p>
                    </div>
                    <button onclick="window.open('${chartsPath}${chart.file}', '_blank')" 
                            style="background: #2C5AA0; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px;">
                        查看大图
                    </button>
                </div>
                <img src="${chartsPath}${chart.file}" 
                     alt="${chart.name}" 
                     style="width: 100%; border-radius: 4px; cursor: pointer;"
                     onclick="window.open(this.src, '_blank')"
                     onerror="this.parentElement.style.display='none'">
            </div>
        `;
    });
    
    html += '</div>';
    resultDisplay.innerHTML = html;
}

/**
 * 导出CSV - 通过后端API导出两个CSV文件
 */
async function exportCSV() {
    try {
        const accuracy = document.getElementById('reconstructionAccuracy').textContent;
        if (accuracy === '--') {
            updateStatus('请先运行NEXTA重构', 'error');
            return;
        }

        updateStatus('正在导出CSV文件...', 'processing');
        
        // 通过后端API下载CSV文件
        const csvFiles = [
            { api: 'ODME_final_result', name: 'ODME_final_result.csv' },
            { api: 'output_ODTDMOE', name: 'output_ODTDMOE.csv' }
        ];
        
        let successCount = 0;
        
        for (const file of csvFiles) {
            try {
                const response = await fetch(`${RECONSTRUCTION_API}/download-csv/${file.api}`);
                if (response.ok) {
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = file.name;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    URL.revokeObjectURL(url);
                    successCount++;
                    // 延迟一下，避免浏览器阻止多个下载
                    await new Promise(resolve => setTimeout(resolve, 500));
                } else {
                    console.warn(`无法下载文件: ${file.name}`);
                }
            } catch (fetchError) {
                console.warn(`下载文件失败: ${file.name}`, fetchError);
            }
        }
        
        if (successCount === 2) {
            updateStatus(`CSV导出完成（${successCount}个文件）`, 'success');
            // 标记导出CSV按钮完成
            markStepDone('exportCSVBtn');
        } else if (successCount > 0) {
            updateStatus(`部分CSV导出完成（${successCount}/2个文件）`, 'success');
            // 标记导出CSV按钮完成
            markStepDone('exportCSVBtn');
        } else {
            updateStatus('CSV导出失败，请确保后端服务已启动', 'error');
        }
    } catch (error) {
        console.error('导出失败:', error);
        updateStatus('导出失败', 'error');
    }
}

/**
 * 生成OD分析图表
 */
async function generateODAnalysis() {
    try {
        const accuracy = document.getElementById('reconstructionAccuracy').textContent;
        if (accuracy === '--') {
            updateStatus('请先运行NEXTA重构', 'error');
            return;
        }

        const resultDisplay = document.getElementById('resultDisplay');
        resultDisplay.innerHTML = `
            <div class="result-status processing">
                <span class="loading-spinner"></span>
                <span>正在加载OD分析图表...</span>
            </div>
        `;

        // 模拟加载过程
        await new Promise(resolve => setTimeout(resolve, 800));

        // 显示真实的OD矩阵热力图
        const odImgUrl = RECONSTRUCTION_API + '/od-chart/od_matrix_heatmap.png';
        resultDisplay.innerHTML = `
            <div class="result-status success">
                <span>✓</span>
                <span>OD矩阵热力图加载成功</span>
            </div>
            <div class="result-image-container">
                <img src="${odImgUrl}" 
                     alt="OD矩阵热力图" 
                     class="result-image"
                     style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);"
                     onerror="this.parentElement.innerHTML='<div style=\\'padding:20px;text-align:center;color:#999;\\'>OD热力图未找到</div>'">
            </div>
            <div class="result-actions">
                <button class="btn btn-primary" onclick="window.open('${odImgUrl}', '_blank')">
                    <span class="btn-icon">🔍</span>
                    查看大图
                </button>
            </div>
        `;

        updateFileList('od_matrix_heatmap.png', 'OD矩阵热力图 - ' + new Date().toLocaleString());
        updateStatus('OD分析图表加载完成', 'success');
    } catch (error) {
        console.error('加载失败:', error);
        updateStatus('加载失败', 'error');
    }
}

/**
 * 下载OD数据CSV
 */
async function downloadODCSV() {
    try {
        const accuracy = document.getElementById('reconstructionAccuracy').textContent;
        if (accuracy === '--') {
            updateStatus('请先运行NEXTA重构', 'error');
            return;
        }

        updateStatus('正在读取OD数据...', 'processing');
        
        // 读取真实的CSV文件
        try {
            const response = await fetch('../../../backend/algorithms/交通流重构/output_ODMOE.csv');
            const csvContent = await response.text();
            
            downloadFile(csvContent, 'output_ODMOE.csv', 'text/csv');
            updateStatus('OD数据下载完成', 'success');
        } catch (fetchError) {
            console.warn('无法读取真实CSV文件，使用模拟数据', fetchError);
            const csvContent = generateODCSVContent();
            downloadFile(csvContent, 'output_ODMOE.csv', 'text/csv');
            updateStatus('OD数据下载完成（模拟数据）', 'success');
        }
    } catch (error) {
        console.error('下载失败:', error);
        updateStatus('下载失败', 'error');
    }
}

/**
 * 下载分析报告 - 通过后端生成并下载
 */
async function downloadReport() {
    try {
        const accuracy = document.getElementById('reconstructionAccuracy').textContent;
        if (accuracy === '--') {
            updateStatus('请先运行NEXTA重构', 'error');
            return;
        }

        updateStatus('正在生成报告...', 'processing');
        
        // 获取前端参数配置
        const params = {
            maxIterations: document.getElementById('maxIterations')?.value || '10',
            convergencyGap: document.getElementById('convergencyGap')?.value || '5.0',
            aggregationInterval: document.getElementById('aggregationInterval')?.value || '15',
            histODWeight: document.getElementById('histODWeight')?.value || '1.0'
        };
        
        console.log('正在调用后端API生成报告...');
        console.log('参数:', params);
        
        try {
            // 调用后端API生成报告
            const genResponse = await fetch(`${RECONSTRUCTION_API}/generate-report`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            
            console.log('生成报告响应状态:', genResponse.status);
            
            if (!genResponse.ok) {
                throw new Error(`生成报告请求失败: ${genResponse.status}`);
            }
            
            const genResult = await genResponse.json();
            console.log('生成报告结果:', genResult);
            
            if (genResult.success) {
                // 下载生成的报告
                console.log('正在下载报告...');
                const downloadResponse = await fetch(`${RECONSTRUCTION_API}/download-report`);
                console.log('下载响应状态:', downloadResponse.status);
                
                if (downloadResponse.ok) {
                    const blob = await downloadResponse.blob();
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    link.href = url;
                    link.download = '交通流重构分析报告.docx';
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    URL.revokeObjectURL(url);
                    updateStatus('报告下载完成', 'success');
                } else {
                    const errorText = await downloadResponse.text();
                    console.error('下载失败:', errorText);
                    throw new Error('下载报告失败');
                }
            } else {
                throw new Error(genResult.message || '生成报告失败');
            }
        } catch (apiError) {
            console.error('后端API调用失败:', apiError);
            updateStatus('后端服务未响应，请检查服务是否正常启动', 'error');
        }
    } catch (error) {
        console.error('下载失败:', error);
        updateStatus('下载失败: ' + error.message, 'error');
    }
}

/**
 * 生成OD热力图
 */
function generateODHeatmap() {
    const canvas = document.createElement('canvas');
    canvas.width = 600;
    canvas.height = 500;
    canvas.style.maxWidth = '100%';
    canvas.style.height = 'auto';
    canvas.className = 'result-image';
    
    const ctx = canvas.getContext('2d');
    
    // 背景
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // 标题
    ctx.fillStyle = '#333';
    ctx.font = 'bold 18px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('OD矩阵热力图', canvas.width / 2, 30);
    
    // 区域标签
    const zones = ['Zone A', 'Zone B', 'Zone C', 'Zone D', 'Zone E'];
    const cellSize = 80;
    const startX = 100;
    const startY = 80;
    
    // 绘制列标签
    ctx.font = '12px Arial';
    ctx.fillStyle = '#666';
    for (let i = 0; i < zones.length; i++) {
        ctx.save();
        ctx.translate(startX + i * cellSize + cellSize / 2, startY - 10);
        ctx.rotate(-Math.PI / 4);
        ctx.textAlign = 'right';
        ctx.fillText(zones[i], 0, 0);
        ctx.restore();
    }
    
    // 绘制行标签
    ctx.textAlign = 'right';
    for (let i = 0; i < zones.length; i++) {
        ctx.fillText(zones[i], startX - 10, startY + i * cellSize + cellSize / 2 + 5);
    }
    
    // 生成并绘制OD矩阵
    for (let i = 0; i < zones.length; i++) {
        for (let j = 0; j < zones.length; j++) {
            const value = i === j ? 0 : Math.floor(Math.random() * 500 + 100);
            const intensity = value / 600;
            
            // 颜色渐变：蓝色到红色
            const r = Math.floor(intensity * 255);
            const g = Math.floor((1 - intensity) * 100);
            const b = Math.floor((1 - intensity) * 255);
            
            ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
            ctx.fillRect(startX + j * cellSize, startY + i * cellSize, cellSize - 2, cellSize - 2);
            
            // 绘制数值
            ctx.fillStyle = intensity > 0.5 ? '#fff' : '#333';
            ctx.font = 'bold 14px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(value, startX + j * cellSize + cellSize / 2, startY + i * cellSize + cellSize / 2 + 5);
        }
    }
    
    // 图例
    const legendY = startY + zones.length * cellSize + 30;
    const legendWidth = 300;
    const legendHeight = 20;
    const legendX = (canvas.width - legendWidth) / 2;
    
    // 绘制渐变图例
    const gradient = ctx.createLinearGradient(legendX, 0, legendX + legendWidth, 0);
    gradient.addColorStop(0, 'rgb(0, 100, 255)');
    gradient.addColorStop(0.5, 'rgb(127, 50, 127)');
    gradient.addColorStop(1, 'rgb(255, 0, 0)');
    
    ctx.fillStyle = gradient;
    ctx.fillRect(legendX, legendY, legendWidth, legendHeight);
    
    // 图例标签
    ctx.fillStyle = '#666';
    ctx.font = '12px Arial';
    ctx.textAlign = 'left';
    ctx.fillText('低流量', legendX, legendY + legendHeight + 15);
    ctx.textAlign = 'right';
    ctx.fillText('高流量', legendX + legendWidth, legendY + legendHeight + 15);
    
    return canvas;
}

/**
 * 算法改变事件
 */
function onAlgorithmChange(e) {
    const algorithm = e.target.value;
    const descriptions = {
        'matrix_completion': '矩阵补全算法通过利用交通流数据的低秩特性，从稀疏观测数据中重构完整的交通流矩阵，适用于传感器覆盖不完整的交通网络。',
        'interpolation': '插值算法通过已知数据点推算未知数据点的值，适用于时间序列数据的填补和空间数据的补全。',
        'neural_network': '神经网络算法利用深度学习模型学习交通流的复杂模式，能够处理非线性关系和复杂的时空依赖性。'
    };

    const descriptionElement = document.getElementById('algorithmDescription');
    if (descriptionElement) {
        descriptionElement.innerHTML = `<p>${descriptions[algorithm] || '请选择算法'}</p>`;
    }
}

/**
 * 更新算法参数
 */
function updateAlgorithmParameters(algorithm) {
    const paramContainer = document.getElementById('algorithmParams');
    if (!paramContainer) return;

    // 根据算法显示不同参数
    const params = {
        'kalman_filter': ['过程噪声', '测量噪声'],
        'particle_filter': ['粒子数量', '重采样阈值'],
        'lstm': ['隐藏层数', '学习率']
    };

    const algorithmParams = params[algorithm] || [];
    paramContainer.innerHTML = algorithmParams.map(param => `
        <div class="param-item">
            <label>${param}:</label>
            <input type="number" step="0.01" value="0.1">
        </div>
    `).join('');
}

/**
 * 显示历史对话框
 */
function showHistoryDialog() {
    // 简单实现，可以后续优化为模态框
    if (reconstructionResults.length === 0) {
        Message.info('暂无历史记录');
        return;
    }

    const historyText = reconstructionResults.map((result, index) => 
        `${index + 1}. ${result.algorithm} - ${DateFormatter.format(result.created_at)} - MAE: ${result.metrics.mae}`
    ).join('\n');

    alert('重构历史记录:\n\n' + historyText);
}

/**
 * 加载指定结果
 */
async function loadResult(resultId) {
    try {
        Loading.show('加载结果...');
        
        const result = reconstructionResults.find(r => r.id === resultId);
        if (!result) return;

        // 显示结果
        displayReconstructionChart(result.result.reconstructed_flow);
        updateStatistics(result.metrics);
        
        // 更新算法选择
        const algorithmSelect = document.getElementById('algorithm');
        if (algorithmSelect) {
            algorithmSelect.value = result.algorithm;
        }

        Message.success('结果加载成功');
    } catch (error) {
        console.error('加载结果失败:', error);
        Message.error('加载结果失败: ' + error.message);
    } finally {
        Loading.hide();
    }
}

/**
 * 显示重构结果
 */
function displayReconstructionResults(data) {
    document.getElementById('reconstructionAccuracy').textContent = data.accuracy;
    document.getElementById('rmseValue').textContent = data.rmse;
    document.getElementById('processingTime').textContent = data.processingTime;
    document.getElementById('improvementRate').textContent = data.odPairCount + ' OD对';
}

/**
 * 更新状态显示
 */
function updateStatus(text, type) {
    const statusElement = document.getElementById('reconstructionStatus');
    if (statusElement) {
        statusElement.textContent = text;
        statusElement.className = 'status-value status-' + type;
    }
}

/**
 * 显示进度条
 */
function showProgress(percent) {
    const progressDisplay = document.getElementById('progressDisplay');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');

    if (progressDisplay) {
        progressDisplay.style.display = 'block';
    }
    if (progressBar) {
        progressBar.style.width = percent + '%';
    }
    if (progressText) {
        progressText.textContent = percent + '%';
    }
}

/**
 * 隐藏进度条
 */
function hideProgress() {
    const progressDisplay = document.getElementById('progressDisplay');
    if (progressDisplay) {
        setTimeout(() => {
            progressDisplay.style.display = 'none';
        }, 1000);
    }
}

/**
 * 生成CSV内容
 */
function generateCSVContent() {
    let csv = '时间,原始流量,重构流量,误差\n';
    for (let i = 0; i < 24; i++) {
        const original = Math.floor(Math.random() * 100 + 50);
        const reconstructed = original + Math.floor(Math.random() * 10 - 5);
        const error = Math.abs(original - reconstructed);
        csv += `${i}:00,${original},${reconstructed},${error}\n`;
    }
    return csv;
}

/**
 * 生成OD CSV内容
 */
function generateODCSVContent() {
    let csv = 'Origin,Destination,Flow\n';
    const zones = ['A', 'B', 'C', 'D', 'E'];
    for (let i = 0; i < zones.length; i++) {
        for (let j = 0; j < zones.length; j++) {
            if (i !== j) {
                const flow = Math.floor(Math.random() * 500 + 100);
                csv += `${zones[i]},${zones[j]},${flow}\n`;
            }
        }
    }
    return csv;
}

/**
 * 生成报告内容
 */
function generateReportContent() {
    const algorithm = document.getElementById('algorithmSelect').value;
    const accuracy = document.getElementById('reconstructionAccuracy').textContent;
    const rmse = document.getElementById('rmseValue').textContent;
    const time = document.getElementById('processingTime').textContent;
    
    return `交通流重构分析报告
===================

算法: ${algorithm}
生成时间: ${new Date().toLocaleString()}

重构结果:
- 重构精度: ${accuracy}
- RMSE: ${rmse}
- 处理时间: ${time}

数据统计:
- 数据点数: ${document.getElementById('dataPoints').textContent}
- 缺失率: ${document.getElementById('missingRate').textContent}

结论:
重构算法成功完成交通流数据的补全和优化，达到预期精度要求。
`;
}

/**
 * 下载文件
 */
function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/**
 * 更新文件列表
 */
function updateFileList(filename, meta) {
    const fileList = document.getElementById('fileList');
    if (!fileList) return;

    // 移除"暂无文件"提示
    const noFiles = fileList.querySelector('.no-files');
    if (noFiles) {
        noFiles.remove();
    }

    // 检查是否已存在
    const existingItems = fileList.querySelectorAll('.file-name');
    for (let item of existingItems) {
        if (item.textContent === filename) {
            return; // 已存在，不重复添加
        }
    }

    // 确定文件路径
    let filePath = '';
    if (filename.endsWith('.csv')) {
        filePath = '../../../backend/algorithms/交通流重构/output_ODMOE.csv';
    } else if (filename.endsWith('.png')) {
        filePath = `../../../backend/algorithms/交通流重构/od_results/${filename}`;
    }

    // 添加文件项
    const fileItem = document.createElement('div');
    fileItem.className = 'file-item';
    fileItem.innerHTML = `
        <div class="file-info">
            <span class="file-icon">${filename.endsWith('.png') ? '🖼️' : '📄'}</span>
            <div class="file-details">
                <div class="file-name">${filename}</div>
                <div class="file-meta">${meta}</div>
            </div>
        </div>
        <div class="file-actions">
            <button class="btn btn-sm btn-primary" onclick="window.open('${filePath}', '_blank')">
                查看
            </button>
        </div>
    `;
    fileList.appendChild(fileItem);
}

/**
 * 显示原始数据统计（已合并到OD数据状态卡片，保留兼容）
 */
function displayOriginalDataChart() {
    // 功能已合并到 importData() 中的卡片更新逻辑
}

/**
 * 显示重构结果统计
 */
function displayReconstructedDataChart(data) {
    data = data || {};
    const odCount = data.odPairCount || '--';
    const reconstructCard = document.getElementById('odReconstructCard');
    if (reconstructCard) {
        reconstructCard.style.borderLeftColor = '#28a745';
        reconstructCard.querySelector('div:first-child').textContent = '✅';
        document.getElementById('odReconstructStatus').innerHTML = 'OD重构完成<br>OD对 ' + odCount + ' · 完成率 100%';
        document.getElementById('odReconstructStatus').style.color = '#333';
    }

    // 显示指标卡片
    const metricsCard = document.getElementById('odMetricsCard');
    if (metricsCard) {
        metricsCard.style.display = '';
        metricsCard.style.borderLeftColor = '#2C5AA0';
        const accuracy = data.accuracy || document.getElementById('reconstructionAccuracy').textContent;
        const rmse = data.rmse || document.getElementById('rmseValue').textContent;
        const avgTime = data.avgTripTime || '--';
        const avgDist = data.avgDistance || '--';
        document.getElementById('odMetricsContent').innerHTML = '精度 ' + accuracy + ' · RMSE ' + rmse + '<br>平均行程 ' + avgTime + ' · 距离 ' + avgDist;
        document.getElementById('odMetricsContent').style.color = '#2C5AA0';
    }
    
    // 更新隐藏字段
    const odPairCount = document.getElementById('odPairCount');
    const completionRate = document.getElementById('completionRate');
    const reconstructionStatus2 = document.getElementById('reconstructionStatus2');
    if (odPairCount) odPairCount.textContent = odCount;
    if (completionRate) completionRate.textContent = '100%';
    if (reconstructionStatus2) reconstructionStatus2.textContent = '已完成';
}

/**
 * 绘制折线图
 */
function drawLineChart(ctx, width, height, labels, data, title, color) {
    const padding = 40;
    const chartWidth = width - padding * 2;
    const chartHeight = height - padding * 2;

    // 清空画布
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, width, height);

    // 绘制标题
    ctx.fillStyle = '#333';
    ctx.font = '14px Arial';
    ctx.textAlign = 'center';
    ctx.fillText(title, width / 2, 20);

    // 找出最大值
    const maxValue = Math.max(...data.filter(v => v !== null));
    const minValue = 0;

    // 绘制坐标轴
    ctx.strokeStyle = '#ddd';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding, padding);
    ctx.lineTo(padding, height - padding);
    ctx.lineTo(width - padding, height - padding);
    ctx.stroke();

    // 绘制数据点和线
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();

    let firstPoint = true;
    for (let i = 0; i < data.length; i++) {
        if (data[i] === null) continue;

        const x = padding + (i / (data.length - 1)) * chartWidth;
        const y = height - padding - ((data[i] - minValue) / (maxValue - minValue)) * chartHeight;

        if (firstPoint) {
            ctx.moveTo(x, y);
            firstPoint = false;
        } else {
            ctx.lineTo(x, y);
        }

        // 绘制数据点
        ctx.fillRect(x - 2, y - 2, 4, 4);
    }
    ctx.stroke();

    // 绘制X轴标签（每4小时显示一次）
    ctx.fillStyle = '#666';
    ctx.font = '10px Arial';
    ctx.textAlign = 'center';
    for (let i = 0; i < labels.length; i += 4) {
        const x = padding + (i / (labels.length - 1)) * chartWidth;
        ctx.fillText(labels[i], x, height - padding + 15);
    }
}

/**
 * 显示结果输出内容
 */
function displayResultOutput() {
    const resultDisplay = document.getElementById('resultDisplay');
    if (!resultDisplay) return;

    const accuracy = document.getElementById('reconstructionAccuracy').textContent;
    const rmse = document.getElementById('rmseValue').textContent;
    const time = document.getElementById('processingTime').textContent;
    const improvement = document.getElementById('improvementRate').textContent;

    resultDisplay.innerHTML = `
        <div class="result-content">
            <div class="result-summary">
                <h4 style="color: #2C5AA0; margin-bottom: 15px;">📊 重构结果摘要</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                    <div style="background: #e3f2fd; padding: 15px; border-radius: 6px;">
                        <div style="font-size: 12px; color: #666;">重构精度</div>
                        <div style="font-size: 24px; font-weight: bold; color: #2C5AA0;">${accuracy}</div>
                    </div>
                    <div style="background: #e8f5e9; padding: 15px; border-radius: 6px;">
                        <div style="font-size: 12px; color: #666;">RMSE</div>
                        <div style="font-size: 24px; font-weight: bold; color: #28a745;">${rmse}</div>
                    </div>
                    <div style="background: #fff3e0; padding: 15px; border-radius: 6px;">
                        <div style="font-size: 12px; color: #666;">处理时间</div>
                        <div style="font-size: 24px; font-weight: bold; color: #ff9800;">${time}</div>
                    </div>
                    <div style="background: #f3e5f5; padding: 15px; border-radius: 6px;">
                        <div style="font-size: 12px; color: #666;">改进率</div>
                        <div style="font-size: 24px; font-weight: bold; color: #9c27b0;">${improvement}</div>
                    </div>
                </div>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin-top: 15px;">
                    <h5 style="margin: 0 0 10px 0; color: #333;">📝 分析结论</h5>
                    <p style="margin: 5px 0; color: #666; line-height: 1.6;">
                        ✓ 交通流重构算法成功完成数据补全<br>
                        ✓ 重构精度达到 ${accuracy}，满足实际应用要求<br>
                        ✓ RMSE值为 ${rmse}，误差控制在合理范围内<br>
                        ✓ 相比原始数据，数据完整性提升 ${improvement}
                    </p>
                </div>
                
                <div style="margin-top: 20px;">
                    <h5 style="margin: 0 0 10px 0; color: #333;">📷 可视化结果</h5>
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
                        <div style="text-align: center;">
                            <img src="../../../backend/algorithms/交通流重构/od_results/od_matrix_heatmap.png" 
                                 style="width: 100%; border-radius: 4px; cursor: pointer;"
                                 onclick="window.open(this.src, '_blank')"
                                 onerror="this.style.display='none'">
                            <p style="font-size: 12px; color: #666; margin-top: 5px;">OD矩阵热力图</p>
                        </div>
                        <div style="text-align: center;">
                            <img src="../../../backend/algorithms/交通流重构/od_results/od_flow_analysis.png" 
                                 style="width: 100%; border-radius: 4px; cursor: pointer;"
                                 onclick="window.open(this.src, '_blank')"
                                 onerror="this.style.display='none'">
                            <p style="font-size: 12px; color: #666; margin-top: 5px;">OD流量分析</p>
                        </div>
                        <div style="text-align: center;">
                            <img src="../../../backend/algorithms/交通流重构/od_results/od_statistics.png" 
                                 style="width: 100%; border-radius: 4px; cursor: pointer;"
                                 onclick="window.open(this.src, '_blank')"
                                 onerror="this.style.dis
                                 play='none'">
                            <p style="font-size: 12px; color: #666; margin-top: 5px;">OD统计数据</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // 更新文件列表
    updateFileList('output_ODMOE.csv', 'OD重构结果数据 - ' + new Date().toLocaleString());
    updateFileList('od_matrix_heatmap.png', 'OD矩阵热力图 - ' + new Date().toLocaleString());
    updateFileList('od_flow_analysis.png', 'OD流量分析图 - ' + new Date().toLocaleString());
    updateFileList('od_statistics.png', 'OD统计图 - ' + new Date().toLocaleString());
}

// 窗口大小改变时重绘图表
window.addEventListener('resize', function() {
    if (currentChart) {
        currentChart.resize();
    }
});

/**
 * 重置状态 - 恢复所有按钮和数据到初始状态
 */
function resetStatus() {
    // 重置所有步骤按钮样式（恢复为蓝底）
    resetAllStepButtons();
    
    // 重置隐藏数据字段
    document.getElementById('fileCount').textContent = '0';
    document.getElementById('dataPoints').textContent = '--';
    document.getElementById('missingRate').textContent = '--';
    document.getElementById('odPairCount').textContent = '--';
    document.getElementById('completionRate').textContent = '--';
    document.getElementById('reconstructionStatus2').textContent = '--';
    document.getElementById('reconstructionAccuracy').textContent = '--';
    document.getElementById('rmseValue').textContent = '--';
    document.getElementById('processingTime').textContent = '--';
    document.getElementById('improvementRate').textContent = '--';
    
    // 重置导入卡片
    const importCard = document.getElementById('odImportCard');
    if (importCard) {
        importCard.style.borderLeftColor = '#dcdfe6';
        importCard.querySelector('div:first-child').textContent = '📥';
        document.getElementById('odImportStatus').innerHTML = '等待导入';
        document.getElementById('odImportStatus').style.color = '#999';
    }
    
    // 重置重构卡片
    const reconstructCard = document.getElementById('odReconstructCard');
    if (reconstructCard) {
        reconstructCard.style.borderLeftColor = '#dcdfe6';
        reconstructCard.querySelector('div:first-child').textContent = '🔄';
        document.getElementById('odReconstructStatus').innerHTML = '等待执行';
        document.getElementById('odReconstructStatus').style.color = '#999';
    }
    
    // 隐藏指标卡片
    const metricsCard = document.getElementById('odMetricsCard');
    if (metricsCard) metricsCard.style.display = 'none';
    
    // 重置结果展示区域
    const resultDisplay = document.getElementById('resultDisplay');
    if (resultDisplay) {
        resultDisplay.innerHTML = `
            <div class="placeholder-content">
                <div class="placeholder-icon">📈</div>
                <p>结果展示区</p>
                <p class="placeholder-hint">点击"结果分析"按钮查看结果</p>
            </div>
        `;
    }
    
    // 重置状态显示
    updateStatus('已重置', 'ready');
    
    // 使用绿色提示代替alert
    showResetToast('已重置为初始状态');
}

/**
 * 显示绿色提示
 */
function showResetToast(message) {
    var toast = document.createElement('div');
    toast.style.cssText = 'position: fixed; top: 80px; right: 20px; background: #28a745; color: white; padding: 15px 25px; border-radius: 8px; font-size: 14px; font-weight: bold; z-index: 9999; box-shadow: 0 4px 12px rgba(40, 167, 69, 0.4);';
    toast.textContent = '✓ ' + message;
    document.body.appendChild(toast);
    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';
        setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 300);
    }, 3000);
}

/**
 * 保存参数到DTASettings.txt配置文件
 */
async function saveParameters() {
    try {
        // 获取界面上的四个参数值
        const params = {
            maxIterations: document.getElementById('maxIterations')?.value || '10',
            convergencyGap: document.getElementById('convergencyGap')?.value || '5.0',
            aggregationInterval: document.getElementById('aggregationInterval')?.value || '15',
            histODWeight: document.getElementById('histODWeight')?.value || '1.0'
        };
        
        console.log('正在保存参数:', params);
        updateStatus('正在保存参数...', 'processing');
        
        // 调用后端API保存参数
        const response = await fetch(`${RECONSTRUCTION_API}/save-params`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        
        const result = await response.json();
        
        if (result.success) {
            updateStatus('参数保存成功', 'success');
            // 标记保存按钮完成（变为白底蓝边）
            markStepDone('saveParamsBtn');
            console.log('参数已保存到DTASettings.txt');
        } else {
            updateStatus('保存失败: ' + result.message, 'error');
        }
    } catch (error) {
        console.error('保存参数失败:', error);
        updateStatus('后端服务未响应，请检查服务是否正常启动', 'error');
    }
}

/**
 * 启动NEXTA路网编辑器
 */
async function launchNEXTA() {
    try {
        updateStatus('正在启动NEXTA路网编辑器...', 'processing');
        
        const response = await fetch(`${RECONSTRUCTION_API}/launch-nexta`, {
            method: 'POST'
        });
        const result = await response.json();
        
        if (result.success) {
            updateStatus('NEXTA已启动，请在外部窗口中编辑路网', 'success');
        } else {
            updateStatus('启动失败: ' + result.message, 'error');
        }
    } catch (error) {
        console.error('启动NEXTA失败:', error);
        updateStatus('后端服务未响应', 'error');
    }
}

/**
 * 导出路网编辑文档（docx）
 */
async function exportNetworkDoc() {
    try {
        updateStatus('正在生成路网编辑文档...', 'processing');
        
        const response = await fetch(`${RECONSTRUCTION_API}/export-network-doc`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = '路网编辑说明文档.docx';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            updateStatus('路网编辑文档导出完成', 'success');
        } else {
            const result = await response.json();
            updateStatus('导出失败: ' + (result.message || result.error), 'error');
        }
    } catch (error) {
        console.error('导出路网文档失败:', error);
        updateStatus('后端服务未响应', 'error');
    }
}


// ==================== 路网拓扑预览 ====================

async function loadNetworkPreview() {
    const container = document.getElementById('networkPreviewContainer');
    const img = document.getElementById('networkImage');
    const btn = document.getElementById('loadNetworkBtn');
    if (!container || !img) return;

    try {
        if (btn) { btn.disabled = true; btn.textContent = '正在生成路网图...'; }
        const url = `${RECONSTRUCTION_API}/network-image?t=${Date.now()}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error('生成路网图失败');
        const blob = await response.blob();
        const imgUrl = URL.createObjectURL(blob);
        img.src = imgUrl;
        container.style.display = 'block';
        updateStatus('路网拓扑图加载完成', 'success');

        // 点击图片放大查看
        img.onclick = function() {
            const win = window.open('', '_blank');
            win.document.write('<html><head><title>路网拓扑图</title></head><body style="margin:0;background:#f0f4f8;display:flex;justify-content:center;align-items:center;min-height:100vh"><img src="' + imgUrl + '" style="max-width:95vw;max-height:95vh;" /></body></html>');
        };
    } catch (error) {
        console.error('加载路网图失败:', error);
        updateStatus('路网图加载失败: ' + error.message, 'error');
    } finally {
        if (btn) { btn.innerHTML = '<span class="btn-icon"></span> 查看路网拓扑图'; btn.disabled = false; }
    }
}

// ==================== 服务器状态检测 ====================
(function() {
    function checkServerStatus() {
        var el = document.getElementById('serverStatus');
        if (!el) return;
        fetch('/', { method: 'GET' })
            .then(function(r) {
                if (r.ok || r.status === 404 || r.status === 405) {
                    el.textContent = '服务器: 已连接 ✓';
                    el.style.color = '#28a745';
                } else { throw new Error(); }
            })
            .catch(function() {
                el.textContent = '服务器: 未连接 ✗';
                el.style.color = '#dc3545';
            });
    }
    document.addEventListener('DOMContentLoaded', function() {
        checkServerStatus();
        setInterval(checkServerStatus, 30000);
    });
})();
