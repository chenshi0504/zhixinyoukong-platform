// 全局变量
let currentScenario = null;
let simulationRunning = false;
let simulationInterval = null;
let currentProgress = 0;
let selectedConfigFiles = {}; // 存储选中的配置文件

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
});

// 初始化事件监听器
function initializeEventListeners() {
    // 返回按钮
    const backBtn = document.getElementById('backBtn');
    if (backBtn) {
        backBtn.addEventListener('click', handleBack);
    }

    // 场景选择按钮
    const scenarioButtons = document.querySelectorAll('.scenario-button');
    scenarioButtons.forEach(button => {
        button.addEventListener('click', function() {
            selectScenario(this.dataset.scenario, this);
        });
    });

    // 开始仿真按钮
    const startSimBtn = document.getElementById('startSimBtn');
    if (startSimBtn) {
        startSimBtn.addEventListener('click', startSimulation);
    }

    // 重置按钮
    const resetBtn = document.getElementById('resetBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetConfiguration);
    }

    // 仿真控制按钮
    const pauseBtn = document.getElementById('pauseBtn');
    const resumeBtn = document.getElementById('resumeBtn');
    const stopBtn = document.getElementById('stopBtn');
    const exportBtn = document.getElementById('exportBtn');

    if (pauseBtn) pauseBtn.addEventListener('click', pauseSimulation);
    if (resumeBtn) resumeBtn.addEventListener('click', resumeSimulation);
    if (stopBtn) stopBtn.addEventListener('click', stopSimulation);
    if (exportBtn) exportBtn.addEventListener('click', exportResults);
    
    // 查看结果图按钮
    const showResultsBtn = document.getElementById('showResultsBtn');
    if (showResultsBtn) showResultsBtn.addEventListener('click', showResultImages);
    
    // 下载报告按钮
    const downloadReportBtn = document.getElementById('downloadReportBtn');
    if (downloadReportBtn) downloadReportBtn.addEventListener('click', downloadReport);
    
    // 配置文件选择按钮
    initConfigFileButtons();
    
    // 算法代码上传
    const algorithmFileInput = document.getElementById('algorithmFile');
    if (algorithmFileInput) {
        algorithmFileInput.addEventListener('change', handleAlgorithmFileUpload);
    }

    // 滑块值更新
    const sliders = document.querySelectorAll('.slider-input');
    sliders.forEach(slider => {
        slider.addEventListener('input', function() {
            const valueSpan = this.nextElementSibling;
            if (valueSpan && valueSpan.classList.contains('slider-value')) {
                valueSpan.textContent = this.value + '%';
            }
        });
    });
}

// 返回上一页
function handleBack() {
    if (confirm('确定要返回吗？未保存的配置将丢失。')) {
        window.history.back();
    }
}

// 选择场景
function selectScenario(scenario, button) {
    // 更新按钮状态
    document.querySelectorAll('.scenario-button').forEach(btn => {
        btn.classList.remove('selected');
    });
    button.classList.add('selected');

    currentScenario = scenario;

    // 显示配置区域
    const configSection = document.getElementById('scenarioConfig');
    const configTitle = document.getElementById('configTitle');
    
    // 隐藏所有配置内容
    document.querySelectorAll('.config-content').forEach(content => {
        content.style.display = 'none';
    });

    // 显示对应的配置内容
    let configId = '';
    let title = '';
    
    switch(scenario) {
        case 'two-level':
            configId = 'twoLevelConfig';
            title = '场景1：两两协同优化配置';
            break;
        case 'three-level':
            configId = 'threeLevelConfig';
            title = '场景2：三层级全协同配置';
            break;
        case 'custom-algorithm':
            configId = 'customAlgorithmConfig';
            title = '场景3：自研算法测试配置';
            break;
        case 'policy-fusion':
            configId = 'policyFusionConfig';
            title = '场景4：政策融合场景配置';
            break;
    }

    if (configId) {
        const configContent = document.getElementById(configId);
        if (configContent) {
            configContent.style.display = 'block';
        }
    }

    configTitle.textContent = title;
    configSection.style.display = 'block';

    // 隐藏仿真区域
    const sumoSection = document.getElementById('sumoSection');
    if (sumoSection) {
        sumoSection.style.display = 'none';
    }
}

// 开始仿真
function startSimulation() {
    if (!currentScenario) {
        alert('请先选择一个操作场景！');
        return;
    }

    // 显示SUMO仿真区域
    const sumoSection = document.getElementById('sumoSection');
    if (sumoSection) {
        sumoSection.style.display = 'block';
        sumoSection.scrollIntoView({ behavior: 'smooth' });
    }

    // 显示视频，隐藏占位符
    const video = document.getElementById('simulationVideo');
    const placeholder = document.getElementById('videoPlaceholder');
    
    if (video && placeholder) {
        placeholder.style.display = 'none';
        video.style.display = 'block';
        video.play();
    }

    // 重置进度
    currentProgress = 0;
    simulationRunning = true;

    // 更新状态
    updateSimulationStatus('运行中');
    
    // 开始模拟仿真过程
    simulateOptimization();
}

// 模拟优化过程
function simulateOptimization() {
    let iteration = 0;
    const maxIterations = 50;

    simulationInterval = setInterval(() => {
        if (!simulationRunning) return;

        iteration++;
        currentProgress = Math.min((iteration / maxIterations) * 100, 100);

        // 更新进度
        updateProgress(currentProgress, iteration, maxIterations);

        // 模拟优化效果
        if (iteration % 10 === 0) {
            updateOptimizationResults(iteration, maxIterations);
        }

        // 完成仿真
        if (iteration >= maxIterations) {
            clearInterval(simulationInterval);
            completeSimulation();
        }
    }, 200);
}

// 更新仿真状态
function updateSimulationStatus(status) {
    const simStatus = document.getElementById('simStatus');
    if (simStatus) {
        simStatus.textContent = status;
    }
}

// 更新进度
function updateProgress(progress, iteration, maxIterations) {
    const progressElem = document.getElementById('progress');
    const iterationElem = document.getElementById('iteration');

    if (progressElem) {
        progressElem.textContent = Math.round(progress) + '%';
    }

    if (iterationElem) {
        iterationElem.textContent = `${iteration}/${maxIterations}`;
    }
}

// 更新优化结果
function updateOptimizationResults(iteration, maxIterations) {
    const progress = iteration / maxIterations;
    
    // 根据不同场景计算不同的优化效果
    let timeImprovement, delayImprovement, throughputImprovement;
    
    switch(currentScenario) {
        case 'two-level':
            // 两两协同：中等改善
            timeImprovement = 15 + progress * 10; // 15-25%
            delayImprovement = 20 + progress * 15; // 20-35%
            throughputImprovement = 10 + progress * 8; // 10-18%
            break;
        case 'three-level':
            // 三层级全协同：显著改善
            timeImprovement = 20 + progress * 15; // 20-35%
            delayImprovement = 25 + progress * 20; // 25-45%
            throughputImprovement = 15 + progress * 12; // 15-27%
            break;
        case 'custom-algorithm':
            // 自研算法：根据算法质量变化
            timeImprovement = 18 + progress * 17; // 18-35%
            delayImprovement = 22 + progress * 23; // 22-45%
            throughputImprovement = 12 + progress * 13; // 12-25%
            break;
        case 'policy-fusion':
            // 政策融合：最佳改善
            timeImprovement = 25 + progress * 20; // 25-45%
            delayImprovement = 30 + progress * 25; // 30-55%
            throughputImprovement = 18 + progress * 17; // 18-35%
            break;
        default:
            timeImprovement = 15 + progress * 10;
            delayImprovement = 20 + progress * 15;
            throughputImprovement = 10 + progress * 8;
    }

    // 计算优化后的值
    const baseTime = 25.3;
    const baseDelay = 8.7;
    const baseThroughput = 1850;

    const optimizedTime = (baseTime * (1 - timeImprovement / 100)).toFixed(1);
    const optimizedDelay = (baseDelay * (1 - delayImprovement / 100)).toFixed(1);
    const optimizedThroughput = Math.round(baseThroughput * (1 + throughputImprovement / 100));

    // 更新显示
    const optimizedTimeElem = document.getElementById('optimizedTime');
    const optimizedDelayElem = document.getElementById('optimizedDelay');
    const optimizedThroughputElem = document.getElementById('optimizedThroughput');
    const benefitElem = document.getElementById('benefit');

    if (optimizedTimeElem) {
        optimizedTimeElem.textContent = `${optimizedTime}分钟 (↓${timeImprovement.toFixed(1)}%)`;
    }
    if (optimizedDelayElem) {
        optimizedDelayElem.textContent = `${optimizedDelay}分钟 (↓${delayImprovement.toFixed(1)}%)`;
    }
    if (optimizedThroughputElem) {
        optimizedThroughputElem.textContent = `${optimizedThroughput}车次/小时 (↑${throughputImprovement.toFixed(1)}%)`;
    }
    if (benefitElem) {
        const avgBenefit = ((timeImprovement + delayImprovement + throughputImprovement) / 3).toFixed(1);
        benefitElem.textContent = `+${avgBenefit}%`;
    }
}

// 完成仿真
function completeSimulation() {
    simulationRunning = false;
    updateSimulationStatus('已完成');
    
    // 显示完成提示
    let message = '仿真优化完成！\n\n';
    
    switch(currentScenario) {
        case 'two-level':
            message += '两两协同优化显示出良好的协同效益，验证了协同机制对系统效益的提升作用。';
            break;
        case 'three-level':
            message += '三层级全协同优化实现了显著的系统性能提升，展现了多层级协同的优势。';
            break;
        case 'custom-algorithm':
            message += '自研算法测试完成，建议对比基准算法性能，进行进一步优化迭代。';
            break;
        case 'policy-fusion':
            message += '政策融合场景展示了技术优化与政策调控的复合效果，实现了最优的系统性能。';
            break;
    }
    
    setTimeout(() => {
        alert(message);
    }, 500);
}

// 获取图片说明
function getImageDescription(scenario, imageIndex) {
    const descriptions = {
        'two-level': [
            '对比单一优化与三种两两协同模式（信号+路径、路径+车速、信号+车速）的优化效果，验证协同叠加效益。理解目标互补与时序同步的核心机制。',
            '从出行时间改善、延误降低、通行量提升、能耗降低、排放减少五个维度评估三种协同模式的综合效益，展示协同优化的多维度优势。'
        ],
        'three-level': [
            '分析路网类型（单点/网状交叉口）、目标函数、OD数据对三层级协同优化效果的影响，掌握多层级协同与多变量分析方法。',
            '展示三层级协同优化过程中上层信号、中层路径、下层车速算法的收敛情况，以及整体协同优化相比单层优化的性能提升曲线。'
        ],
        'custom-algorithm': [
            '展示自研算法的完整流程：分析原有算法瓶颈 → 设计改进方案 → 测试对比性能 → 迭代优化。对比自研算法与基准算法（MPC-TuRBO、KSP+MSA、遗传算法）的性能指标，达成教学闭环。',
            '测试自研算法在不同交通流量水平（低流量0.6、中流量0.8、高流量1.0、过饱和1.2）下的稳定性和适应性，验证算法的鲁棒性。'
        ],
        'policy-fusion': [
            '分析ATIS信息推送（推送频率、覆盖率）和道路拥挤收费（费率、拥堵系数）政策对三层级协同优化效果的增强作用。输出政策干预前后数据，理解"技术优化+政策调控"的复合逻辑和叠加效应。',
            '对比四个场景（两两协同、三层级全协同、自研算法、政策融合）的综合优化效果，展示从基础协同到政策融合的递进式改善。'
        ]
    };
    
    return descriptions[scenario]?.[imageIndex] || '优化效果可视化图表';
}

// 下载图片
function downloadImage(imageSrc, fileName) {
    const link = document.createElement('a');
    link.href = imageSrc;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// 处理算法文件上传
function handleAlgorithmFileUpload(event) {
    const file = event.target.files[0];
    const fileInfoDiv = document.getElementById('algorithmFileInfo');
    
    if (!file) {
        return;
    }
    
    // 验证文件类型
    const validExtensions = ['.py', '.m', '.cpp'];
    const fileName = file.name;
    const fileExtension = fileName.substring(fileName.lastIndexOf('.')).toLowerCase();
    
    if (!validExtensions.includes(fileExtension)) {
        fileInfoDiv.className = 'file-info error';
        fileInfoDiv.innerHTML = `
            <div style="color: #dc3545; font-weight: 600;">
                ❌ 文件格式不支持
            </div>
            <div style="color: #666; font-size: 11px; margin-top: 4px;">
                请上传.py, .m或.cpp格式的算法文件
            </div>
        `;
        return;
    }
    
    // 验证文件大小（限制10MB）
    const maxSize = 10 * 1024 * 1024; // 10MB
    if (file.size > maxSize) {
        fileInfoDiv.className = 'file-info error';
        fileInfoDiv.innerHTML = `
            <div style="color: #dc3545; font-weight: 600;">
                ❌ 文件过大
            </div>
            <div style="color: #666; font-size: 11px; margin-top: 4px;">
                文件大小：${(file.size / 1024 / 1024).toFixed(2)} MB（限制10MB）
            </div>
        `;
        return;
    }
    
    // 显示加载中
    fileInfoDiv.className = 'file-info';
    fileInfoDiv.innerHTML = `
        <div style="color: #2C5AA0; font-weight: 600;">
            ⏳ 正在加载算法文件...
        </div>
    `;
    
    // 读取文件内容
    const reader = new FileReader();
    reader.onload = function(e) {
        const content = e.target.result;
        const lines = content.split('\n').length;
        
        // 显示上传成功信息
        fileInfoDiv.className = 'file-info success';
        fileInfoDiv.innerHTML = `
            <div style="color: #28a745; font-weight: 600; font-size: 14px;">
                ✅ 算法文件上传成功！
            </div>
            <div style="color: #333; margin-top: 6px; font-size: 12px;">
                📄 文件名：${fileName}
            </div>
            <div style="color: #666; font-size: 11px; margin-top: 4px;">
                📊 大小：${(file.size / 1024).toFixed(2)} KB | 代码行数：${lines} 行
            </div>
            <div style="color: #28a745; font-size: 11px; margin-top: 4px;">
                ✓ 文件已就绪，可以开始测试
            </div>
        `;
        
        // 存储文件信息
        if (!window.uploadedFiles) {
            window.uploadedFiles = {};
        }
        window.uploadedFiles.algorithmFile = {
            name: fileName,
            size: file.size,
            type: fileExtension,
            content: content,
            lines: lines,
            file: file
        };
        
        console.log('自研算法文件上传成功:', fileName, '行数:', lines);
        
        // 显示成功提示
        setTimeout(() => {
            alert(`算法文件上传成功！\n\n文件名：${fileName}\n大小：${(file.size / 1024).toFixed(2)} KB\n代码行数：${lines} 行\n\n可以开始配置参数并运行测试。`);
        }, 300);
    };
    
    reader.onerror = function() {
        fileInfoDiv.className = 'file-info error';
        fileInfoDiv.innerHTML = `
            <div style="color: #dc3545; font-weight: 600;">
                ❌ 文件读取失败
            </div>
            <div style="color: #666; font-size: 11px; margin-top: 4px;">
                请重新选择文件
            </div>
        `;
    };
    
    reader.readAsText(file);
}

// 暂停仿真
function pauseSimulation() {
    simulationRunning = false;
    updateSimulationStatus('已暂停');
    
    const pauseBtn = document.getElementById('pauseBtn');
    const resumeBtn = document.getElementById('resumeBtn');
    
    if (pauseBtn) pauseBtn.style.display = 'none';
    if (resumeBtn) resumeBtn.style.display = 'inline-block';
}

// 继续仿真
function resumeSimulation() {
    simulationRunning = true;
    updateSimulationStatus('运行中');
    
    const pauseBtn = document.getElementById('pauseBtn');
    const resumeBtn = document.getElementById('resumeBtn');
    
    if (pauseBtn) pauseBtn.style.display = 'inline-block';
    if (resumeBtn) resumeBtn.style.display = 'none';
}

// 停止仿真
function stopSimulation() {
    if (confirm('确定要停止仿真吗？')) {
        simulationRunning = false;
        if (simulationInterval) {
            clearInterval(simulationInterval);
        }
        updateSimulationStatus('已停止');
        
        // 重置按钮状态
        const pauseBtn = document.getElementById('pauseBtn');
        const resumeBtn = document.getElementById('resumeBtn');
        
        if (pauseBtn) pauseBtn.style.display = 'inline-block';
        if (resumeBtn) resumeBtn.style.display = 'none';
    }
}

// 初始化配置文件按钮
function initConfigFileButtons() {
    const configButtons = document.querySelectorAll('.config-file-btn');
    configButtons.forEach(button => {
        button.addEventListener('click', function() {
            const fileName = this.dataset.file;
            const parentCard = this.closest('.config-card');
            const selectedConfigDiv = parentCard.querySelector('.selected-config');
            
            // 移除同组其他按钮的选中状态
            parentCard.querySelectorAll('.config-file-btn').forEach(btn => {
                btn.classList.remove('selected');
            });
            
            // 选中当前按钮
            this.classList.add('selected');
            
            // 更新显示
            if (selectedConfigDiv) {
                selectedConfigDiv.textContent = `已选择: ${fileName}`;
                selectedConfigDiv.classList.remove('empty');
            }
            
            // 存储选中的文件
            const configType = selectedConfigDiv.id;
            selectedConfigFiles[configType] = fileName;
            
            console.log(`已选择配置文件: ${fileName}`);
        });
    });
}

// 下载报告（DOCX格式）
function downloadReport() {
    if (!currentScenario) {
        alert('请先运行仿真！');
        return;
    }

    const currentTime = new Date().toLocaleString('zh-CN');
    const scenarioName = getScenarioName(currentScenario);
    
    // 获取优化数据
    const optimizedTime = document.getElementById('optimizedTime')?.textContent || '18.6分钟';
    const optimizedDelay = document.getElementById('optimizedDelay')?.textContent || '3.2分钟';
    const optimizedThroughput = document.getElementById('optimizedThroughput')?.textContent || '2450车次/小时';
    const benefit = document.getElementById('benefit')?.textContent || '32.5%';

    // 获取配置文件列表
    let configFilesList = '使用默认配置';
    if (Object.keys(selectedConfigFiles).length > 0) {
        configFilesList = Object.values(selectedConfigFiles).join('、');
    }

    // 生成完整的HTML格式报告（可在Word中打开并保存为docx）
    const reportContent = `
<!DOCTYPE html>
<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
<head>
    <meta charset='UTF-8'>
    <title>三层级协同优化控制实验报告</title>
    <style>
        @page { size: A4; margin: 2.54cm; }
        body { font-family: "宋体", "SimSun", serif; font-size: 12pt; line-height: 1.8; margin: 0; padding: 20px; }
        h1 { text-align: center; font-size: 22pt; font-weight: bold; color: #000080; margin: 20px 0; }
        h2 { font-size: 16pt; font-weight: bold; color: #000080; margin-top: 24px; margin-bottom: 12px; border-bottom: 2px solid #000080; padding-bottom: 6px; }
        h3 { font-size: 14pt; font-weight: bold; color: #0066CC; margin-top: 18px; margin-bottom: 10px; }
        p { text-indent: 2em; margin: 8px 0; text-align: justify; }
        table { width: 100%; border-collapse: collapse; margin: 16px 0; }
        th, td { border: 1px solid #000; padding: 8px; text-align: left; font-size: 11pt; }
        th { background-color: #4472C4; color: white; font-weight: bold; text-align: center; }
        tr:nth-child(even) { background-color: #F2F2F2; }
        .info-box { background-color: #E7F3FF; padding: 12px; border-left: 4px solid #4472C4; margin: 16px 0; }
        .info-box p { text-indent: 0; margin: 6px 0; }
        .highlight { background-color: #FFFF00; padding: 2px 4px; font-weight: bold; }
        ul, ol { margin: 10px 0; padding-left: 40px; }
        li { margin: 6px 0; line-height: 1.6; }
        .footer { margin-top: 40px; text-align: right; }
        .signature { display: inline-block; margin: 0 30px; text-align: left; }
        .signature p { text-indent: 0; margin: 8px 0; }
        .meta-info { text-align: center; color: #666; font-size: 11pt; margin: 10px 0; }
        .meta-info p { text-indent: 0; }
    </style>
</head>
<body>
    <h1>三层级协同优化控制实验报告</h1>
    <div class="meta-info">
        <p>实验时间：${currentTime}</p>
        <p>实验场景：${scenarioName}</p>
    </div>
    
    <h2>一、实验目的</h2>
    <p>本实验旨在通过三层级协同优化控制系统的应用与分析，使学生掌握智能交通系统中多层级协同优化的基本原理和实现方法。通过对比不同协同场景的性能特点，理解各层级之间的协同机制和优化策略，培养学生对复杂交通系统的整体把握能力。</p>
    
    <h2>二、实验原理</h2>
    <h3>2.1 三层级协同优化框架</h3>
    <p>三层级协同优化控制系统采用分层递阶的控制架构，包括上层交通信号优化、中层路径诱导和下层车速控制三个层级。各层级通过信息共享和决策协调，实现交通系统的全局优化。</p>
    
    <h2>三、实验环境与配置</h2>
    <div class="info-box">
        <table>
            <tr>
                <th style="width: 25%;">配置项</th>
                <th style="width: 75%;">配置内容</th>
            </tr>
            <tr>
                <td>实验场景</td>
                <td><span class="highlight">${scenarioName}</span></td>
            </tr>
            <tr>
                <td>配置文件</td>
                <td>${configFilesList}</td>
            </tr>
            <tr>
                <td>仿真平台</td>
                <td>SUMO交通仿真平台</td>
            </tr>
        </table>
    </div>
    
    <h2>四、实验过程</h2>
    <p>启动仿真系统后，三层级协同优化控制开始执行。上层根据全局交通状态优化信号配时，中层根据路网拥堵情况提供路径诱导，下层根据信号和路径信息控制车辆速度。</p>
    
    <h2>五、实验结果与分析</h2>
    <table>
        <tr>
            <th style="width: 30%;">评价指标</th>
            <th style="width: 25%;">优化前</th>
            <th style="width: 25%;">优化后</th>
            <th style="width: 20%;">改善幅度</th>
        </tr>
        <tr>
            <td>平均出行时间</td>
            <td>25.3分钟</td>
            <td><strong>${optimizedTime}</strong></td>
            <td><strong>显著降低</strong></td>
        </tr>
        <tr>
            <td>平均延误</td>
            <td>8.7分钟</td>
            <td><strong>${optimizedDelay}</strong></td>
            <td><strong>显著降低</strong></td>
        </tr>
        <tr>
            <td>通行量</td>
            <td>1850车次/小时</td>
            <td><strong>${optimizedThroughput}</strong></td>
            <td><strong>显著提升</strong></td>
        </tr>
        <tr style="background-color: #E7F3FF;">
            <td><strong>综合协同效益</strong></td>
            <td colspan="2" style="text-align: center;"><strong>${benefit}</strong></td>
            <td><strong>显著提升</strong></td>
        </tr>
    </table>
    
    <h2>六、实验结论</h2>
    <p>${getScenarioConclusion(currentScenario)}</p>
    
    <h2>七、实验心得与体会</h2>
    <p style="min-height: 120px; border: 1px solid #ccc; padding: 12px; margin: 16px 0; text-indent: 0;">
        （请在此处填写实验心得体会，不少于200字）
    </p>
    
    <h2>八、参考文献</h2>
    <ol>
        <li>杨晓光, 庄斌. (2010). 智能交通系统中的协同控制理论与方法. 北京: 人民交通出版社.</li>
        <li>王殿海, 金盛. (2008). 交通流理论. 北京: 人民交通出版社.</li>
        <li>Papageorgiou, M., et al. (2003). Review of road traffic control strategies. <em>Proceedings of the IEEE</em>, 91(12), 2043-2067.</li>
    </ol>
    
    <div class="footer">
        <table style="border: none; width: 100%;">
            <tr style="background: none;">
                <td style="border: none; width: 50%; text-align: left;">
                    <div class="signature">
                        <p><strong>实验人员：</strong>_______________</p>
                        <p><strong>学号：</strong>_______________</p>
                    </div>
                </td>
                <td style="border: none; width: 50%; text-align: right;">
                    <div class="signature">
                        <p><strong>指导教师：</strong>_______________</p>
                        <p><strong>日期：</strong>${currentTime.split(' ')[0]}</p>
                    </div>
                </td>
            </tr>
        </table>
    </div>
</body>
</html>
    `.trim();

    // 创建Blob并下载
    const blob = new Blob(['\ufeff', reportContent], { 
        type: 'application/msword;charset=utf-8' 
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const fileName = scenarioName.replace(/[：:]/g, '_').replace(/\s+/g, '_');
    a.download = `三层级协同优化控制实验报告_${fileName}_${new Date().getTime()}.doc`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    alert('实验报告已导出！\n\n文件格式：.doc (可用Microsoft Word打开后另存为.docx)\n\n报告内容完整，格式规范，可直接用于实验提交！');
}

// 重置配置
function resetConfiguration() {
    if (confirm('确定要重置配置吗？')) {
        // 停止仿真
        if (simulationInterval) {
            clearInterval(simulationInterval);
        }
        simulationRunning = false;
        currentProgress = 0;

        // 重置场景选择
        document.querySelectorAll('.scenario-button').forEach(btn => {
            btn.classList.remove('selected');
        });
        currentScenario = null;

        // 隐藏配置和仿真区域
        const configSection = document.getElementById('scenarioConfig');
        const sumoSection = document.getElementById('sumoSection');
        
        if (configSection) configSection.style.display = 'none';
        if (sumoSection) sumoSection.style.display = 'none';

        // 重置所有输入
        document.querySelectorAll('input[type="number"]').forEach(input => {
            input.value = input.defaultValue || '';
        });
        document.querySelectorAll('input[type="radio"]').forEach(radio => {
            radio.checked = radio.defaultChecked;
        });
        document.querySelectorAll('select').forEach(select => {
            select.selectedIndex = 0;
        });

        alert('配置已重置！');
    }
}

// 获取场景名称
function getScenarioName(scenario) {
    const names = {
        'two-level': '场景1：两两协同优化',
        'three-level': '场景2：三层级全协同',
        'custom-algorithm': '场景3：自研算法测试',
        'policy-fusion': '场景4：政策融合场景'
    };
    return names[scenario] || '未知场景';
}

// 获取场景结论
function getScenarioConclusion(scenario) {
    const conclusions = {
        'two-level': '两两协同优化验证了协同机制的有效性，相比单一优化有明显提升。建议进一步探索三层级全协同优化。',
        'three-level': '三层级全协同优化实现了系统性能的显著提升，展现了多层级协同的优势。信号-路径-车速的有机配合是关键。',
        'custom-algorithm': '自研算法在测试中表现良好，建议继续优化算法参数，缩短迭代时长，提升收敛精度。',
        'policy-fusion': '政策融合场景展示了技术优化与政策调控的复合效果，ATIS信息推送和拥挤收费政策对优化效果有显著增强作用。'
    };
    return conclusions[scenario] || '实验完成，请分析结果。';
}

// 显示结果图片
function showResultImages() {
    if (!currentScenario) {
        alert('请先运行仿真！');
        return;
    }
    
    // 根据场景显示对应的结果图片
    const resultImageMap = {
        'two-level': [
            {file: '场景2_协同效果对比.png', title: '两两协同优化 - 单一vs协同对比'},
            {file: '场景2_协同效益雷达图.png', title: '协同效益雷达图 - 多维度评估'}
        ],
        'three-level': [
            {file: '场景3_三层级全协同对比.png', title: '三层级全协同 - 多变量分析'},
            {file: '场景3_协同优化过程.png', title: '协同优化收敛过程'}
        ],
        'custom-algorithm': [
            {file: '场景4_自研算法对比.png', title: '自研算法全流程 - 设计测试迭代'},
            {file: '场景4_不同流量性能.png', title: '不同流量水平性能测试'}
        ],
        'policy-fusion': [
            {file: '场景5_政策融合效果.png', title: 'ATIS+拥挤收费政策叠加效果'},
            {file: '总体对比图.png', title: '四个场景综合对比'}
        ]
    };
    
    const images = resultImageMap[currentScenario];
    if (!images || images.length === 0) {
        alert('该场景暂无结果图片！');
        return;
    }
    
    // 显示结果图片区域
    const resultSection = document.getElementById('resultImagesSection');
    const resultGrid = document.getElementById('resultImagesGrid');
    
    if (resultSection && resultGrid) {
        // 清空之前的内容
        resultGrid.innerHTML = '';
        
        // 添加结果图片和说明
        images.forEach((img, index) => {
            const card = document.createElement('div');
            card.className = 'result-image-card';
            
            // 获取图片说明
            const description = getImageDescription(currentScenario, index);
            
            card.innerHTML = `
                <img src="result_images/${img.file}" alt="${img.title}" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'500\' height=\'300\'%3E%3Crect fill=\'%23f0f0f0\' width=\'500\' height=\'300\'/%3E%3Ctext x=\'50%25\' y=\'50%25\' dominant-baseline=\'middle\' text-anchor=\'middle\' font-family=\'Arial\' font-size=\'18\' fill=\'%23999\'%3E${img.title}%3C/text%3E%3C/svg%3E'">
                <div class="result-image-title">${img.title}</div>
                <div class="result-image-desc">${description}</div>
                <button class="download-image-btn" onclick="downloadImage('result_images/${img.file}', '${img.file}')">
                    📥 下载图片
                </button>
            `;
            resultGrid.appendChild(card);
        });
        
        // 显示区域并滚动到该位置
        resultSection.style.display = 'block';
        resultSection.scrollIntoView({ behavior: 'smooth' });
    }
}
