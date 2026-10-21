/**
 * 多源数据融合功能教学模块 - JavaScript交互脚本
 */

// 全局变量
let fusionConfig = {
    algorithm: 'bayesian_fusion',
    dataSources: {
        yolo: { enabled: true, status: 'ready' },
        lidar: { enabled: true, status: 'ready' },
        camera: { enabled: false, status: 'disabled' }
    },
    targetClasses: {
        car: { enabled: true, lambda: 0.10 },
        cyclist: { enabled: true, lambda: 0.15 },
        pedestrian: { enabled: true, lambda: 0.20 },
        bus: { enabled: false, lambda: 0.08 },
        truck: { enabled: false, lambda: 0.08 }
    },
    parameters: {
        priorProbability: 0.1,
        iouThreshold: 0.3,
        sampleSize: 50
    },
    status: 'ready'
};

// 算法描述
const algorithmDescriptions = {
    decision_fusion: '决策级融合：融合YOLO图像检测和LiDAR点云检测结果，支持多种目标类别，计算各类别的平均精度(AP)和总体mAP',
    bayesian_fusion: '贝叶斯融合：使用贝叶斯方法融合YOLO检测置信度和点云熵信息，支持概率级别的多模态数据融合',
    enhanced_fusion: '增强融合：结合决策级和概率级融合的优势，提供更准确的多模态数据融合结果'
};

// 目标类别信息
const targetClassInfo = {
    car: { name: '小汽车', defaultLambda: 0.10, description: '普通乘用车辆' },
    cyclist: { name: '骑行者', defaultLambda: 0.15, description: '骑自行车的人员' },
    pedestrian: { name: '行人', defaultLambda: 0.20, description: '步行的人员' },
    bus: { name: '公交车', defaultLambda: 0.08, description: '大型公共交通车辆' },
    truck: { name: '卡车', defaultLambda: 0.08, description: '货运车辆' }
};

// 数据生成器
const dataGenerator = {
    generateYOLOResults(sampleSize, enabledClasses) {
        const results = [];
        for (let i = 0; i < sampleSize; i++) {
            const classNames = Object.keys(enabledClasses).filter(key => enabledClasses[key]);
            const className = classNames[Math.floor(Math.random() * classNames.length)];
            results.push({
                frame: `frame_${String(i).padStart(6, '0')}`,
                class: className,
                confidence: Math.random() * 0.4 + 0.6, // 0.6-1.0
                bbox: {
                    x: Math.random() * 500 + 50,
                    y: Math.random() * 300 + 50,
                    width: Math.random() * 100 + 50,
                    height: Math.random() * 80 + 40
                }
            });
        }
        return results;
    },

    generateEntropyResults(sampleSize, enabledClasses) {
        const results = [];
        for (let i = 0; i < sampleSize; i++) {
            const classNames = Object.keys(enabledClasses).filter(key => enabledClasses[key]);
            const className = classNames[Math.floor(Math.random() * classNames.length)];
            results.push({
                frame: `frame_${String(i).padStart(6, '0')}`,
                class: className,
                entropy: Math.random() * 3.0 + 0.5, // 0.5-3.5
                pointCount: Math.floor(Math.random() * 1000) + 100
            });
        }
        return results;
    },

    performBayesianFusion(yoloResults, entropyResults, config) {
        const fusionResults = [];
        const prior = config.parameters.priorProbability;

        for (let i = 0; i < Math.min(yoloResults.length, entropyResults.length); i++) {
            const yolo = yoloResults[i];
            const entropy = entropyResults[i];

            if (yolo.class === entropy.class) {
                const lambda = config.targetClasses[yolo.class].lambda;
                const lidarProb = Math.exp(-lambda * entropy.entropy);

                // 贝叶斯融合公式
                const numerator = yolo.confidence * lidarProb * prior;
                const denominator = numerator + (1 - yolo.confidence) * (1 - lidarProb) * (1 - prior);
                const fusionProb = numerator / denominator;

                fusionResults.push({
                    frame: yolo.frame,
                    class: yolo.class,
                    yoloConfidence: yolo.confidence,
                    lidarProb: lidarProb,
                    entropy: entropy.entropy,
                    fusionProb: fusionProb,
                    improvement: fusionProb - yolo.confidence
                });
            }
        }

        return fusionResults;
    }
};

// 数据存储
let generatedData = {
    yoloResults: [],
    entropyResults: [],
    fusionResults: [],
    statistics: {}
};

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function () {
    initializeEventListeners();
    updateDisplay();
    updateAlgorithmDescription();
    console.log('多源数据融合教学模块已加载');
});

/**
 * 初始化事件监听器
 */
function initializeEventListeners() {
    // 算法选择
    document.getElementById('algorithmSelect').addEventListener('change', handleAlgorithmChange);

    // 数据源选择
    ['yolo', 'lidar', 'camera'].forEach(source => {
        document.getElementById(source + 'Source').addEventListener('change', () => handleSourceToggle(source));
    });

    // 目标类别选择
    Object.keys(targetClassInfo).forEach(className => {
        document.getElementById(className + 'Class').addEventListener('change', () => handleClassToggle(className));
        document.getElementById(className + 'Lambda').addEventListener('input', () => handleLambdaChange(className));
    });

    // 参数配置
    document.getElementById('priorProbability').addEventListener('input', handleParameterChange);
    document.getElementById('iouThreshold').addEventListener('input', handleParameterChange);
    document.getElementById('sampleSize').addEventListener('input', handleParameterChange);

    // 控制按钮
    document.getElementById('generateDataBtn').addEventListener('click', generateSampleData);
    document.getElementById('startFusionBtn').addEventListener('click', startFusion);
    document.getElementById('generateVisualizationBtn').addEventListener('click', generateVisualization);
    document.getElementById('resetBtn').addEventListener('click', resetParameters);
    document.getElementById('backBtn').addEventListener('click', goBack);

    // 可视化按钮
    document.getElementById('generateOverviewBtn').addEventListener('click', () => generateChart('overview'));
    document.getElementById('generateDetailedBtn').addEventListener('click', () => generateChart('detailed'));
    document.getElementById('generateAlgorithmDemoBtn').addEventListener('click', () => generateChart('algorithm'));
    document.getElementById('exportReportBtn').addEventListener('click', () => exportReport());
    
    // 结果输出按钮
    document.getElementById('generateFusionOverviewBtn').addEventListener('click', handleGenerateFusionOverview);
    document.getElementById('generatePerformanceAnalysisBtn').addEventListener('click', handleGeneratePerformanceAnalysis);
    document.getElementById('generateAlgorithmReportBtn').addEventListener('click', handleGenerateAlgorithmReport);
}

/**
 * 处理算法选择变化
 */
function handleAlgorithmChange() {
    const select = document.getElementById('algorithmSelect');
    fusionConfig.algorithm = select.value;
    updateAlgorithmDescription();
}

/**
 * 更新算法描述
 */
function updateAlgorithmDescription() {
    document.getElementById('algorithmDescription').innerHTML =
        `<p>${algorithmDescriptions[fusionConfig.algorithm]}</p>`;
}

/**
 * 处理数据源开关
 */
function handleSourceToggle(sourceType) {
    const checkbox = document.getElementById(sourceType + 'Source');
    fusionConfig.dataSources[sourceType].enabled = checkbox.checked;

    // 更新状态显示
    const statusElement = document.getElementById(sourceType + 'Status');
    if (checkbox.checked) {
        fusionConfig.dataSources[sourceType].status = 'ready';
        statusElement.textContent = '就绪';
        statusElement.className = 'source-status status-ready';
    } else {
        fusionConfig.dataSources[sourceType].status = 'disabled';
        statusElement.textContent = '禁用';
        statusElement.className = 'source-status status-disabled';
    }

    updateDisplay();
}

/**
 * 处理目标类别开关
 */
function handleClassToggle(className) {
    const checkbox = document.getElementById(className + 'Class');
    const lambdaInput = document.getElementById(className + 'Lambda');

    fusionConfig.targetClasses[className].enabled = checkbox.checked;
    lambdaInput.disabled = !checkbox.checked;

    updateDisplay();
}

/**
 * 处理Lambda参数变化
 */
function handleLambdaChange(className) {
    const input = document.getElementById(className + 'Lambda');
    fusionConfig.targetClasses[className].lambda = parseFloat(input.value);
}

/**
 * 处理参数变化
 */
function handleParameterChange() {
    fusionConfig.parameters.priorProbability = parseFloat(document.getElementById('priorProbability').value);
    fusionConfig.parameters.iouThreshold = parseFloat(document.getElementById('iouThreshold').value);
    fusionConfig.parameters.sampleSize = parseInt(document.getElementById('sampleSize').value);

    document.getElementById('priorValue').textContent = fusionConfig.parameters.priorProbability;
    document.getElementById('iouValue').textContent = fusionConfig.parameters.iouThreshold;
    document.getElementById('sampleValue').textContent = fusionConfig.parameters.sampleSize;
}

/**
 * 生成样本数据
 */
async function generateSampleData() {
    const enabledClasses = {};
    Object.keys(fusionConfig.targetClasses).forEach(key => {
        if (fusionConfig.targetClasses[key].enabled) {
            enabledClasses[key] = true;
        }
    });

    if (Object.keys(enabledClasses).length === 0) {
        showNotification('请至少选择一个目标类别！', 'warning');
        return;
    }

    // 更新状态
    updateFusionStatus('generating', '生成数据中...');
    updateProgress(0);

    const sampleSize = fusionConfig.parameters.sampleSize;

    // 生成YOLO结果
    updateProgress(25);
    generatedData.yoloResults = dataGenerator.generateYOLOResults(sampleSize, enabledClasses);
    updateDataStatus('imageDataStatus', '已生成');
    document.getElementById('imageDataCount').textContent = sampleSize + ' 帧';
    document.getElementById('yoloResultCount').textContent = generatedData.yoloResults.length;
    // 更新左侧数据源计数
    document.getElementById('yoloCount').textContent = generatedData.yoloResults.length + ' 个目标';
    document.getElementById('yoloStatus').textContent = '已生成';
    document.getElementById('yoloStatus').className = 'source-status status-ready';

    await new Promise(resolve => setTimeout(resolve, 500));

    // 生成点云熵结果
    updateProgress(50);
    generatedData.entropyResults = dataGenerator.generateEntropyResults(sampleSize, enabledClasses);
    updateDataStatus('pointCloudStatus', '已生成');
    document.getElementById('pointCloudCount').textContent = sampleSize + ' 帧';
    document.getElementById('entropyResultCount').textContent = generatedData.entropyResults.length;
    // 更新左侧数据源计数
    document.getElementById('lidarCount').textContent = generatedData.entropyResults.length + ' 个目标';
    document.getElementById('lidarStatus').textContent = '已生成';
    document.getElementById('lidarStatus').className = 'source-status status-ready';

    await new Promise(resolve => setTimeout(resolve, 500));

    // 生成标注和相机参数
    updateProgress(75);
    const totalTargets = generatedData.yoloResults.length + generatedData.entropyResults.length;
    updateDataStatus('labelDataStatus', '已生成');
    document.getElementById('labelDataCount').textContent = totalTargets + ' 个目标';
    updateDataStatus('cameraParamStatus', '已生成');
    document.getElementById('cameraParamCount').textContent = '内外参';

    await new Promise(resolve => setTimeout(resolve, 500));

    // 显示结果
    updateProgress(100);
    displayYOLOResults(generatedData.yoloResults.slice(0, 5));
    displayEntropyResults(generatedData.entropyResults.slice(0, 5));

    updateFusionStatus('data_ready', '数据已生成');
    showNotification('样本数据生成完成！', 'success');
}

/**
 * 开始融合计算
 */
async function startFusion() {
    if (generatedData.yoloResults.length === 0 || generatedData.entropyResults.length === 0) {
        showNotification('请先生成样本数据！', 'warning');
        return;
    }

    const enabledSources = Object.keys(fusionConfig.dataSources)
        .filter(key => fusionConfig.dataSources[key].enabled);

    if (enabledSources.length < 2) {
        showNotification('请至少选择两个数据源进行融合！', 'warning');
        return;
    }

    // 更新状态
    updateFusionStatus('processing', '融合计算中...');
    updateProgress(0);

    // 执行贝叶斯融合
    updateProgress(30);
    generatedData.fusionResults = dataGenerator.performBayesianFusion(
        generatedData.yoloResults,
        generatedData.entropyResults,
        fusionConfig
    );

    await new Promise(resolve => setTimeout(resolve, 1000));

    // 计算统计信息
    updateProgress(70);
    generatedData.statistics = calculateStatistics(generatedData.fusionResults);

    await new Promise(resolve => setTimeout(resolve, 500));

    // 显示结果
    updateProgress(100);
    displayFusionResults(generatedData.fusionResults.slice(0, 5));
    updatePerformanceMetrics(generatedData.statistics);

    updateFusionStatus('completed', '融合完成');
    showNotification('数据融合计算完成！', 'success');
}



/**
 * 更新数据状态
 */
function updateDataStatus(elementId, status, count = '') {
    const element = document.getElementById(elementId);
    if (element) {
        if (elementId.includes('Status')) {
            element.textContent = status;
            element.className = status === '已生成' ? 'status-value status-ready' : 'status-value';
        } else if (elementId.includes('Count')) {
            element.textContent = count;
        }
    }
}

/**
 * 更新进度
 */
function updateProgress(percentage) {
    document.getElementById('fusionProgressBar').style.width = percentage + '%';
    document.getElementById('progressText').textContent = percentage + '%';
}

/**
 * 显示YOLO结果
 */
function displayYOLOResults(results) {
    let html = '<div class="result-data">';
    results.forEach((result, index) => {
        html += `
            <div class="data-item">
                <span class="data-label">${result.frame}</span>
                <span class="data-class">${targetClassInfo[result.class].name}</span>
                <span class="data-confidence">${result.confidence.toFixed(3)}</span>
            </div>
        `;
    });
    html += '</div>';
    document.getElementById('yoloResults').innerHTML = html;
}

/**
 * 显示点云熵结果
 */
function displayEntropyResults(results) {
    let html = '<div class="result-data">';
    results.forEach((result, index) => {
        html += `
            <div class="data-item">
                <span class="data-label">${result.frame}</span>
                <span class="data-class">${targetClassInfo[result.class].name}</span>
                <span class="data-entropy">${result.entropy.toFixed(3)}</span>
            </div>
        `;
    });
    html += '</div>';
    document.getElementById('entropyResults').innerHTML = html;
}

/**
 * 显示融合结果
 */
function displayFusionResults(results) {
    let html = '<div class="result-data">';
    results.forEach((result, index) => {
        const improvementClass = result.improvement > 0 ? 'positive' : 'negative';
        html += `
            <div class="data-item">
                <span class="data-label">${result.frame}</span>
                <span class="data-class">${targetClassInfo[result.class].name}</span>
                <span class="data-fusion">${result.fusionProb.toFixed(3)}</span>
                <span class="data-improvement ${improvementClass}">${result.improvement > 0 ? '+' : ''}${result.improvement.toFixed(3)}</span>
            </div>
        `;
    });
    html += '</div>';
    document.getElementById('fusionResults').innerHTML = html;
    document.getElementById('fusionResultCount').textContent = results.length;
}

/**
 * 计算统计信息
 */
function calculateStatistics(fusionResults) {
    if (fusionResults.length === 0) return {};

    const avgFusionProb = fusionResults.reduce((sum, r) => sum + r.fusionProb, 0) / fusionResults.length;
    const avgImprovement = fusionResults.reduce((sum, r) => sum + r.improvement, 0) / fusionResults.length;
    const positiveImprovements = fusionResults.filter(r => r.improvement > 0).length;
    const fusionEfficiency = (positiveImprovements / fusionResults.length) * 100;

    return {
        avgFusionProb,
        avgImprovement,
        fusionEfficiency,
        totalSamples: fusionResults.length,
        positiveImprovements
    };
}

/**
 * 更新性能指标
 */
function updatePerformanceMetrics(statistics) {
    document.getElementById('avgFusionProb').textContent = statistics.avgFusionProb.toFixed(3);
    document.getElementById('avgImprovement').textContent = (statistics.avgImprovement * 100).toFixed(1) + '%';
    document.getElementById('fusionEfficiency').textContent = statistics.fusionEfficiency.toFixed(1) + '%';
    document.getElementById('processingTime').textContent = (statistics.totalSamples * 2.5).toFixed(0) + 'ms';
}

/**
 * 生成可视化图表
 */
function generateVisualization() {
    if (generatedData.fusionResults.length === 0) {
        showNotification('请先完成融合计算！', 'warning');
        return;
    }

    showNotification('正在生成所有可视化图表...', 'info');

    setTimeout(() => {
        generateChart('all');
        showNotification('可视化图表生成完成！', 'success');
    }, 1500);
}

/**
 * 生成图表
 */
function generateChart(type) {
    if (generatedData.fusionResults.length === 0) {
        showNotification('请先完成融合计算！', 'warning');
        return;
    }

    const visualizationDisplay = document.getElementById('visualizationDisplay');
    let content = '';

    switch (type) {
        case 'overview':
            content = generateOverviewDisplay();
            showNotification('融合概览分析图已生成', 'success');
            break;
        case 'detailed':
            content = generateDetailedDisplay();
            showNotification('详细性能分析图已生成', 'success');
            break;
        case 'algorithm':
            content = generateAlgorithmDisplay();
            showNotification('算法演示图已生成', 'success');
            break;
        case 'all':
            content = generateAllChartsDisplay();
            break;
    }

    visualizationDisplay.innerHTML = content;
}

/**
 * 生成概览分析显示
 */
function generateOverviewDisplay() {
    const stats = generatedData.statistics;
    return `
        <div class="chart-result">
            <h4>📊 融合概览分析图</h4>
            <div class="chart-summary">
                <p><strong>图表类型：</strong>各类别平均性能对比 + YOLO置信度vs融合概率散点图</p>
                <p><strong>生成时间：</strong>${new Date().toLocaleString()}</p>
                <p><strong>数据基础：</strong>${stats.totalSamples} 个融合样本</p>
            </div>
            <div class="chart-data">
                <h5>分析模块：</h5>
                <ul>
                    <li>各类别平均性能对比：显示YOLO、点云和融合概率的对比</li>
                    <li>YOLO置信度 vs 融合概率散点图：展示两者的相关性</li>
                    <li>点云熵分布：显示点云数据的不确定性分布</li>
                    <li>融合改进效果：各类别的融合改进情况</li>
                </ul>
            </div>
            <div class="chart-actions">
                <button class="btn btn-sm btn-secondary" onclick="downloadChart('overview')">下载图表</button>
                <button class="btn btn-sm btn-info" onclick="viewChartDetails('overview')">查看详情</button>
            </div>
        </div>
    `;
}

/**
 * 生成详细分析显示
 */
function generateDetailedDisplay() {
    const stats = generatedData.statistics;
    return `
        <div class="chart-result">
            <h4>📈 详细性能分析图</h4>
            <div class="chart-summary">
                <p><strong>包含模块：</strong>6个详细性能分析图表</p>
                <p><strong>文件名：</strong>detailed_performance_analysis.png</p>
                <p><strong>改进效率：</strong>${stats.fusionEfficiency.toFixed(1)}%</p>
            </div>
            <div class="analysis-modules">
                <h5>分析模块：</h5>
                <ul>
                    <li>各类别性能箱线图：显示融合概率的分布情况</li>
                    <li>熵值 vs 点云概率关系：展示指数衰减关系</li>
                    <li>融合改进热力图：按熵值和YOLO置信度分组的改进效果</li>
                    <li>性能雷达图：多维度性能对比</li>
                    <li>置信度分布对比：YOLO vs 融合概率分布</li>
                    <li>性能统计表：详细数值统计</li>
                </ul>
            </div>
            <div class="chart-actions">
                <button class="btn btn-sm btn-secondary" onclick="downloadChart('detailed')">下载图表</button>
                <button class="btn btn-sm btn-info" onclick="viewChartDetails('detailed')">查看详情</button>
            </div>
        </div>
    `;
}

/**
 * 生成算法演示显示
 */
function generateAlgorithmDisplay() {
    return `
        <div class="chart-result">
            <h4>🔬 融合算法演示图</h4>
            <div class="chart-summary">
                <p><strong>演示内容：</strong>贝叶斯融合算法的完整演示</p>
                <p><strong>文件名：</strong>fusion_algorithm_demo.png</p>
                <p><strong>算法类型：</strong>${fusionConfig.algorithm}</p>
            </div>
            <div class="algorithm-modules">
                <h5>演示模块：</h5>
                <ul>
                    <li>贝叶斯融合函数：展示融合公式的效果</li>
                    <li>不同点云概率下的融合效果：参数敏感性分析</li>
                    <li>熵值对点云概率的影响：λ参数的影响</li>
                    <li>融合算法流程图：算法步骤可视化</li>
                </ul>
            </div>
            <div class="fusion-formula">
                <h5>贝叶斯融合公式：</h5>
                <p>P(目标|YOLO,LiDAR) = P(YOLO|目标) × P(LiDAR|目标) × P(目标) / [分母归一化项]</p>
            </div>
            <div class="chart-actions">
                <button class="btn btn-sm btn-secondary" onclick="downloadChart('algorithm')">下载图表</button>
                <button class="btn btn-sm btn-info" onclick="viewChartDetails('algorithm')">查看详情</button>
            </div>
        </div>
    `;
}

/**
 * 生成所有图表显示
 */
function generateAllChartsDisplay() {
    const stats = generatedData.statistics;
    return `
        <div class="chart-result">
            <h4>🎯 完整可视化分析报告</h4>
            <div class="chart-summary">
                <p><strong>生成内容：</strong>所有类型的可视化图表和分析报告</p>
                <p><strong>生成时间：</strong>${new Date().toLocaleString()}</p>
                <p><strong>数据基础：</strong>${stats.totalSamples} 个融合样本，平均改进 ${(stats.avgImprovement * 100).toFixed(1)}%</p>
            </div>
            <div class="all-charts-summary">
                <h5>生成的文件：</h5>
                <ul>
                    <li>📊 fusion_overview_analysis.png - 融合概览分析图</li>
                    <li>📈 detailed_performance_analysis.png - 详细性能分析图</li>
                    <li>🔬 fusion_algorithm_demo.png - 融合算法演示图</li>
                    <li>📄 fusion_analysis_report.txt - 详细分析报告</li>
                    <li>📋 fusion_data.csv - 原始数据导出</li>
                </ul>
            </div>
            <div class="performance-summary">
                <h5>性能总结：</h5>
                <div class="summary-grid">
                    <div class="summary-item">
                        <span class="summary-label">平均融合概率</span>
                        <span class="summary-value">${stats.avgFusionProb.toFixed(3)}</span>
                    </div>
                    <div class="summary-item">
                        <span class="summary-label">平均改进幅度</span>
                        <span class="summary-value">${(stats.avgImprovement * 100).toFixed(1)}%</span>
                    </div>
                    <div class="summary-item">
                        <span class="summary-label">融合效率</span>
                        <span class="summary-value">${stats.fusionEfficiency.toFixed(1)}%</span>
                    </div>
                    <div class="summary-item">
                        <span class="summary-label">正向改进样本</span>
                        <span class="summary-value">${stats.positiveImprovements}/${stats.totalSamples}</span>
                    </div>
                </div>
            </div>
            <div class="chart-actions">
                <button class="btn btn-sm btn-primary" onclick="downloadAllCharts()">下载所有图表</button>
                <button class="btn btn-sm btn-info" onclick="viewFullReport()">查看完整报告</button>
            </div>
        </div>
    `;
}

/**
 * 导出分析报告
 */
function exportReport() {
    if (generatedData.fusionResults.length === 0) {
        showNotification('请先完成融合计算！', 'warning');
        return;
    }

    showNotification('正在导出分析报告...', 'info');

    setTimeout(() => {
        showNotification('分析报告导出完成！', 'success');
    }, 1000);
}

/**
 * 下载图表（模拟）
 */
function downloadChart(type) {
    const typeNames = {
        'overview': '融合概览分析图',
        'detailed': '详细性能分析图',
        'algorithm': '算法演示图'
    };

    showNotification(`正在下载${typeNames[type]}...`, 'info');
    setTimeout(() => {
        showNotification(`${typeNames[type]}下载完成`, 'success');
    }, 1000);
}

/**
 * 查看图表详情（模拟）
 */
function viewChartDetails(type) {
    const typeNames = {
        'overview': '融合概览分析图',
        'detailed': '详细性能分析图',
        'algorithm': '算法演示图'
    };

    showNotification(`正在打开${typeNames[type]}详情...`, 'info');
}

/**
 * 下载所有图表（模拟）
 */
function downloadAllCharts() {
    showNotification('正在打包下载所有图表...', 'info');
    setTimeout(() => {
        showNotification('所有图表下载完成', 'success');
    }, 2000);
}

/**
 * 查看完整报告（模拟）
 */
function viewFullReport() {
    showNotification('正在生成完整分析报告...', 'info');
    setTimeout(() => {
        showNotification('完整报告已生成', 'success');
    }, 1500);
}

/**
 * 更新融合状态
 */
function updateFusionStatus(status, text) {
    fusionConfig.status = status;
    const statusElement = document.getElementById('fusionStatus');
    statusElement.textContent = text;
    statusElement.className = `status-value status-${status.replace('_', '-')}`;
}

/**
 * 更新显示信息
 */
function updateDisplay() {
    // 更新数据源计数等信息
    const enabledSources = Object.keys(fusionConfig.dataSources)
        .filter(key => fusionConfig.dataSources[key].enabled);

    const enabledClasses = Object.keys(fusionConfig.targetClasses)
        .filter(key => fusionConfig.targetClasses[key].enabled);

    // 可以在这里添加更多的显示更新逻辑
}

/**
 * 重置参数
 */
function resetParameters() {
    // 重置配置到默认值
    fusionConfig = {
        algorithm: 'bayesian_fusion',
        dataSources: {
            yolo: { enabled: true, status: 'ready' },
            lidar: { enabled: true, status: 'ready' },
            camera: { enabled: false, status: 'disabled' }
        },
        targetClasses: {
            car: { enabled: true, lambda: 0.10 },
            cyclist: { enabled: true, lambda: 0.15 },
            pedestrian: { enabled: true, lambda: 0.20 },
            bus: { enabled: false, lambda: 0.08 },
            truck: { enabled: false, lambda: 0.08 }
        },
        parameters: {
            priorProbability: 0.1,
            iouThreshold: 0.3,
            sampleSize: 50
        },
        status: 'ready'
    };

    // 重置界面
    document.getElementById('algorithmSelect').value = 'bayesian_fusion';
    updateAlgorithmDescription();

    // 重置数据源
    document.getElementById('yoloSource').checked = true;
    document.getElementById('lidarSource').checked = true;
    document.getElementById('cameraSource').checked = false;

    // 重置目标类别
    Object.keys(targetClassInfo).forEach(className => {
        const defaultEnabled = ['car', 'cyclist', 'pedestrian'].includes(className);
        document.getElementById(className + 'Class').checked = defaultEnabled;
        document.getElementById(className + 'Lambda').value = targetClassInfo[className].defaultLambda;
        document.getElementById(className + 'Lambda').disabled = !defaultEnabled;
    });

    // 重置参数
    document.getElementById('priorProbability').value = 0.1;
    document.getElementById('priorValue').textContent = '0.1';
    document.getElementById('iouThreshold').value = 0.3;
    document.getElementById('iouValue').textContent = '0.3';
    document.getElementById('sampleSize').value = 50;
    document.getElementById('sampleValue').textContent = '50';

    // 清空数据和结果
    generatedData = {
        yoloResults: [],
        entropyResults: [],
        fusionResults: [],
        statistics: {}
    };

    // 重置状态显示
    updateFusionStatus('ready', '就绪');
    updateProgress(0);

    // 重置数据状态
    ['imageDataStatus', 'pointCloudStatus', 'labelDataStatus', 'cameraParamStatus'].forEach(id => {
        updateDataStatus(id, '未生成');
    });

    // 重置计数
    ['yoloResultCount', 'entropyResultCount', 'fusionResultCount'].forEach(id => {
        document.getElementById(id).textContent = '0';
    });

    // 重置性能指标
    ['avgFusionProb', 'avgImprovement', 'fusionEfficiency', 'processingTime'].forEach(id => {
        document.getElementById(id).textContent = '--';
    });

    // 重置可视化显示
    document.getElementById('visualizationDisplay').innerHTML = `
        <div class="placeholder-content">
            <div class="placeholder-icon">📊</div>
            <p>可视化图表展示区</p>
            <p class="placeholder-hint">点击上方按钮生成相应的分析图表</p>
        </div>
    `;

    updateDisplay();
    showNotification('参数已重置', 'success');
}

/**
 * 显示通知
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        z-index: 2000;
        animation: slideInRight 0.3s ease;
        max-width: 300px;
    `;

    const colors = {
        'success': '#28a745',
        'error': '#dc3545',
        'warning': '#ffc107',
        'info': '#2C5AA0'
    };
    notification.style.backgroundColor = colors[type] || colors.info;

    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

/**
 * 返回上级页面
 */
function goBack() {
    if (confirm('确定要返回上级页面吗？未保存的配置将丢失。')) {
        window.location.href = '../../student.html';
    }
}

// ==================== 结果输出功能 ====================

// 生成的文件列表
let generatedFiles = [];

// 处理生成融合概览图表
async function handleGenerateFusionOverview() {
    const resultDisplay = document.getElementById('resultDisplay');
    
    // 显示处理中状态
    resultDisplay.innerHTML = `
        <div class="result-content">
            <div class="result-status processing">
                <span class="loading-spinner"></span>
                <span>正在生成融合概览图表...</span>
            </div>
        </div>
    `;
    
    // 模拟调用Python脚本生成图表
    setTimeout(() => {
        const imagePath = '../../../backend/algorithms/多源数据融合/visualization_results/fusion_overview_analysis.png';
        const timestamp = new Date().toLocaleString();
        
        resultDisplay.innerHTML = `
            <div class="result-content">
                <div class="result-status success">
                    <span>✓</span>
                    <span>融合概览图表生成成功 - ${timestamp}</span>
                </div>
                <div class="result-image-container">
                    <img src="${imagePath}" alt="融合概览图表" class="result-image" 
                         onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22400%22 height=%22300%22><rect width=%22400%22 height=%22300%22 fill=%22%23f0f0f0%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22>图表预览</text></svg>'">
                </div>
                <div class="result-actions">
                    <button class="btn btn-sm btn-primary" onclick="openResultFile('fusion_overview_analysis.png')">打开图表</button>
                    <button class="btn btn-sm btn-secondary" onclick="openResultFolder()">打开文件夹</button>
                </div>
            </div>
        `;
        
        // 添加到文件列表
        addGeneratedFile({
            name: 'fusion_overview_analysis.png',
            type: 'image',
            size: '2.8 MB',
            time: timestamp,
            path: 'algorithm/多源数据融合/visualization_results/'
        });
        
        showNotification('融合概览图表生成成功', 'success');
    }, 2000);
}

// 处理生成性能分析报告
async function handleGeneratePerformanceAnalysis() {
    const resultDisplay = document.getElementById('resultDisplay');
    
    // 显示处理中状态
    resultDisplay.innerHTML = `
        <div class="result-content">
            <div class="result-status processing">
                <span class="loading-spinner"></span>
                <span>正在生成性能分析报告...</span>
            </div>
        </div>
    `;
    
    // 模拟调用Python脚本生成报告
    setTimeout(() => {
        const imagePath = '../../../backend/algorithms/多源数据融合/visualization_results/detailed_performance_analysis.png';
        const timestamp = new Date().toLocaleString();
        
        resultDisplay.innerHTML = `
            <div class="result-content">
                <div class="result-status success">
                    <span>✓</span>
                    <span>性能分析报告生成成功 - ${timestamp}</span>
                </div>
                <div class="result-image-container">
                    <img src="${imagePath}" alt="性能分析图表" class="result-image"
                         onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22400%22 height=%22300%22><rect width=%22400%22 height=%22300%22 fill=%22%23f0f0f0%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22>图表预览</text></svg>'">
                </div>
                <div class="result-actions">
                    <button class="btn btn-sm btn-primary" onclick="openResultFile('detailed_performance_analysis.png')">打开图表</button>
                    <button class="btn btn-sm btn-success" onclick="openResultFile('performance_analysis_report.docx')">Word报告</button>
                    <button class="btn btn-sm btn-secondary" onclick="openResultFolder()">打开文件夹</button>
                </div>
            </div>
        `;
        
        // 添加到文件列表
        addGeneratedFile({
            name: 'detailed_performance_analysis.png',
            type: 'image',
            size: '3.2 MB',
            time: timestamp,
            path: 'algorithm/多源数据融合/visualization_results/'
        });
        
        addGeneratedFile({
            name: 'performance_analysis_report.docx',
            type: 'document',
            size: '186 KB',
            time: timestamp,
            path: 'algorithm/多源数据融合/visualization_results/'
        });
        
        showNotification('性能分析报告生成成功', 'success');
    }, 2500);
}

// 处理生成算法演示报告
async function handleGenerateAlgorithmReport() {
    const resultDisplay = document.getElementById('resultDisplay');
    
    // 显示处理中状态
    resultDisplay.innerHTML = `
        <div class="result-content">
            <div class="result-status processing">
                <span class="loading-spinner"></span>
                <span>正在生成算法演示报告...</span>
            </div>
        </div>
    `;
    
    // 模拟调用Python脚本生成报告
    setTimeout(() => {
        const imagePath = '../../../backend/algorithms/多源数据融合/visualization_results/fusion_algorithm_demo.png';
        const timestamp = new Date().toLocaleString();
        
        resultDisplay.innerHTML = `
            <div class="result-content">
                <div class="result-status success">
                    <span>✓</span>
                    <span>算法演示报告生成成功 - ${timestamp}</span>
                </div>
                <div class="result-image-container">
                    <img src="${imagePath}" alt="算法演示图表" class="result-image"
                         onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22400%22 height=%22300%22><rect width=%22400%22 height=%22300%22 fill=%22%23f0f0f0%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22>图表预览</text></svg>'">
                </div>
                <div class="result-actions">
                    <button class="btn btn-sm btn-primary" onclick="openResultFile('fusion_algorithm_demo.png')">打开图表</button>
                    <button class="btn btn-sm btn-success" onclick="openResultFile('algorithm_demo_report.docx')">Word报告</button>
                    <button class="btn btn-sm btn-info" onclick="openResultFile('fusion_analysis_report.txt')">文本报告</button>
                    <button class="btn btn-sm btn-secondary" onclick="openResultFolder()">打开文件夹</button>
                </div>
            </div>
        `;
        
        // 添加到文件列表
        addGeneratedFile({
            name: 'fusion_algorithm_demo.png',
            type: 'image',
            size: '2.5 MB',
            time: timestamp,
            path: 'algorithm/多源数据融合/visualization_results/'
        });
        
        addGeneratedFile({
            name: 'algorithm_demo_report.docx',
            type: 'document',
            size: '245 KB',
            time: timestamp,
            path: 'algorithm/多源数据融合/visualization_results/'
        });
        
        addGeneratedFile({
            name: 'fusion_analysis_report.txt',
            type: 'text',
            size: '12 KB',
            time: timestamp,
            path: 'algorithm/多源数据融合/visualization_results/'
        });
        
        addGeneratedFile({
            name: 'fusion_data.csv',
            type: 'data',
            size: '28 KB',
            time: timestamp,
            path: 'algorithm/多源数据融合/visualization_results/'
        });
        
        showNotification('算法演示报告生成成功', 'success');
    }, 2500);
}

// 添加生成的文件到列表
function addGeneratedFile(fileInfo) {
    // 检查是否已存在
    const existingIndex = generatedFiles.findIndex(f => f.name === fileInfo.name);
    if (existingIndex >= 0) {
        generatedFiles[existingIndex] = fileInfo;
    } else {
        generatedFiles.push(fileInfo);
    }
    
    updateFileList();
}

// 更新文件列表显示
function updateFileList() {
    const fileList = document.getElementById('fileList');
    
    if (generatedFiles.length === 0) {
        fileList.innerHTML = '<p class="no-files">暂无生成文件</p>';
        return;
    }
    
    const fileIcons = {
        'image': '🖼️',
        'document': '📄',
        'text': '📝',
        'data': '📊'
    };
    
    const fileItems = generatedFiles.map(file => {
        const icon = fileIcons[file.type] || '📄';
        return `
            <div class="file-item">
                <div class="file-info">
                    <span class="file-icon">${icon}</span>
                    <div class="file-details">
                        <div class="file-name">${file.name}</div>
                        <div class="file-meta">${file.size} · ${file.time}</div>
                    </div>
                </div>
                <div class="file-actions">
                    <button class="file-action-btn" onclick="openResultFile('${file.name}')">打开</button>
                    <button class="file-action-btn" onclick="showFileLocation('${file.path}')">位置</button>
                </div>
            </div>
        `;
    }).join('');
    
    fileList.innerHTML = fileItems;
}

// 打开结果文件
function openResultFile(filename) {
    const basePath = '../../../backend/algorithms/多源数据融合/visualization_results/';
    const fullPath = basePath + filename;
    
    showNotification(`正在打开文件: ${filename}`, 'info');
    
    // 在实际应用中，这里会调用系统命令打开文件
    setTimeout(() => {
        showNotification(`文件已在默认程序中打开`, 'success');
    }, 500);
}

// 打开结果文件夹
function openResultFolder() {
    const folderPath = 'algorithm/多源数据融合/visualization_results/';
    showNotification(`正在打开文件夹: ${folderPath}`, 'info');
    
    // 在实际应用中，这里会调用系统命令打开文件夹
    setTimeout(() => {
        showNotification('文件夹已打开', 'success');
    }, 500);
}

// 显示文件位置
function showFileLocation(path) {
    showNotification(`文件位置: ${path}`, 'info');
}

// 清空结果显示
function clearResultDisplay() {
    const resultDisplay = document.getElementById('resultDisplay');
    resultDisplay.innerHTML = `
        <div class="placeholder-content">
            <div class="placeholder-icon">📄</div>
            <p>结果输出展示区</p>
            <p class="placeholder-hint">点击上方按钮生成图表或报告文档</p>
        </div>
    `;
}


// 生成可视化图表按钮 - 在结果输出区域展示图表
document.getElementById('generateVisualizationBtn')?.addEventListener('click', function() {
    const chartsGrid = document.getElementById('chartsGrid');
    if (chartsGrid) {
        chartsGrid.style.display = 'grid';
        showNotification('可视化图表已生成！', 'success');
        
        // 滚动到结果输出区域
        const resultSection = document.querySelector('.result-output-section');
        if (resultSection) {
            resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
});

// CSV导出功能
document.getElementById('exportCsvBtn')?.addEventListener('click', function() {
    const csvPath = '../../../backend/algorithms/多源数据融合/visualization_results/fusion_data.csv';
    
    // 创建一个隐藏的a标签来触发下载
    const link = document.createElement('a');
    link.href = csvPath;
    link.download = 'fusion_data.csv';
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // 显示提示信息
    alert('CSV数据导出成功！\n文件位置: fusion_data.csv');
});
