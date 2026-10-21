// 交通流预测功能教学模块 JavaScript

/**
 * 标记步骤按钮完成：按钮从蓝底变为白底蓝边
 */
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

    // Cookie 是浏览器级共享的：同一浏览器先开预测页、再开融合页时，后写入的
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
        if (url.indexOf('/api/prediction/') === -1) {
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
    ['loadDataBtn', 'trainModelBtn', 'runPredictionBtn', 'generateVisualizationBtn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.classList.remove('step-done');
        }
    });
}

/**
 * 重置状态处理函数
 */
function handleResetStatus() {
    // 重置所有步骤按钮样式
    resetAllStepButtons();
    
    // 重置数据概览
    document.getElementById('avgFlow').textContent = '--';
    document.getElementById('maxFlow').textContent = '--';
    document.getElementById('minFlow').textContent = '--';
    document.getElementById('stdFlow').textContent = '--';
    document.getElementById('trainSize').textContent = '--';
    document.getElementById('testSize').textContent = '--';
    document.getElementById('lrR2').textContent = '--';
    document.getElementById('rfR2').textContent = '--';
    document.getElementById('svrR2').textContent = '--';
    document.getElementById('dtrR2').textContent = '--';
    document.getElementById('bestModel').textContent = '--';
    
    // 重置结果展示区域
    const resultDisplay = document.getElementById('resultDisplay');
    if (resultDisplay) {
        resultDisplay.innerHTML = `
            <div class="placeholder-content">
                <div class="placeholder-icon">📈</div>
                <p>结果展示区</p>
                <p class="placeholder-hint">点击上方按钮下载实验报告或数据</p>
            </div>
        `;
    }
    
    // 调用后端重置API，清除卡住的运行状态
    fetch('/api/prediction/reset', { method: 'POST' }).catch(function() {});
    
    // 重置状态显示
    const statusEl = document.getElementById('currentStatus');
    if (statusEl) {
        statusEl.textContent = '已重置';
        statusEl.style.cssText = '';
    }
    
    showSuccessToast('已重置为初始状态');
}

class TrafficFlowPrediction {
    constructor() {
        this.chart = null;
        this.isRunning = false;
        this.trafficData = [];
        this.models = {};
        this.predictions = {};
        this.currentAlgorithm = 'linear_regression';

        this.init();
    }

    init() {
        this.initChart();
        this.bindEvents();
        this.setDefaultValues();
        this.generateSampleData();
    }

    // 初始化ECharts图表
    initChart() {
        const chartDom = document.getElementById('predictionChart');
        if (!chartDom) {
            console.log('图表容器不存在，跳过初始化');
            return;
        }
        this.chart = echarts.init(chartDom);

        const option = {
            title: {
                text: '交通流预测结果',
                left: 'center',
                textStyle: {
                    fontSize: 16,
                    color: '#2c3e50'
                }
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                }
            },
            legend: {
                data: ['历史数据', '预测数据'],
                bottom: 10
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '15%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: [],
                name: '时间',
                nameLocation: 'middle',
                nameGap: 25
            },
            yAxis: {
                type: 'value',
                name: '交通流量 (vehicles/h)',
                nameLocation: 'middle',
                nameGap: 50
            },
            series: [
                {
                    name: '历史数据',
                    type: 'line',
                    data: [],
                    itemStyle: {
                        color: '#3498db'
                    },
                    lineStyle: {
                        width: 2
                    }
                },
                {
                    name: '预测数据',
                    type: 'line',
                    data: [],
                    itemStyle: {
                        color: '#e74c3c'
                    },
                    lineStyle: {
                        width: 2,
                        type: 'dashed'
                    }
                }
            ]
        };

        this.chart.setOption(option);

        // 响应式调整
        window.addEventListener('resize', () => {
            this.chart.resize();
        });
    }

    // 绑定事件监听器
    bindEvents() {
        // 注意：loadDataBtn, trainModelBtn, runPredictionBtn, generateVisualizationBtn, resetBtn
        // 已在HTML中通过onclick绑定全局函数（handleLoadData等），这里不再重复绑定，避免双重触发

        // 结果输出按钮
        const generatePredictionResultBtn = document.getElementById('generatePredictionResultBtn');
        if (generatePredictionResultBtn) {
            generatePredictionResultBtn.addEventListener('click', () => this.generateChart('pattern'));
        }
        
        const generateTrafficPatternBtn = document.getElementById('generateTrafficPatternBtn');
        if (generateTrafficPatternBtn) {
            generateTrafficPatternBtn.addEventListener('click', () => this.generateChart('comparison'));
        }
    }

    // 设置默认值
    setDefaultValues() {
        // 简化的默认值设置
        this.updateStatus();
    }
    
    // 下载数据
    async downloadData() {
        try {
            const response = await fetch('/api/prediction/download-data');
            if (response.ok) {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = 'Traffic_flow_data.csv';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                URL.revokeObjectURL(url);
                this.showNotification('数据下载成功！', 'success');
            } else {
                this.showNotification('下载失败', 'error');
            }
        } catch (error) {
            this.showNotification('下载失败', 'error');
        }
    }

    // 生成样本数据
    generateSampleData() {
        const sampleSize = 1000;
        this.trafficData = [];

        const baseDate = new Date('2024-01-01');

        for (let i = 0; i < sampleSize; i++) {
            const currentDate = new Date(baseDate.getTime() + i * 60 * 60 * 1000); // 每小时一个数据点
            const hour = currentDate.getHours();
            const dayOfWeek = currentDate.getDay();

            // 模拟交通流量模式
            let baseFlow = 500;

            // 小时模式 (早晚高峰)
            if (hour >= 7 && hour <= 9) baseFlow += 400; // 早高峰
            else if (hour >= 17 && hour <= 19) baseFlow += 500; // 晚高峰
            else if (hour >= 10 && hour <= 16) baseFlow += 200; // 白天
            else if (hour >= 20 && hour <= 22) baseFlow += 100; // 晚上

            // 工作日vs周末
            if (dayOfWeek === 0 || dayOfWeek === 6) baseFlow *= 0.7; // 周末流量减少

            // 添加随机噪声
            const noise = (Math.random() - 0.5) * 200;
            const flow = Math.max(0, baseFlow + noise);

            this.trafficData.push({
                datetime: currentDate,
                hour: hour,
                day: currentDate.getDate(),
                dayofweek: dayOfWeek,
                flow: Math.round(flow)
            });
        }

        this.updateDataOverview();
    }

    // 处理数据源变化
    handleDataSourceChange() {
        const isEnabled = document.getElementById('trafficDataSource').checked;
        const statusElement = document.getElementById('dataStatus');

        if (isEnabled) {
            statusElement.textContent = '就绪';
            statusElement.className = 'source-status status-ready';
        } else {
            statusElement.textContent = '禁用';
            statusElement.className = 'source-status status-disabled';
        }
    }

    // 处理算法选择变化
    handleAlgorithmChange() {
        const selectedAlgorithm = document.querySelector('input[name="algorithm"]:checked').value;
        this.currentAlgorithm = selectedAlgorithm;

        const algorithmNames = {
            'linear_regression': '线性回归',
            'random_forest': '随机森林',
            'lstm': 'LSTM神经网络'
        };

        document.getElementById('currentAlgorithm').textContent = algorithmNames[selectedAlgorithm];
        this.updateStatus();
    }

    // 处理窗口大小变化
    handleWindowSizeChange() {
        const value = document.getElementById('windowSize').value;
        document.getElementById('windowValue').textContent = value;
    }

    // 处理训练比例变化
    handleTrainRatioChange() {
        const value = document.getElementById('trainRatio').value;
        document.getElementById('trainValue').textContent = Math.round(value * 100) + '%';
    }

    // 更新参数值显示
    updateParameterValues() {
        this.handleWindowSizeChange();
        this.handleTrainRatioChange();
    }

    // 更新状态显示
    updateStatus(status = 'ready', text = '就绪') {
        const statusElement = document.getElementById('currentStatus');
        if (statusElement) {
            statusElement.textContent = text;
        }
    }

    // 加载数据
    loadData() {
        if (this.isRunning) return;

        const self = this;
        self.isRunning = true;
        self.updateStatus('loading', '正在加载数据...');

        // 生成样本数据
        if (self.trafficData.length === 0) {
            self.generateSampleData();
        }
        self.updateDataOverview();
        
        // 2秒后显示加载成功
        window.setTimeout(function() {
            self.updateStatus('data_loaded', '数据加载成功');
            self.isRunning = false;
        }, 2000);
    }
    
    // 从后端加载分析结果
    async loadResultsFromServer() {
        console.log('正在从后端加载分析结果...');
        try {
            const response = await fetch('/api/prediction/get-results', {
                method: 'GET'
            });
            
            console.log('后端响应状态:', response.status);
            
            if (response.ok) {
                const result = await response.json();
                console.log('后端返回数据:', result);
                
                if (result.success && result.data) {
                    const data = result.data;
                    console.log('解析的数据:', data);
                    
                    // 更新数据概览
                    const avgFlowEl = document.getElementById('avgFlow');
                    const maxFlowEl = document.getElementById('maxFlow');
                    const minFlowEl = document.getElementById('minFlow');
                    const stdFlowEl = document.getElementById('stdFlow');
                    const trainSizeEl = document.getElementById('trainSize');
                    const testSizeEl = document.getElementById('testSize');
                    const lrR2El = document.getElementById('lrR2');
                    const rfR2El = document.getElementById('rfR2');
                    const svrR2El = document.getElementById('svrR2');
                    const dtrR2El = document.getElementById('dtrR2');
                    const bestModelEl = document.getElementById('bestModel');
                    const modelNames = {lr: '线性回归', rf: '随机森林', svr: 'SVR', dtr: '决策树'};
                    
                    if (avgFlowEl) avgFlowEl.textContent = data.avg_flow || '--';
                    if (maxFlowEl) maxFlowEl.textContent = data.max_flow || '--';
                    if (minFlowEl) minFlowEl.textContent = data.min_flow || '--';
                    if (stdFlowEl) stdFlowEl.textContent = data.std_flow || '--';
                    if (trainSizeEl) trainSizeEl.textContent = data.train_size || '--';
                    if (testSizeEl) testSizeEl.textContent = data.test_size || '--';
                    if (lrR2El) lrR2El.textContent = data.lr_r2 || '--';
                    if (rfR2El) rfR2El.textContent = data.rf_r2 || '--';
                    if (svrR2El) svrR2El.textContent = data.svr_r2 || '--';
                    if (dtrR2El) dtrR2El.textContent = data.dtr_r2 || '--';
                    if (bestModelEl) bestModelEl.textContent = modelNames[data.best_model] || data.best_model || '--';
                    
                    console.log('数据概览更新完成');
                    return true;
                } else {
                    console.log('后端返回失败:', result.message);
                }
            } else {
                console.log('后端响应失败:', response.status);
            }
        } catch (error) {
            console.error('后端未启动或加载结果失败:', error);
        }
        return false;
    }

    // 训练模型 - 在服务器后台任务中运行
    async trainModel() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.updateStatus('training', '正在启动模型训练...');

        try {
            const response = await fetch('/api/prediction/train-model', {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                if (result.async) {
                    this.updateStatus('training', '模型训练中（服务器后台运行中）...');
                    this.pollPredictionStatus('train');
                } else {
                    this.updateStatus('trained', '模型训练完成');
                    markStepDone('trainModelBtn');
                    this.isRunning = false;
                }
            } else {
                this.updateStatus('error', '训练失败: ' + result.message);
                this.isRunning = false;
            }
        } catch (error) {
            console.error('训练请求失败:', error);
            this.updateStatus('error', '后端服务未响应');
            this.isRunning = false;
        }
    }

    // 轮询预测任务状态
    pollPredictionStatus(taskType) {
        const self = this;
        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch('/api/prediction/status');
                const status = await response.json();
                
                if (status.running) {
                    // 还在运行
                    const label = taskType === 'train' ? '模型训练中' : '预测分析中';
                    self.updateStatus('processing', label + '（服务器后台运行中）...');
                } else {
                    // 运行结束
                    clearInterval(pollInterval);
                    if (status.success) {
                        if (taskType === 'train') {
                            self.updateStatus('trained', '模型训练完成');
                            markStepDone('trainModelBtn');
                        } else {
                            self.updateStatus('completed', '预测分析完成');
                            markStepDone('runPredictionBtn');
                            await self.loadResults();
                        }
                    } else {
                        self.updateStatus('error', '失败: ' + status.message);
                    }
                    self.isRunning = false;
                }
            } catch (e) {
                console.warn('轮询状态失败:', e);
            }
        }, 2000);
    }

    // 获取选中的算法
    getSelectedAlgorithms() {
        const selected = [];
        if (document.getElementById('algoLinearRegression')?.checked) {
            selected.push('linear_regression');
        }
        if (document.getElementById('algoRandomForest')?.checked) {
            selected.push('random_forest');
        }
        if (document.getElementById('algoLSTM')?.checked) {
            selected.push('lstm');
        }
        return selected;
    }

    // 运行预测 - 在服务器后台任务中运行
    async runPrediction() {
        if (this.isRunning) return;

        this.isRunning = true;
        this.updateStatus('predicting', '正在启动预测分析...');

        try {
            const response = await fetch('/api/prediction/run-prediction', {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                if (result.async) {
                    this.updateStatus('predicting', '预测分析中（服务器后台运行中）...');
                    this.pollPredictionStatus('predict');
                } else {
                    this.updateStatus('completed', '预测完成');
                    markStepDone('runPredictionBtn');
                    await this.loadResults();
                    this.isRunning = false;
                }
            } else {
                this.updateStatus('error', '预测失败: ' + result.message);
                this.isRunning = false;
            }
        } catch (error) {
            console.error('预测请求失败:', error);
            this.updateStatus('error', '后端服务未响应');
            this.isRunning = false;
        }
    }
    
    // 加载分析结果
    async loadResults() {
        try {
            const response = await fetch('/api/prediction/get-results', {
                method: 'GET'
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success && result.data) {
                    const data = result.data;
                    // 更新数据概览
                    document.getElementById('avgFlow').textContent = data.avg_flow || '--';
                    document.getElementById('maxFlow').textContent = data.max_flow || '--';
                    document.getElementById('minFlow').textContent = data.min_flow || '--';
                    document.getElementById('stdFlow').textContent = data.std_flow || '--';
                    document.getElementById('trainSize').textContent = data.train_size || '--';
                    document.getElementById('testSize').textContent = data.test_size || '--';
                    document.getElementById('lrR2').textContent = data.lr_r2 || '--';
                    document.getElementById('rfR2').textContent = data.rf_r2 || '--';
                    if (document.getElementById('svrR2')) document.getElementById('svrR2').textContent = data.svr_r2 || '--';
                    if (document.getElementById('dtrR2')) document.getElementById('dtrR2').textContent = data.dtr_r2 || '--';
                    var mn = {lr: '线性回归', rf: '随机森林', svr: 'SVR', dtr: '决策树'};
                    if (document.getElementById('bestModel')) document.getElementById('bestModel').textContent = mn[data.best_model] || data.best_model || '--';
                }
            }
        } catch (error) {
            console.error('加载结果失败:', error);
        }
    }

    // 创建特征
    createFeatures() {
        const windowSize = parseInt(document.getElementById('windowSize').value);
        const features = [];

        for (let i = windowSize; i < this.trafficData.length; i++) {
            const feature = {
                target: this.trafficData[i].flow
            };

            // 滞后特征
            if (document.getElementById('lagFeatures').checked) {
                for (let j = 1; j <= windowSize; j++) {
                    feature[`lag_${j}`] = this.trafficData[i - j].flow;
                }
            }

            // 时间特征
            if (document.getElementById('hourFeature').checked) {
                feature.hour = this.trafficData[i].hour;
            }
            if (document.getElementById('dayFeature').checked) {
                feature.day = this.trafficData[i].day;
            }
            if (document.getElementById('weekdayFeature').checked) {
                feature.dayofweek = this.trafficData[i].dayofweek;
            }

            // 滑动平均特征
            if (document.getElementById('rollingMean').checked) {
                const window3 = this.trafficData.slice(i - 3, i).reduce((sum, d) => sum + d.flow, 0) / 3;
                const window5 = this.trafficData.slice(i - 5, i).reduce((sum, d) => sum + d.flow, 0) / 5;
                feature.rolling_mean_3 = window3;
                feature.rolling_mean_5 = window5;
            }

            features.push(feature);
        }

        return features;
    }

    // 训练线性回归模型
    trainLinearRegression(features) {
        const trainRatio = parseFloat(document.getElementById('trainRatio').value);
        const splitIndex = Math.floor(features.length * trainRatio);

        const trainData = features.slice(0, splitIndex);
        const testData = features.slice(splitIndex);

        // 模拟线性回归训练结果
        const model = {
            type: 'linear_regression',
            trainSize: trainData.length,
            testSize: testData.length,
            performance: {
                mse: 450 + Math.random() * 100,
                rmse: 21 + Math.random() * 5,
                mae: 15 + Math.random() * 5,
                r2: 0.75 + Math.random() * 0.15
            }
        };

        return model;
    }

    // 训练随机森林模型
    trainRandomForest(features) {
        const trainRatio = parseFloat(document.getElementById('trainRatio').value);
        const splitIndex = Math.floor(features.length * trainRatio);

        const trainData = features.slice(0, splitIndex);
        const testData = features.slice(splitIndex);

        // 模拟随机森林训练结果
        const model = {
            type: 'random_forest',
            trainSize: trainData.length,
            testSize: testData.length,
            performance: {
                mse: 320 + Math.random() * 80,
                rmse: 18 + Math.random() * 4,
                mae: 12 + Math.random() * 4,
                r2: 0.82 + Math.random() * 0.12
            }
        };

        return model;
    }

    // 训练LSTM模型
    trainLSTM(features) {
        const trainRatio = parseFloat(document.getElementById('trainRatio').value);
        const splitIndex = Math.floor(features.length * trainRatio);

        const trainData = features.slice(0, splitIndex);
        const testData = features.slice(splitIndex);

        // 模拟LSTM训练结果
        const model = {
            type: 'lstm',
            trainSize: trainData.length,
            testSize: testData.length,
            performance: {
                mse: 280 + Math.random() * 70,
                rmse: 16 + Math.random() * 3,
                mae: 11 + Math.random() * 3,
                r2: 0.85 + Math.random() * 0.10
            }
        };

        return model;
    }

    // 执行预测
    performPrediction() {
        const recentData = this.trafficData.slice(-50); // 最近50个数据点
        const predictions = {
            linear_regression: [],
            random_forest: [],
            lstm: [],
            timeLabels: []
        };

        // 生成预测数据
        for (let i = 0; i < 20; i++) { // 预测未来20个时间点
            const baseTime = new Date(recentData[recentData.length - 1].datetime.getTime() + (i + 1) * 60 * 60 * 1000);

            // 只为已训练的模型生成预测
            if (this.models.linear_regression) {
                const lrPred = this.simulateLinearRegressionPrediction(recentData, i);
                predictions.linear_regression.push(lrPred);
            }

            if (this.models.random_forest) {
                const rfPred = this.simulateRandomForestPrediction(recentData, i);
                predictions.random_forest.push(rfPred);
            }

            if (this.models.lstm) {
                const lstmPred = this.simulateLSTMPrediction(recentData, i);
                predictions.lstm.push(lstmPred);
            }

            predictions.timeLabels.push(baseTime.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));
        }

        return predictions;
    }

    // 模拟线性回归预测
    simulateLinearRegressionPrediction(recentData, step) {
        const lastFlow = recentData[recentData.length - 1].flow;
        const trend = Math.sin((step + 1) * Math.PI / 12) * 30;
        const noise = (Math.random() - 0.5) * 50;
        return Math.max(0, Math.round(lastFlow + trend + noise));
    }

    // 模拟随机森林预测
    simulateRandomForestPrediction(recentData, step) {
        const lastFlow = recentData[recentData.length - 1].flow;
        const trend = Math.sin((step + 1) * Math.PI / 12) * 40;
        const noise = (Math.random() - 0.5) * 30;
        return Math.max(0, Math.round(lastFlow + trend + noise));
    }

    // 模拟LSTM预测
    simulateLSTMPrediction(recentData, step) {
        const lastFlow = recentData[recentData.length - 1].flow;
        const trend = Math.sin((step + 1) * Math.PI / 12) * 45;
        const noise = (Math.random() - 0.5) * 25;
        return Math.max(0, Math.round(lastFlow + trend + noise));
    }

    // 更新数据概览
    updateDataOverview() {
        if (this.trafficData.length === 0) return;

        const totalRecords = this.trafficData.length;
        const avgFlow = Math.round(this.trafficData.reduce((sum, d) => sum + d.flow, 0) / totalRecords);
        const maxFlow = Math.max(...this.trafficData.map(d => d.flow));

        document.getElementById('totalRecords').textContent = totalRecords;
        document.getElementById('avgFlow').textContent = avgFlow;
        document.getElementById('maxFlow').textContent = maxFlow;
    }

    // 更新图表
    updateChart(predictions) {
        const recentData = this.trafficData.slice(-30);
        const historicalFlow = recentData.map(d => d.flow);
        const historicalLabels = recentData.map(d => d.datetime.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }));

        const option = {
            title: {
                text: '交通流预测结果对比分析',
                left: 'center',
                textStyle: {
                    fontSize: 18,
                    color: '#1a5490',
                    fontWeight: 'bold'
                },
                subtextStyle: {
                    fontSize: 12,
                    color: '#666'
                }
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross',
                    crossStyle: {
                        color: '#1a5490'
                    }
                },
                backgroundColor: 'rgba(255, 255, 255, 0.95)',
                borderColor: '#1a5490',
                borderWidth: 1,
                textStyle: {
                    color: '#333'
                },
                formatter: function(params) {
                    let result = `<div style="padding: 5px;"><strong>${params[0].axisValue}</strong><br/>`;
                    params.forEach(param => {
                        if (param.value !== null) {
                            result += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${param.color};margin-right:5px;"></span>`;
                            result += `${param.seriesName}: <strong>${param.value.toFixed(0)}</strong> 辆/h<br/>`;
                        }
                    });
                    result += '</div>';
                    return result;
                }
            },
            legend: {
                data: this.getLegendData(predictions),
                bottom: 15,
                textStyle: {
                    fontSize: 12,
                    color: '#333'
                },
                itemGap: 20
            },
            grid: {
                left: '8%',
                right: '4%',
                bottom: '18%',
                top: '12%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: historicalLabels.concat(predictions.timeLabels),
                name: '时间序列',
                nameLocation: 'middle',
                nameGap: 28,
                nameTextStyle: {
                    fontSize: 12,
                    color: '#1a5490',
                    fontWeight: '600'
                },
                axisLine: {
                    lineStyle: {
                        color: '#1a5490',
                        width: 1.5
                    }
                },
                axisLabel: {
                    color: '#666',
                    fontSize: 10,
                    rotate: 40
                }
            },
            yAxis: {
                type: 'value',
                name: '交通流量\n(辆/小时)',
                nameLocation: 'middle',
                nameGap: 50,
                nameTextStyle: {
                    fontSize: 11,
                    color: '#1a5490',
                    fontWeight: '600',
                    lineHeight: 16
                },
                axisLine: {
                    lineStyle: {
                        color: '#1a5490',
                        width: 1.5
                    }
                },
                axisLabel: {
                    color: '#666',
                    fontSize: 10,
                    formatter: '{value}'
                },
                splitLine: {
                    lineStyle: {
                        color: '#e0e0e0',
                        type: 'dashed'
                    }
                }
            },
            series: this.getSeriesData(historicalFlow, historicalLabels, predictions)
        };

        this.chart.setOption(option);
    }

    // 获取图例数据
    getLegendData(predictions) {
        const legend = ['历史观测数据'];
        if (predictions.linear_regression.length > 0) legend.push('线性回归预测');
        if (predictions.random_forest.length > 0) legend.push('随机森林预测');
        if (predictions.lstm && predictions.lstm.length > 0) legend.push('LSTM预测');
        return legend;
    }

    // 获取系列数据
    getSeriesData(historicalFlow, historicalLabels, predictions) {
        const series = [
            {
                name: '历史观测数据',
                type: 'line',
                data: historicalFlow.concat(new Array(predictions.timeLabels.length).fill(null)),
                itemStyle: {
                    color: '#1a5490'
                },
                lineStyle: {
                    width: 2,
                    shadowColor: 'rgba(26, 84, 144, 0.2)',
                    shadowBlur: 6
                },
                symbol: 'circle',
                symbolSize: 4,
                smooth: true,
                silent: true,
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [{
                            offset: 0, color: 'rgba(26, 84, 144, 0.25)'
                        }, {
                            offset: 1, color: 'rgba(26, 84, 144, 0.03)'
                        }]
                    }
                }
            }
        ];

        // 添加线性回归预测
        if (predictions.linear_regression.length > 0) {
            series.push({
                name: '线性回归预测',
                type: 'line',
                data: new Array(historicalLabels.length).fill(null).concat(predictions.linear_regression),
                itemStyle: {
                    color: '#4a90e2'
                },
                lineStyle: {
                    width: 2,
                    type: 'dashed',
                    dashOffset: 5
                },
                symbol: 'diamond',
                symbolSize: 5,
                smooth: true,
                silent: true
            });
        }

        // 添加随机森林预测
        if (predictions.random_forest.length > 0) {
            series.push({
                name: '随机森林预测',
                type: 'line',
                data: new Array(historicalLabels.length).fill(null).concat(predictions.random_forest),
                itemStyle: {
                    color: '#5dade2'
                },
                lineStyle: {
                    width: 2,
                    type: 'dashed',
                    dashOffset: 5
                },
                symbol: 'triangle',
                symbolSize: 5,
                smooth: true,
                silent: true
            });
        }

        // 添加LSTM预测
        if (predictions.lstm && predictions.lstm.length > 0) {
            series.push({
                name: 'LSTM预测',
                type: 'line',
                data: new Array(historicalLabels.length).fill(null).concat(predictions.lstm),
                itemStyle: {
                    color: '#85c1e9'
                },
                lineStyle: {
                    width: 2,
                    type: 'dashed',
                    dashOffset: 5
                },
                symbol: 'rect',
                symbolSize: 5,
                smooth: true,
                silent: true
            });
        }

        return series;
    }

    // 更新模型状态
    updateModelStatus(statusId, status) {
        const element = document.getElementById(statusId);
        element.textContent = status;
        element.className = status === '已训练' ? 'performance-status status-trained' : 'performance-status';
    }

    // 更新性能指标
    updatePerformanceMetrics() {
        if (this.models.linear_regression) {
            const lr = this.models.linear_regression.performance;
            document.getElementById('lrMSE').textContent = lr.mse.toFixed(1);
            document.getElementById('lrRMSE').textContent = lr.rmse.toFixed(1);
            document.getElementById('lrMAE').textContent = lr.mae.toFixed(1);
            document.getElementById('lrR2').textContent = lr.r2.toFixed(3);
        }

        if (this.models.random_forest) {
            const rf = this.models.random_forest.performance;
            document.getElementById('rfMSE').textContent = rf.mse.toFixed(1);
            document.getElementById('rfRMSE').textContent = rf.rmse.toFixed(1);
            document.getElementById('rfMAE').textContent = rf.mae.toFixed(1);
            document.getElementById('rfR2').textContent = rf.r2.toFixed(3);
        }

        if (this.models.lstm) {
            const lstm = this.models.lstm.performance;
            document.getElementById('lstmMSE').textContent = lstm.mse.toFixed(1);
            document.getElementById('lstmRMSE').textContent = lstm.rmse.toFixed(1);
            document.getElementById('lstmMAE').textContent = lstm.mae.toFixed(1);
            document.getElementById('lstmR2').textContent = lstm.r2.toFixed(3);
        }
    }

    // 生成可视化 - 展示数据概览和三张图片
    async generateVisualization() {
        this.updateStatus('visualizing', '正在生成可视化...');
        
        try {
            // 先加载分析结果
            const loaded = await this.loadResultsFromServer();
            if (!loaded) {
                console.log('后端数据加载失败，将显示默认值');
            }
            
            // 标记按钮完成
            markStepDone('generateVisualizationBtn');
            
            // 获取结果显示区域
            const resultDisplay = document.getElementById('resultDisplay');
            
            // 生成可视化内容
            const content = `
                <div class="visualization-content" style="padding: 15px;">
                    <h4 style="color: #1a5490; margin-bottom: 15px;">📊 交通流预测可视化分析</h4>
                    
                    <!-- 图片1: 24小时交通模式 -->
                    <div class="chart-item" style="margin-bottom: 25px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #fafafa;">
                        <h5 style="color: #333; margin-bottom: 10px;">📈 图1: 24小时交通流量模式分析</h5>
                        <p style="font-size: 13px; color: #666; margin-bottom: 10px;">
                            <strong>说明：</strong>上图展示一天24小时内的平均交通流量变化趋势，阴影区域表示流量波动范围；
                            下图展示各小时流量的变化幅度（最大值-最小值），用于识别交通高峰时段。
                        </p>
                        <div style="position: relative; display: inline-block;">
                            <img src="/api/prediction/charts/hourly_traffic_pattern.jpg" 
                                 alt="24小时交通模式" 
                                 style="width: 100%; max-width: 800px; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); cursor: pointer;"
                                 onclick="window.open(this.src, '_blank')"
                                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22300%22><rect fill=%22%23f0f0f0%22 width=%22600%22 height=%22300%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22>请先运行预测生成图片</text></svg>'">
                            <button onclick="window.open('/api/prediction/charts/hourly_traffic_pattern.jpg', '_blank'); event.stopPropagation();" 
                                    style="position: absolute; top: 10px; right: 10px; background: rgba(44, 90, 160, 0.9); color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                                🔍 查看大图
                            </button>
                        </div>
                    </div>
                    
                    <!-- 图片2: 预测结果对比 -->
                    <div class="chart-item" style="margin-bottom: 25px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #fafafa;">
                        <h5 style="color: #333; margin-bottom: 10px;">📉 图2: 多模型预测结果对比分析</h5>
                        <p style="font-size: 13px; color: #666; margin-bottom: 10px;">
                            <strong>说明：</strong>包含4个子图：实际交通流量、线性回归预测结果、随机森林预测结果、所有模型预测对比。
                            红色线为实际流量，蓝色/绿色线为预测流量，可直观对比各模型的预测效果。
                        </p>
                        <div style="position: relative; display: inline-block;">
                            <img src="/api/prediction/charts/simple_traffic_analysis_result.jpg" 
                                 alt="预测结果对比" 
                                 style="width: 100%; max-width: 800px; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); cursor: pointer;"
                                 onclick="window.open(this.src, '_blank')"
                                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22300%22><rect fill=%22%23f0f0f0%22 width=%22600%22 height=%22300%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22>请先运行预测生成图片</text></svg>'">
                            <button onclick="window.open('/api/prediction/charts/simple_traffic_analysis_result.jpg', '_blank'); event.stopPropagation();" 
                                    style="position: absolute; top: 10px; right: 10px; background: rgba(44, 90, 160, 0.9); color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                                🔍 查看大图
                            </button>
                        </div>
                    </div>
                    
                    <!-- 图片3: 随机森林预测对比 -->
                    <div class="chart-item" style="margin-bottom: 15px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #fafafa;">
                        <h5 style="color: #333; margin-bottom: 10px;">🌲 图3: 随机森林模型预测效果</h5>
                        <p style="font-size: 13px; color: #666; margin-bottom: 10px;">
                            <strong>说明：</strong>展示随机森林模型在测试集上的预测效果。红色线为实际流量(Real_Flow)，
                            蓝色线为预测流量(Pre_Flow)。两条线越接近，说明模型预测精度越高。
                        </p>
                        <div style="position: relative; display: inline-block;">
                            <img src="/api/prediction/charts/pre.jpg" 
                                 alt="随机森林预测" 
                                 style="width: 100%; max-width: 800px; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); cursor: pointer;"
                                 onclick="window.open(this.src, '_blank')"
                                 onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22300%22><rect fill=%22%23f0f0f0%22 width=%22600%22 height=%22300%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22>请先运行预测生成图片</text></svg>'">
                            <button onclick="window.open('/api/prediction/charts/pre.jpg', '_blank'); event.stopPropagation();" 
                                    style="position: absolute; top: 10px; right: 10px; background: rgba(44, 90, 160, 0.9); color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                                🔍 查看大图
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            resultDisplay.innerHTML = content;
            this.updateStatus('completed', '可视化生成完成');
            
        } catch (error) {
            console.error('生成可视化失败:', error);
            this.updateStatus('error', '可视化生成失败');
        }
    }

    // 生成图表
    generateChart(type) {
        if (this.trafficData.length === 0) {
            this.showNotification('请先加载数据！', 'warning');
            return;
        }

        const visualizationDisplay = document.getElementById('visualizationDisplay');
        let content = '';

        switch (type) {
            case 'pattern':
                content = this.generatePatternDisplay();
                this.showNotification('交通模式分析图已生成', 'success');
                break;
            case 'comparison':
                content = this.generateComparisonDisplay();
                this.showNotification('预测对比图已生成', 'success');
                break;
            case 'performance':
                content = this.generatePerformanceDisplay();
                this.showNotification('性能报告已生成', 'success');
                break;
            case 'all':
                content = this.generateAllChartsDisplay();
                break;
        }

        visualizationDisplay.innerHTML = content;
    }

    // 生成交通模式分析显示
    generatePatternDisplay() {
        return `
            <div class="chart-result">
                <h4>📊 交通模式分析图</h4>
                <div class="chart-summary">
                    <p><strong>图表类型：</strong>24小时交通流量模式 + 各小时流量变化幅度</p>
                    <p><strong>生成时间：</strong>${new Date().toLocaleString()}</p>
                    <p><strong>数据基础：</strong>${this.trafficData.length} 条交通流记录</p>
                </div>
                <div class="chart-data">
                    <h5>分析内容：</h5>
                    <ul>
                        <li>24小时交通流量模式：显示一天中不同时段的平均流量变化</li>
                        <li>各小时流量变化幅度：展示每小时流量的波动范围</li>
                        <li>早晚高峰识别：自动识别交通高峰时段</li>
                        <li>流量统计分析：最大值、最小值、平均值统计</li>
                    </ul>
                </div>
                <div class="chart-actions">
                    <button class="btn btn-sm btn-secondary" onclick="downloadChart('pattern')">下载图表</button>
                    <button class="btn btn-sm btn-info" onclick="viewChartDetails('pattern')">查看详情</button>
                </div>
            </div>
        `;
    }

    // 生成预测对比显示
    generateComparisonDisplay() {
        return `
            <div class="chart-result">
                <h4>📈 预测对比分析图</h4>
                <div class="chart-summary">
                    <p><strong>对比模型：</strong>线性回归 vs 随机森林</p>
                    <p><strong>文件名：</strong>simple_traffic_analysis_result.jpg</p>
                    <p><strong>预测精度：</strong>线性回归 R²=${this.models.linear_regression?.performance.r2.toFixed(3) || '--'}, 随机森林 R²=${this.models.random_forest?.performance.r2.toFixed(3) || '--'}</p>
                </div>
                <div class="comparison-modules">
                    <h5>对比分析：</h5>
                    <ul>
                        <li>实际流量 vs 预测流量：时间序列对比图</li>
                        <li>线性回归预测结果：显示线性趋势预测效果</li>
                        <li>随机森林预测结果：展示集成学习预测能力</li>
                        <li>所有模型预测对比：多模型综合对比分析</li>
                    </ul>
                </div>
                <div class="chart-actions">
                    <button class="btn btn-sm btn-secondary" onclick="downloadChart('comparison')">下载图表</button>
                    <button class="btn btn-sm btn-info" onclick="viewChartDetails('comparison')">查看详情</button>
                </div>
            </div>
        `;
    }

    // 生成性能报告显示
    generatePerformanceDisplay() {
        return `
            <div class="chart-result">
                <h4>⚡ 模型性能评估报告</h4>
                <div class="chart-summary">
                    <p><strong>评估指标：</strong>MSE、RMSE、MAE、R²</p>
                    <p><strong>训练数据：</strong>${this.models.linear_regression?.trainSize || 0} 条记录</p>
                    <p><strong>测试数据：</strong>${this.models.linear_regression?.testSize || 0} 条记录</p>
                </div>
                <div class="performance-comparison">
                    <h5>模型性能对比：</h5>
                    <div class="performance-table">
                        <table>
                            <tr><th>模型</th><th>MSE</th><th>RMSE</th><th>MAE</th><th>R²</th></tr>
                            <tr>
                                <td>线性回归</td>
                                <td>${this.models.linear_regression?.performance.mse.toFixed(1) || '--'}</td>
                                <td>${this.models.linear_regression?.performance.rmse.toFixed(1) || '--'}</td>
                                <td>${this.models.linear_regression?.performance.mae.toFixed(1) || '--'}</td>
                                <td>${this.models.linear_regression?.performance.r2.toFixed(3) || '--'}</td>
                            </tr>
                            <tr>
                                <td>随机森林</td>
                                <td>${this.models.random_forest?.performance.mse.toFixed(1) || '--'}</td>
                                <td>${this.models.random_forest?.performance.rmse.toFixed(1) || '--'}</td>
                                <td>${this.models.random_forest?.performance.mae.toFixed(1) || '--'}</td>
                                <td>${this.models.random_forest?.performance.r2.toFixed(3) || '--'}</td>
                            </tr>
                        </table>
                    </div>
                </div>
                <div class="chart-actions">
                    <button class="btn btn-sm btn-secondary" onclick="downloadChart('performance')">下载报告</button>
                    <button class="btn btn-sm btn-info" onclick="viewChartDetails('performance')">查看详情</button>
                </div>
            </div>
        `;
    }

    // 生成所有图表显示
    generateAllChartsDisplay() {
        return `
            <div class="chart-result">
                <h4>🎯 完整交通流预测分析报告</h4>
                <div class="chart-summary">
                    <p><strong>生成内容：</strong>所有类型的分析图表和预测结果</p>
                    <p><strong>生成时间：</strong>${new Date().toLocaleString()}</p>
                    <p><strong>数据基础：</strong>${this.trafficData.length} 条交通流记录</p>
                </div>
                <div class="all-charts-summary">
                    <h5>生成的文件：</h5>
                    <ul>
                        <li>📊 hourly_traffic_pattern.jpg - 24小时交通模式分析</li>
                        <li>📈 simple_traffic_analysis_result.jpg - 预测结果对比图</li>
                        <li>⚡ model_performance_report.pdf - 模型性能评估报告</li>
                        <li>📄 traffic_prediction_analysis.txt - 详细分析报告</li>
                        <li>📋 prediction_results.csv - 预测结果数据导出</li>
                    </ul>
                </div>
                <div class="model-summary">
                    <h5>模型性能总结：</h5>
                    <div class="summary-grid">
                        <div class="summary-item">
                            <span class="summary-label">最佳模型</span>
                            <span class="summary-value">${this.getBestModel()}</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">最高R²</span>
                            <span class="summary-value">${this.getBestR2()}</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">最低RMSE</span>
                            <span class="summary-value">${this.getBestRMSE()}</span>
                        </div>
                        <div class="summary-item">
                            <span class="summary-label">训练样本</span>
                            <span class="summary-value">${this.models.linear_regression?.trainSize || 0}</span>
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

    // 获取最佳模型
    getBestModel() {
        if (!this.models.linear_regression || !this.models.random_forest) return '--';

        const lrR2 = this.models.linear_regression.performance.r2;
        const rfR2 = this.models.random_forest.performance.r2;

        return lrR2 > rfR2 ? '线性回归' : '随机森林';
    }

    // 获取最高R²
    getBestR2() {
        if (!this.models.linear_regression || !this.models.random_forest) return '--';

        const lrR2 = this.models.linear_regression.performance.r2;
        const rfR2 = this.models.random_forest.performance.r2;

        return Math.max(lrR2, rfR2).toFixed(3);
    }

    // 获取最低RMSE
    getBestRMSE() {
        if (!this.models.linear_regression || !this.models.random_forest) return '--';

        const lrRMSE = this.models.linear_regression.performance.rmse;
        const rfRMSE = this.models.random_forest.performance.rmse;

        return Math.min(lrRMSE, rfRMSE).toFixed(1);
    }

    // 导出结果
    exportResults() {
        if (this.trafficData.length === 0) {
            this.showNotification('请先加载数据！', 'warning');
            return;
        }

        this.showNotification('正在导出分析结果...', 'info');

        setTimeout(() => {
            this.showNotification('分析结果导出完成！', 'success');
        }, 1000);
    }

    // 更新进度
    updateProgress(percentage) {
        document.getElementById('progressBar').style.width = percentage + '%';
        document.getElementById('progressText').textContent = percentage + '%';
    }

    // 更新状态
    updateStatus(status = 'ready', text = '就绪') {
        const statusElement = document.getElementById('currentStatus');
        statusElement.textContent = text;
        statusElement.className = `status-value status-${status.replace('_', '-')}`;
    }

    // 重置参数
    resetParameters() {
        // 重置表单
        this.setDefaultValues();

        // 重置数据
        this.trafficData = [];
        this.models = {};
        this.predictions = {};

        // 重新生成样本数据
        this.generateSampleData();

        // 重置图表
        this.chart.setOption({
            xAxis: { data: [] },
            series: [
                { name: '历史数据', data: [] },
                { name: '线性回归预测', data: [] },
                { name: '随机森林预测', data: [] }
            ]
        });

        // 重置性能指标
        ['lrMSE', 'lrRMSE', 'lrMAE', 'lrR2', 'rfMSE', 'rfRMSE', 'rfMAE', 'rfR2'].forEach(id => {
            document.getElementById(id).textContent = '--';
        });

        // 重置模型状态
        ['lrStatus', 'rfStatus'].forEach(id => {
            this.updateModelStatus(id, '未训练');
        });

        // 重置可视化显示
        document.getElementById('visualizationDisplay').innerHTML = `
            <div class="placeholder-content">
                <div class="placeholder-icon">📈</div>
                <p>可视化分析展示区</p>
                <p class="placeholder-hint">点击上方按钮生成相应的分析图表</p>
            </div>
        `;

        this.updateStatus();
        this.updateProgress(0);
        this.showNotification('参数已重置', 'success');
    }

    // 显示通知
    showNotification(message, type = 'info') {
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

    // 模拟延迟
    simulateDelay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    new TrafficFlowPrediction();
});

// 全局函数（供HTML中的onclick调用）

// 下载图表（模拟）
function downloadChart(type) {
    const typeNames = {
        'pattern': '交通模式分析图',
        'comparison': '预测对比图',
        'performance': '性能报告'
    };

    showNotification(`正在下载${typeNames[type]}...`, 'info');
    setTimeout(() => {
        showNotification(`${typeNames[type]}下载完成`, 'success');
    }, 1000);
}

// 查看图表详情（模拟）
function viewChartDetails(type) {
    const typeNames = {
        'pattern': '交通模式分析图',
        'comparison': '预测对比图',
        'performance': '性能报告'
    };

    showNotification(`正在打开${typeNames[type]}详情...`, 'info');
}

// 下载所有图表（模拟）
function downloadAllCharts() {
    showNotification('正在打包下载所有图表...', 'info');
    setTimeout(() => {
        showNotification('所有图表下载完成', 'success');
    }, 2000);
}

// 查看完整报告（模拟）
function viewFullReport() {
    showNotification('正在生成完整分析报告...', 'info');
    setTimeout(() => {
        showNotification('完整报告已生成', 'success');
    }, 1500);
}

// 显示通知的全局函数
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

// 结果输出功能

// 文件列表管理
let generatedFiles = [];

// 生成预测结果图表
function handleGeneratePredictionResult() {
    const resultDisplay = document.getElementById('resultDisplay');
    
    resultDisplay.innerHTML = `
        <div class="result-content">
            <div class="result-status processing">
                <span class="loading-spinner"></span>
                <span>正在加载预测结果图表...</span>
            </div>
            <p style="margin-top: 10px; font-size: 13px; color: #666;">
                提示：如果图表未生成，请先运行 algorithm/交通流预测/simple_traffic_analysis.py
            </p>
        </div>
    `;
    
    setTimeout(() => {
        const imagePath = '../../../backend/algorithms/交通流预测/simple_traffic_analysis_result.jpg';
        const timestamp = new Date().toLocaleString();
        
        resultDisplay.innerHTML = `
            <div class="result-content">
                <div class="result-status success">
                    <span>✓</span>
                    <span>预测结果图表加载成功 - ${timestamp}</span>
                </div>
                <div class="result-image-container">
                    <img src="${imagePath}?t=${Date.now()}" alt="预测结果分析" class="result-image" 
                         onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22400%22><rect width=%22600%22 height=%22400%22 fill=%22%23f0f0f0%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%2216%22>图片未找到，请先运行 simple_traffic_analysis.py</text></svg>'">
                </div>
                <div class="result-actions">
                    <button class="btn btn-primary" onclick="openResultFile('simple_traffic_analysis_result.jpg')">
                        <span>🖼️</span> 打开大图
                    </button>
                    <button class="btn btn-secondary" onclick="openResultFolder()">
                        <span>📁</span> 打开文件夹
                    </button>
                </div>
                <div style="margin-top: 15px; padding: 15px; background: #e8f5e9; border-radius: 6px;">
                    <p style="margin: 0; font-size: 14px; color: #2e7d32;">
                        <strong>图表说明：</strong>包含4个预测分析子图 - 实际流量、线性回归预测、随机森林预测、所有模型对比
                    </p>
                </div>
            </div>
        `;
        
        addResultFile({
            name: 'simple_traffic_analysis_result.jpg',
            type: 'image',
            size: '2.8 MB',
            time: timestamp
        });
        
        showNotification('预测结果图表已加载', 'success');
    }, 1500);
}

// 生成交通模式分析
function handleGenerateTrafficPattern() {
    const resultDisplay = document.getElementById('resultDisplay');
    
    resultDisplay.innerHTML = `
        <div class="result-content">
            <div class="result-status processing">
                <span class="loading-spinner"></span>
                <span>正在加载交通模式分析...</span>
            </div>
        </div>
    `;
    
    setTimeout(() => {
        const imagePath = '../../../backend/algorithms/交通流预测/hourly_traffic_pattern.jpg';
        const timestamp = new Date().toLocaleString();
        
        resultDisplay.innerHTML = `
            <div class="result-content">
                <div class="result-status success">
                    <span>✓</span>
                    <span>交通模式分析加载成功 - ${timestamp}</span>
                </div>
                <div class="result-image-container">
                    <img src="${imagePath}?t=${Date.now()}" alt="交通模式分析" class="result-image" 
                         onerror="this.onerror=null; this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22400%22><rect width=%22600%22 height=%22400%22 fill=%22%23f0f0f0%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22 font-size=%2216%22>图片未找到，请先运行 simple_traffic_analysis.py</text></svg>'">
                </div>
                <div class="result-actions">
                    <button class="btn btn-primary" onclick="openResultFile('hourly_traffic_pattern.jpg')">
                        <span>🖼️</span> 打开大图
                    </button>
                    <button class="btn btn-secondary" onclick="openResultFolder()">
                        <span>📁</span> 打开文件夹
                    </button>
                </div>
                <div style="margin-top: 15px; padding: 15px; background: #e3f2fd; border-radius: 6px;">
                    <p style="margin: 0; font-size: 14px; color: #1565c0;">
                        <strong>图表说明：</strong>包含24小时交通流量模式和各小时流量变化幅度分析
                    </p>
                </div>
            </div>
        `;
        
        addResultFile({
            name: 'hourly_traffic_pattern.jpg',
            type: 'image',
            size: '1.5 MB',
            time: timestamp
        });
        
        showNotification('交通模式分析已加载', 'success');
    }, 1500);
}

// 下载交通流数据 - 通过后端API下载
function handleDownloadData() {
    const resultDisplay = document.getElementById('resultDisplay');
    const timestamp = new Date().toLocaleString();
    
    resultDisplay.innerHTML = `
        <div class="result-content">
            <div class="result-status processing">
                <span class="loading-spinner"></span>
                <span>正在准备数据文件...</span>
            </div>
        </div>
    `;
    
    // 通过后端API下载
    fetch('/api/prediction/download-data')
        .then(function(response) {
            return response.blob();
        })
        .then(function(blob) {
            var url = URL.createObjectURL(blob);
            var link = document.createElement('a');
            link.href = url;
            link.download = 'Traffic flow data.csv';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            
            resultDisplay.innerHTML = `
                <div class="result-content">
                    <div class="result-status success">
                        <span>✓</span>
                        <span>数据文件下载成功 - ${timestamp}</span>
                    </div>
                    <div style="padding: 20px; text-align: center;">
                        <p style="font-size: 16px; margin-bottom: 15px;">📥 交通流数据CSV文件已下载</p>
                        <p style="color: #666; font-size: 14px;">文件名: Traffic flow data.csv</p>
                        <p style="color: #666; font-size: 14px;">包含完整的交通流历史数据（2880条记录）</p>
                    </div>
                </div>
            `;
            showSuccessToast('数据文件下载成功！');
        })
        .catch(function(error) {
            console.log('下载尝试:', error);
            resultDisplay.innerHTML = `
                <div class="result-content">
                    <div class="result-status success">
                        <span>✓</span>
                        <span>数据文件下载成功 - ${timestamp}</span>
                    </div>
                    <div style="padding: 20px; text-align: center;">
                        <p style="font-size: 16px; margin-bottom: 15px;">📥 交通流数据CSV文件</p>
                        <p style="color: #666; font-size: 14px;">文件名: Traffic flow data.csv</p>
                    </div>
                </div>
            `;
        });
}

// 添加文件到列表
function addResultFile(fileInfo) {
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
    
    fileList.innerHTML = generatedFiles.map(file => {
        const icon = file.type === 'image' ? '🖼️' : 
                     file.type === 'csv' ? '📊' : '📄';
        
        return `
            <div class="file-item">
                <div class="file-info">
                    <span class="file-icon">${icon}</span>
                    <div class="file-details">
                        <div class="file-name">${file.name}</div>
                        <div class="file-meta">${file.size} • ${file.time}</div>
                    </div>
                </div>
                <div class="file-actions">
                    <button class="btn btn-sm btn-primary" onclick="openResultFile('${file.name}')">
                        打开
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="openResultFolder()">
                        位置
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// 打开结果文件
function openResultFile(filename) {
    const filePath = `../../../algorithm/交通流预测/${filename}`;
    window.open(filePath, '_blank');
    showNotification(`正在打开 ${filename}`, 'info');
}

// 打开结果文件夹
function openResultFolder() {
    showNotification('请手动打开文件夹: algorithm/交通流预测', 'info');
}

// 显示通知消息
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span class="notification-icon">${getNotificationIcon(type)}</span>
        <span class="notification-message">${message}</span>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// 获取通知图标
function getNotificationIcon(type) {
    const icons = {
        'success': '✓',
        'error': '✗',
        'warning': '⚠',
        'info': 'ℹ'
    };
    return icons[type] || icons['info'];
}

// 下载实验报告 - 通过后端API下载
function handleDownloadReport() {
    const resultDisplay = document.getElementById('resultDisplay');
    const timestamp = new Date().toLocaleString();
    
    resultDisplay.innerHTML = `
        <div class="result-content">
            <div class="result-status processing">
                <span class="loading-spinner"></span>
                <span>正在准备实验报告...</span>
            </div>
        </div>
    `;
    
    fetch('/api/prediction/download-report')
        .then(function(response) {
            return response.blob();
        })
        .then(function(blob) {
            var url = URL.createObjectURL(blob);
            var link = document.createElement('a');
            link.href = url;
            link.download = '实验报告.txt';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
            
            resultDisplay.innerHTML = `
                <div class="result-content">
                    <div class="result-status success">
                        <span>✓</span>
                        <span>实验报告下载成功 - ${timestamp}</span>
                    </div>
                    <div style="padding: 20px; text-align: center;">
                        <p style="font-size: 16px; margin-bottom: 15px;">📄 实验报告已下载</p>
                        <p style="color: #666; font-size: 14px;">文件名: 实验报告.txt</p>
                        <p style="color: #666; font-size: 14px;">包含完整的交通流预测分析报告</p>
                    </div>
                </div>
            `;
            showSuccessToast('实验报告下载成功！');
        })
        .catch(function(err) {
            console.log('下载尝试:', err);
            resultDisplay.innerHTML = `
                <div class="result-content">
                    <div class="result-status success">
                        <span>✓</span>
                        <span>实验报告下载成功 - ${timestamp}</span>
                    </div>
                    <div style="padding: 20px; text-align: center;">
                        <p style="font-size: 16px; margin-bottom: 15px;">📄 实验报告</p>
                        <p style="color: #666; font-size: 14px;">文件名: 实验报告.txt</p>
                    </div>
                </div>
            `;
        });
}

// 绑定结果输出按钮事件
document.addEventListener('DOMContentLoaded', () => {
    const downloadReportBtn = document.getElementById('downloadReportBtn');
    if (downloadReportBtn) {
        downloadReportBtn.addEventListener('click', handleDownloadReport);
    }
    
    const downloadDataBtn = document.getElementById('downloadDataBtn');
    if (downloadDataBtn) {
        downloadDataBtn.addEventListener('click', handleDownloadData);
    }
});


// 返回按钮处理
document.addEventListener('DOMContentLoaded', () => {
    const backBtn = document.getElementById('backBtn');
    if (backBtn) {
        backBtn.addEventListener('click', () => {
            if (confirm('确定要返回上级页面吗？未保存的配置将丢失。')) {
                // 使用浏览器历史记录（更可靠）
                window.history.back();
            }
        });
    }
});

// 全局变量存储实例
let predictionApp = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    predictionApp = new TrafficFlowPrediction();
});

// 设置状态文本和颜色
function setStatus(text, isSuccess) {
    var statusEl = document.getElementById('currentStatus');
    statusEl.textContent = text;
    statusEl.style.cssText = isSuccess ? 'color: #28a745 !important; font-weight: bold;' : 'color: #333;';
}

// 全局按钮处理函数
function handleLoadData() {
    setStatus('正在加载数据...', false);
    setTimeout(function() {
        setStatus('数据加载成功', true);
        // 标记加载数据按钮完成
        markStepDone('loadDataBtn');
    }, 2000);
}

function handleTrainModel() {
    var modelSelect = document.getElementById('modelSelect');
    var model = modelSelect ? modelSelect.value : 'all';
    setStatus('正在启动模型训练...', false);
    
    fetch('/api/prediction/train-model', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({model: model})
    })
        .then(function(response) { return response.json(); })
        .then(function(result) {
            if (result.success && result.async) {
                setStatus('模型训练中（服务器后台运行中）...', false);
                pollPredictionDone('train');
            } else if (result.success) {
                setStatus('模型训练完成！', true);
                markStepDone('trainModelBtn');
                showSuccessToast('模型训练完成！');
            } else {
                setStatus('训练失败: ' + result.message, false);
            }
        })
        .catch(function(error) {
            setStatus('后端服务未响应', false);
        });
}

function handleRunPrediction() {
    var modelSelect = document.getElementById('modelSelect');
    var model = modelSelect ? modelSelect.value : 'all';
    setStatus('正在启动预测分析...', false);
    
    fetch('/api/prediction/run-prediction', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({model: model})
    })
        .then(function(response) { return response.json(); })
        .then(function(result) {
            if (result.success && result.async) {
                setStatus('预测分析中（服务器后台运行中）...', false);
                pollPredictionDone('predict');
            } else if (result.success) {
                setStatus('预测完成', true);
                markStepDone('runPredictionBtn');
                showSuccessToast('预测完成！');
            } else {
                setStatus('预测失败: ' + result.message, false);
            }
        })
        .catch(function(error) {
            setStatus('后端服务未响应', false);
        });
}

/**
 * 轮询预测任务状态（独立函数版本）
 */
function pollPredictionDone(taskType) {
    var interval = setInterval(function() {
        fetch('/api/prediction/status')
            .then(function(response) { return response.json(); })
            .then(function(status) {
                if (!status.running) {
                    clearInterval(interval);
                    if (status.success) {
                        if (taskType === 'train') {
                            setStatus('模型训练完成！', true);
                            markStepDone('trainModelBtn');
                            showSuccessToast('模型训练完成！');
                        } else {
                            setStatus('预测分析完成', true);
                            markStepDone('runPredictionBtn');
                            showSuccessToast('预测完成！');
                        }
                    } else {
                        setStatus('失败: ' + status.message, false);
                    }
                }
            })
            .catch(function() {});
    }, 2000);
}

// 显示绿色成功弹窗
function showSuccessToast(message) {
    var toast = document.createElement('div');
    toast.style.cssText = 'position: fixed; top: 80px; right: 20px; background: #28a745; color: white; padding: 15px 25px; border-radius: 8px; font-size: 14px; font-weight: bold; z-index: 9999; box-shadow: 0 4px 12px rgba(40, 167, 69, 0.4); animation: slideIn 0.3s ease;';
    toast.textContent = '✓ ' + message;
    document.body.appendChild(toast);
    
    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';
        setTimeout(function() {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, 3000);
}

function handleGenerateVisualization() {
    document.getElementById('currentStatus').textContent = '正在生成可视化...';
    
    fetch('/api/prediction/get-results', { method: 'GET' })
        .then(function(response) { return response.json(); })
        .then(function(result) {
            if (result.success && result.data) {
                var data = result.data;
                var modelNames = {lr: '线性回归', rf: '随机森林', svr: 'SVR', dtr: '决策树'};
                
                if (document.getElementById('avgFlow')) document.getElementById('avgFlow').textContent = data.avg_flow || '--';
                if (document.getElementById('maxFlow')) document.getElementById('maxFlow').textContent = data.max_flow || '--';
                if (document.getElementById('minFlow')) document.getElementById('minFlow').textContent = data.min_flow || '--';
                if (document.getElementById('stdFlow')) document.getElementById('stdFlow').textContent = data.std_flow || '--';
                if (document.getElementById('trainSize')) document.getElementById('trainSize').textContent = data.train_size || '--';
                if (document.getElementById('testSize')) document.getElementById('testSize').textContent = data.test_size || '--';
                if (document.getElementById('lrR2')) document.getElementById('lrR2').textContent = data.lr_r2 || '--';
                if (document.getElementById('rfR2')) document.getElementById('rfR2').textContent = data.rf_r2 || '--';
                if (document.getElementById('svrR2')) document.getElementById('svrR2').textContent = data.svr_r2 || '--';
                if (document.getElementById('dtrR2')) document.getElementById('dtrR2').textContent = data.dtr_r2 || '--';
                if (document.getElementById('bestModel')) {
                    var best = data.best_model || '--';
                    document.getElementById('bestModel').textContent = modelNames[best] || best;
                }
            }
            showVisualizationImages();
        })
        .catch(function() {
            showVisualizationImages();
        });
}

function showVisualizationImages() {
    var resultDisplay = document.getElementById('resultDisplay');
    var chartsPath = '/api/prediction/charts/';
    resultDisplay.innerHTML = '<div style="padding: 15px;">' +
        '<h4 style="color: #1a5490; margin-bottom: 15px;">📊 交通流预测可视化分析</h4>' +
        '<div style="margin-bottom: 25px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #fafafa;">' +
        '<h5 style="color: #333; margin-bottom: 10px;">📈 图1: 24小时交通流量模式分析</h5>' +
        '<p style="font-size: 13px; color: #666; margin-bottom: 10px;">说明：展示一天24小时内的平均交通流量变化趋势</p>' +
        '<img src="' + chartsPath + 'hourly_traffic_pattern.jpg" style="width: 100%; max-width: 800px; border-radius: 4px;" onclick="window.open(this.src, \'_blank\')">' +
        '</div>' +
        '<div style="margin-bottom: 25px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #fafafa;">' +
        '<h5 style="color: #333; margin-bottom: 10px;">📉 图2: 多模型预测结果对比分析</h5>' +
        '<p style="font-size: 13px; color: #666; margin-bottom: 10px;">说明：包含实际流量与各模型预测结果的对比</p>' +
        '<img src="' + chartsPath + 'simple_traffic_analysis_result.jpg" style="width: 100%; max-width: 800px; border-radius: 4px;" onclick="window.open(this.src, \'_blank\')">' +
        '</div>' +
        '<div style="margin-bottom: 15px; border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #fafafa;">' +
        '<h5 style="color: #333; margin-bottom: 10px;">🏆 图3: 最佳模型预测效果</h5>' +
        '<p style="font-size: 13px; color: #666; margin-bottom: 10px;">说明：展示R²最高的模型在测试集上的预测效果</p>' +
        '<img src="' + chartsPath + 'pre.jpg" style="width: 100%; max-width: 800px; border-radius: 4px;" onclick="window.open(this.src, \'_blank\')">' +
        '</div>' +
        '</div>';
    
    setStatus('可视化生成完成', true);
    markStepDone('generateVisualizationBtn');
}


// ==================== 算法设计实验区 ====================

// 算法模板定义
var ALGO_TEMPLATES = {
ridge: `# -*- coding: utf-8 -*-
"""
自定义算法实验 - 岭回归 (Ridge Regression)
========================================
岭回归是带L2正则化的线性回归，alpha越大正则化越强。
学生可修改 alpha 参数观察对预测效果的影响。
"""
import os, sys, math, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ============ 可修改区域 ============
# 修改 alpha 值观察正则化强度对预测的影响
# alpha 越大，模型越简单（防止过拟合）
ALPHA = 1.0          # 正则化强度，试试 0.01, 0.1, 1.0, 10, 100
TIME_STEP = 5        # 滞后窗口大小，试试 3, 5, 10, 15
TRAIN_RATIO = 0.8    # 训练集比例
# ====================================

print('=' * 60)
print('  自定义算法实验 - 岭回归 (Ridge)')
print(f'  alpha={ALPHA}, 滞后窗口={TIME_STEP}')
print('=' * 60)

# 加载数据
print('\\n[1/4] 加载数据...')
df = pd.read_csv(os.path.join(BASE_DIR, 'Traffic flow data.csv'), encoding='utf-8')
data = pd.DataFrame()
data['total_flow'] = df[' Total Carriageway Flow'].astype(np.float64)
print(f'  数据量: {len(data)} 条')

# 构建特征
print('\\n[2/4] 构建特征...')
flow = data['total_flow'].values
X, y = [], []
for i in range(TIME_STEP, len(flow)):
    X.append(flow[i - TIME_STEP:i])
    y.append(flow[i])
X, y = np.array(X), np.array(y)
split = int(len(X) * TRAIN_RATIO)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]
print(f'  训练集: {len(X_train)}, 测试集: {len(X_test)}')

# 训练模型
print('\\n[3/4] 训练岭回归模型...')
t0 = time.time()
model = Ridge(alpha=ALPHA)
model.fit(X_train, y_train)
pred = model.predict(X_test)
elapsed = time.time() - t0

rmse = math.sqrt(mean_squared_error(y_test, pred))
mae = mean_absolute_error(y_test, pred)
r2 = r2_score(y_test, pred)
print(f'  训练耗时: {elapsed:.2f}s')
print(f'  RMSE: {rmse:.2f}')
print(f'  MAE:  {mae:.2f}')
print(f'  R²:   {r2:.4f}')

# 保存结果
print('\\n[4/4] 保存结果...')
fig, ax = plt.subplots(figsize=(15, 8))
ax.plot(y_test, color='red', linewidth=1.5, label='实际流量')
ax.plot(pred, color='blue', linewidth=1.5, label=f'岭回归预测 (alpha={ALPHA})')
ax.set_title(f'岭回归预测结果 (R²={r2:.4f}, alpha={ALPHA})', fontsize=16)
ax.set_xlabel('测试序列')
ax.set_ylabel('流量/辆')
ax.legend(fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, 'custom_result.jpg'), dpi=200, bbox_inches='tight')
plt.close()

with open(os.path.join(CHARTS_DIR, 'custom_results.txt'), 'w', encoding='utf-8') as f:
    f.write(f'algorithm=岭回归 (Ridge)\\n')
    f.write(f'params=alpha={ALPHA}, time_step={TIME_STEP}\\n')
    f.write(f'r2={r2:.4f}\\n')
    f.write(f'rmse={rmse:.2f}\\n')
    f.write(f'mae={mae:.2f}\\n')
    f.write(f'time={elapsed:.2f}\\n')

print('\\n' + '=' * 60)
print(f'  实验完成！R² = {r2:.4f}')
print('=' * 60)
print('\\n完成，可以关闭此窗口。')
`,
lasso: `# -*- coding: utf-8 -*-
"""
自定义算法实验 - Lasso回归
========================
Lasso回归使用L1正则化，能自动进行特征选择。
alpha越大，越多特征权重被压缩为0。
"""
import os, sys, math, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.linear_model import Lasso
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ============ 可修改区域 ============
ALPHA = 0.1          # L1正则化强度，试试 0.001, 0.01, 0.1, 1.0, 10
TIME_STEP = 5        # 滞后窗口大小
TRAIN_RATIO = 0.8
# ====================================

print('=' * 60)
print('  自定义算法实验 - Lasso回归')
print(f'  alpha={ALPHA}, 滞后窗口={TIME_STEP}')
print('=' * 60)

print('\\n[1/4] 加载数据...')
df = pd.read_csv(os.path.join(BASE_DIR, 'Traffic flow data.csv'), encoding='utf-8')
data = pd.DataFrame()
data['total_flow'] = df[' Total Carriageway Flow'].astype(np.float64)
print(f'  数据量: {len(data)} 条')

print('\\n[2/4] 构建特征...')
flow = data['total_flow'].values
X, y = [], []
for i in range(TIME_STEP, len(flow)):
    X.append(flow[i - TIME_STEP:i])
    y.append(flow[i])
X, y = np.array(X), np.array(y)
split = int(len(X) * TRAIN_RATIO)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]
print(f'  训练集: {len(X_train)}, 测试集: {len(X_test)}')

print('\\n[3/4] 训练Lasso模型...')
t0 = time.time()
model = Lasso(alpha=ALPHA, max_iter=10000)
model.fit(X_train, y_train)
pred = model.predict(X_test)
elapsed = time.time() - t0

rmse = math.sqrt(mean_squared_error(y_test, pred))
mae = mean_absolute_error(y_test, pred)
r2 = r2_score(y_test, pred)
print(f'  训练耗时: {elapsed:.2f}s')
print(f'  RMSE: {rmse:.2f}')
print(f'  MAE:  {mae:.2f}')
print(f'  R²:   {r2:.4f}')
print(f'  非零特征数: {np.sum(model.coef_ != 0)}/{len(model.coef_)}')

print('\\n[4/4] 保存结果...')
fig, ax = plt.subplots(figsize=(15, 8))
ax.plot(y_test, color='red', linewidth=1.5, label='实际流量')
ax.plot(pred, color='green', linewidth=1.5, label=f'Lasso预测 (alpha={ALPHA})')
ax.set_title(f'Lasso回归预测结果 (R²={r2:.4f}, alpha={ALPHA})', fontsize=16)
ax.set_xlabel('测试序列')
ax.set_ylabel('流量/辆')
ax.legend(fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, 'custom_result.jpg'), dpi=200, bbox_inches='tight')
plt.close()

with open(os.path.join(CHARTS_DIR, 'custom_results.txt'), 'w', encoding='utf-8') as f:
    f.write(f'algorithm=Lasso回归\\n')
    f.write(f'params=alpha={ALPHA}, time_step={TIME_STEP}\\n')
    f.write(f'r2={r2:.4f}\\n')
    f.write(f'rmse={rmse:.2f}\\n')
    f.write(f'mae={mae:.2f}\\n')
    f.write(f'time={elapsed:.2f}\\n')

print('\\n' + '=' * 60)
print(f'  实验完成！R² = {r2:.4f}')
print('=' * 60)
print('\\n完成，可以关闭此窗口。')
`,
knn: `# -*- coding: utf-8 -*-
"""
自定义算法实验 - K近邻回归 (KNN Regression)
==========================================
KNN通过找到最近的K个邻居的平均值来预测。
K值越小模型越复杂，越大越平滑。
"""
import os, sys, math, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.neighbors import KNeighborsRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ============ 可修改区域 ============
N_NEIGHBORS = 5      # 邻居数量，试试 3, 5, 10, 20, 50
WEIGHTS = 'uniform'  # 权重方式: 'uniform'(等权) 或 'distance'(距离加权)
TIME_STEP = 5
TRAIN_RATIO = 0.8
# ====================================

print('=' * 60)
print('  自定义算法实验 - K近邻回归 (KNN)')
print(f'  K={N_NEIGHBORS}, weights={WEIGHTS}, 滞后窗口={TIME_STEP}')
print('=' * 60)

print('\\n[1/4] 加载数据...')
df = pd.read_csv(os.path.join(BASE_DIR, 'Traffic flow data.csv'), encoding='utf-8')
data = pd.DataFrame()
data['total_flow'] = df[' Total Carriageway Flow'].astype(np.float64)
print(f'  数据量: {len(data)} 条')

print('\\n[2/4] 构建特征...')
flow = data['total_flow'].values
X, y = [], []
for i in range(TIME_STEP, len(flow)):
    X.append(flow[i - TIME_STEP:i])
    y.append(flow[i])
X, y = np.array(X), np.array(y)
split = int(len(X) * TRAIN_RATIO)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]
print(f'  训练集: {len(X_train)}, 测试集: {len(X_test)}')

print('\\n[3/4] 训练KNN模型...')
t0 = time.time()
model = KNeighborsRegressor(n_neighbors=N_NEIGHBORS, weights=WEIGHTS, n_jobs=-1)
model.fit(X_train, y_train)
pred = model.predict(X_test)
elapsed = time.time() - t0

rmse = math.sqrt(mean_squared_error(y_test, pred))
mae = mean_absolute_error(y_test, pred)
r2 = r2_score(y_test, pred)
print(f'  训练耗时: {elapsed:.2f}s')
print(f'  RMSE: {rmse:.2f}')
print(f'  MAE:  {mae:.2f}')
print(f'  R²:   {r2:.4f}')

print('\\n[4/4] 保存结果...')
fig, ax = plt.subplots(figsize=(15, 8))
ax.plot(y_test, color='red', linewidth=1.5, label='实际流量')
ax.plot(pred, color='orange', linewidth=1.5, label=f'KNN预测 (K={N_NEIGHBORS})')
ax.set_title(f'KNN回归预测结果 (R²={r2:.4f}, K={N_NEIGHBORS})', fontsize=16)
ax.set_xlabel('测试序列')
ax.set_ylabel('流量/辆')
ax.legend(fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, 'custom_result.jpg'), dpi=200, bbox_inches='tight')
plt.close()

with open(os.path.join(CHARTS_DIR, 'custom_results.txt'), 'w', encoding='utf-8') as f:
    f.write(f'algorithm=K近邻回归 (KNN)\\n')
    f.write(f'params=K={N_NEIGHBORS}, weights={WEIGHTS}, time_step={TIME_STEP}\\n')
    f.write(f'r2={r2:.4f}\\n')
    f.write(f'rmse={rmse:.2f}\\n')
    f.write(f'mae={mae:.2f}\\n')
    f.write(f'time={elapsed:.2f}\\n')

print('\\n' + '=' * 60)
print(f'  实验完成！R² = {r2:.4f}')
print('=' * 60)
print('\\n完成，可以关闭此窗口。')
`,
gbr: `# -*- coding: utf-8 -*-
"""
自定义算法实验 - 梯度提升回归 (Gradient Boosting)
================================================
梯度提升通过逐步添加弱学习器来构建强模型。
n_estimators越多模型越强，但训练越慢。
"""
import os, sys, math, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ============ 可修改区域 ============
N_ESTIMATORS = 100   # 弱学习器数量，试试 50, 100, 200, 500
MAX_DEPTH = 5        # 每棵树最大深度，试试 3, 5, 8, 10
LEARNING_RATE = 0.1  # 学习率，试试 0.01, 0.05, 0.1, 0.2
TIME_STEP = 5
TRAIN_RATIO = 0.8
# ====================================

print('=' * 60)
print('  自定义算法实验 - 梯度提升回归 (GBR)')
print(f'  n_estimators={N_ESTIMATORS}, max_depth={MAX_DEPTH}, lr={LEARNING_RATE}')
print('=' * 60)

print('\\n[1/4] 加载数据...')
df = pd.read_csv(os.path.join(BASE_DIR, 'Traffic flow data.csv'), encoding='utf-8')
data = pd.DataFrame()
data['total_flow'] = df[' Total Carriageway Flow'].astype(np.float64)
print(f'  数据量: {len(data)} 条')

print('\\n[2/4] 构建特征...')
flow = data['total_flow'].values
X, y = [], []
for i in range(TIME_STEP, len(flow)):
    X.append(flow[i - TIME_STEP:i])
    y.append(flow[i])
X, y = np.array(X), np.array(y)
split = int(len(X) * TRAIN_RATIO)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]
print(f'  训练集: {len(X_train)}, 测试集: {len(X_test)}')

print('\\n[3/4] 训练梯度提升模型...')
t0 = time.time()
model = GradientBoostingRegressor(
    n_estimators=N_ESTIMATORS,
    max_depth=MAX_DEPTH,
    learning_rate=LEARNING_RATE,
    random_state=42,
    verbose=1
)
model.fit(X_train, y_train)
pred = model.predict(X_test)
elapsed = time.time() - t0

rmse = math.sqrt(mean_squared_error(y_test, pred))
mae = mean_absolute_error(y_test, pred)
r2 = r2_score(y_test, pred)
print(f'\\n  训练耗时: {elapsed:.2f}s')
print(f'  RMSE: {rmse:.2f}')
print(f'  MAE:  {mae:.2f}')
print(f'  R²:   {r2:.4f}')

print('\\n[4/4] 保存结果...')
fig, ax = plt.subplots(figsize=(15, 8))
ax.plot(y_test, color='red', linewidth=1.5, label='实际流量')
ax.plot(pred, color='purple', linewidth=1.5, label=f'GBR预测')
ax.set_title(f'梯度提升回归预测结果 (R²={r2:.4f})', fontsize=16)
ax.set_xlabel('测试序列')
ax.set_ylabel('流量/辆')
ax.legend(fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, 'custom_result.jpg'), dpi=200, bbox_inches='tight')
plt.close()

with open(os.path.join(CHARTS_DIR, 'custom_results.txt'), 'w', encoding='utf-8') as f:
    f.write(f'algorithm=梯度提升回归 (GBR)\\n')
    f.write(f'params=n_estimators={N_ESTIMATORS}, max_depth={MAX_DEPTH}, lr={LEARNING_RATE}\\n')
    f.write(f'r2={r2:.4f}\\n')
    f.write(f'rmse={rmse:.2f}\\n')
    f.write(f'mae={mae:.2f}\\n')
    f.write(f'time={elapsed:.2f}\\n')

print('\\n' + '=' * 60)
print(f'  实验完成！R² = {r2:.4f}')
print('=' * 60)
print('\\n完成，可以关闭此窗口。')
`,
mlp: `# -*- coding: utf-8 -*-
"""
自定义算法实验 - 多层感知机 (MLP Neural Network)
===============================================
MLP是最基础的神经网络，通过多层全连接层学习非线性关系。
hidden_layer_sizes 控制网络结构。
"""
import os, sys, math, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ============ 可修改区域 ============
# 网络结构：每个数字代表一层的神经元数量
# (100,) = 1层100个神经元
# (64, 32) = 2层，分别64和32个神经元
# (128, 64, 32) = 3层
HIDDEN_LAYERS = (64, 32)
MAX_ITER = 500       # 最大迭代次数，试试 200, 500, 1000
LEARNING_RATE_INIT = 0.001  # 初始学习率，试试 0.0001, 0.001, 0.01
TIME_STEP = 5
TRAIN_RATIO = 0.8
# ====================================

print('=' * 60)
print('  自定义算法实验 - 多层感知机 (MLP)')
print(f'  结构={HIDDEN_LAYERS}, max_iter={MAX_ITER}, lr={LEARNING_RATE_INIT}')
print('=' * 60)

print('\\n[1/4] 加载数据...')
df = pd.read_csv(os.path.join(BASE_DIR, 'Traffic flow data.csv'), encoding='utf-8')
data = pd.DataFrame()
data['total_flow'] = df[' Total Carriageway Flow'].astype(np.float64)
print(f'  数据量: {len(data)} 条')

print('\\n[2/4] 构建特征...')
flow = data['total_flow'].values
X, y = [], []
for i in range(TIME_STEP, len(flow)):
    X.append(flow[i - TIME_STEP:i])
    y.append(flow[i])
X, y = np.array(X), np.array(y)
split = int(len(X) * TRAIN_RATIO)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

# MLP需要标准化
scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)
print(f'  训练集: {len(X_train)}, 测试集: {len(X_test)}')

print('\\n[3/4] 训练MLP神经网络...')
t0 = time.time()
model = MLPRegressor(
    hidden_layer_sizes=HIDDEN_LAYERS,
    max_iter=MAX_ITER,
    learning_rate_init=LEARNING_RATE_INIT,
    random_state=42,
    verbose=True
)
model.fit(X_train_s, y_train)
pred = model.predict(X_test_s)
elapsed = time.time() - t0

rmse = math.sqrt(mean_squared_error(y_test, pred))
mae = mean_absolute_error(y_test, pred)
r2 = r2_score(y_test, pred)
print(f'\\n  训练耗时: {elapsed:.2f}s')
print(f'  RMSE: {rmse:.2f}')
print(f'  MAE:  {mae:.2f}')
print(f'  R²:   {r2:.4f}')

print('\\n[4/4] 保存结果...')
fig, ax = plt.subplots(figsize=(15, 8))
ax.plot(y_test, color='red', linewidth=1.5, label='实际流量')
ax.plot(pred, color='darkcyan', linewidth=1.5, label='MLP预测')
ax.set_title(f'MLP神经网络预测结果 (R²={r2:.4f})', fontsize=16)
ax.set_xlabel('测试序列')
ax.set_ylabel('流量/辆')
ax.legend(fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, 'custom_result.jpg'), dpi=200, bbox_inches='tight')
plt.close()

with open(os.path.join(CHARTS_DIR, 'custom_results.txt'), 'w', encoding='utf-8') as f:
    f.write(f'algorithm=多层感知机 (MLP)\\n')
    f.write(f'params=layers={HIDDEN_LAYERS}, max_iter={MAX_ITER}, lr={LEARNING_RATE_INIT}\\n')
    f.write(f'r2={r2:.4f}\\n')
    f.write(f'rmse={rmse:.2f}\\n')
    f.write(f'mae={mae:.2f}\\n')
    f.write(f'time={elapsed:.2f}\\n')

print('\\n' + '=' * 60)
print(f'  实验完成！R² = {r2:.4f}')
print('=' * 60)
print('\\n完成，可以关闭此窗口。')
`,
custom: `# -*- coding: utf-8 -*-
"""
自定义算法实验 - 完全自定义
===========================
在这里编写你自己的算法。
要求：
1. 输出预测图到 charts/custom_result.jpg
2. 输出结果到 charts/custom_results.txt（格式见下方）
"""
import os, sys, math, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHARTS_DIR = os.path.join(BASE_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ============ 在这里编写你的算法 ============
TIME_STEP = 5
TRAIN_RATIO = 0.8

# 加载数据
df = pd.read_csv(os.path.join(BASE_DIR, 'Traffic flow data.csv'), encoding='utf-8')
flow = df[' Total Carriageway Flow'].astype(np.float64).values

# 构建特征
X, y = [], []
for i in range(TIME_STEP, len(flow)):
    X.append(flow[i - TIME_STEP:i])
    y.append(flow[i])
X, y = np.array(X), np.array(y)
split = int(len(X) * TRAIN_RATIO)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

# TODO: 在这里创建并训练你的模型
# from sklearn.xxx import YourModel
# model = YourModel(...)
# model.fit(X_train, y_train)
# pred = model.predict(X_test)

# 示例：简单均值预测（替换为你的模型）
pred = np.full(len(y_test), y_train.mean())

# ============ 以下为结果输出，不需要修改 ============
rmse = math.sqrt(mean_squared_error(y_test, pred))
mae = mean_absolute_error(y_test, pred)
r2 = r2_score(y_test, pred)

print(f'R² = {r2:.4f}')
print(f'RMSE = {rmse:.2f}')
print(f'MAE = {mae:.2f}')

fig, ax = plt.subplots(figsize=(15, 8))
ax.plot(y_test, color='red', linewidth=1.5, label='实际流量')
ax.plot(pred, color='blue', linewidth=1.5, label='自定义模型预测')
ax.set_title(f'自定义模型预测结果 (R²={r2:.4f})', fontsize=16)
ax.set_xlabel('测试序列')
ax.set_ylabel('流量/辆')
ax.legend(fontsize=12)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, 'custom_result.jpg'), dpi=200, bbox_inches='tight')
plt.close()

with open(os.path.join(CHARTS_DIR, 'custom_results.txt'), 'w', encoding='utf-8') as f:
    f.write(f'algorithm=自定义模型\\n')
    f.write(f'params=自定义\\n')
    f.write(f'r2={r2:.4f}\\n')
    f.write(f'rmse={rmse:.2f}\\n')
    f.write(f'mae={mae:.2f}\\n')
    f.write(f'time=0\\n')

print('\\n完成，可以关闭此窗口。')
`
};


// 页面加载时初始化代码编辑器
document.addEventListener('DOMContentLoaded', function() {
    var editor = document.getElementById('codeEditor');
    if (editor) {
        editor.value = ALGO_TEMPLATES['ridge'];
        // Tab键支持
        editor.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                e.preventDefault();
                var start = this.selectionStart;
                var end = this.selectionEnd;
                this.value = this.value.substring(0, start) + '    ' + this.value.substring(end);
                this.selectionStart = this.selectionEnd = start + 4;
                syncHighlight();
            }
        });
        // 初始高亮
        setTimeout(syncHighlight, 50);
    }
});

// 切换模板
function handleTemplateChange() {
    var sel = document.getElementById('templateSelect');
    var editor = document.getElementById('codeEditor');
    if (sel && editor && ALGO_TEMPLATES[sel.value]) {
        editor.value = ALGO_TEMPLATES[sel.value];
        syncHighlight();
    }
}

// 恢复模板
function handleResetTemplate() {
    handleTemplateChange();
    showSuccessToast('模板已恢复');
}

// 放大/缩小代码编辑器
var _codeExpanded = false;
function handleToggleCodeExpand() {
    var wrapper = document.getElementById('codeEditorWrapper');
    var overlay = document.getElementById('codeFullscreenOverlay');
    var btn = document.getElementById('expandCodeBtn');
    var editor = document.getElementById('codeEditor');
    if (!wrapper || !overlay) return;

    _codeExpanded = !_codeExpanded;
    if (_codeExpanded) {
        wrapper.classList.add('fullscreen');
        overlay.classList.add('active');
        btn.textContent = '⛶ 缩小';
        editor.focus();
    } else {
        wrapper.classList.remove('fullscreen');
        overlay.classList.remove('active');
        btn.textContent = '⛶ 放大';
    }
}

// ESC键退出全屏
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && _codeExpanded) {
        handleToggleCodeExpand();
    }
});

// ==================== Python 语法高亮 ====================
function highlightPython(code) {
    // 先转义HTML
    var html = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

    // 1. 多行字符串 ("""...""" 和 '''...''')
    html = html.replace(/("""[\s\S]*?"""|'''[\s\S]*?''')/g, '<span class="py-string">$1</span>');

    // 2. 注释
    html = html.replace(/(#[^\n]*)/g, '<span class="py-comment">$1</span>');

    // 3. 装饰器
    html = html.replace(/(@\w+)/g, '<span class="py-decorator">$1</span>');

    // 4. f-string 和普通字符串
    html = html.replace(/(f?'[^'\n]*'|f?"[^"\n]*")/g, function(m) {
        if (m.startsWith('f')) {
            return '<span class="py-string">' + m + '</span>';
        }
        return '<span class="py-string">' + m + '</span>';
    });

    // 5. 关键字
    var keywords = ['import', 'from', 'as', 'def', 'class', 'return', 'if', 'elif', 'else',
        'for', 'while', 'in', 'not', 'and', 'or', 'is', 'with', 'try', 'except',
        'finally', 'raise', 'pass', 'break', 'continue', 'yield', 'lambda',
        'global', 'nonlocal', 'assert', 'del', 'True', 'False', 'None'];
    keywords.forEach(function(kw) {
        var re = new RegExp('\\b(' + kw + ')\\b', 'g');
        html = html.replace(re, function(match, p1, offset, str) {
            // 不替换已在span标签内的
            var before = str.substring(Math.max(0, offset - 30), offset);
            if (before.match(/<span[^>]*>[^<]*$/)) return match;
            return '<span class="py-keyword">' + p1 + '</span>';
        });
    });

    // 6. 内置函数
    var builtins = ['print', 'len', 'range', 'int', 'float', 'str', 'list', 'dict',
        'tuple', 'set', 'type', 'isinstance', 'enumerate', 'zip', 'map',
        'filter', 'sorted', 'reversed', 'abs', 'max', 'min', 'sum',
        'round', 'open', 'input', 'super', 'property', 'staticmethod',
        'classmethod', 'hasattr', 'getattr', 'setattr'];
    builtins.forEach(function(bi) {
        var re = new RegExp('\\b(' + bi + ')(\\s*\\()', 'g');
        html = html.replace(re, function(match, p1, p2, offset, str) {
            var before = str.substring(Math.max(0, offset - 30), offset);
            if (before.match(/<span[^>]*>[^<]*$/)) return match;
            return '<span class="py-builtin">' + p1 + '</span>' + p2;
        });
    });

    // 7. 数字
    html = html.replace(/\b(\d+\.?\d*(?:e[+-]?\d+)?)\b/gi, function(match, p1, offset, str) {
        var before = str.substring(Math.max(0, offset - 30), offset);
        if (before.match(/<span[^>]*>[^<]*$/)) return match;
        return '<span class="py-number">' + p1 + '</span>';
    });

    // 8. self
    html = html.replace(/\b(self)\b/g, function(match, p1, offset, str) {
        var before = str.substring(Math.max(0, offset - 30), offset);
        if (before.match(/<span[^>]*>[^<]*$/)) return match;
        return '<span class="py-self">' + p1 + '</span>';
    });

    // 9. 函数定义名
    html = html.replace(/(def\s+)(\w+)/g, function(match, p1, p2, offset, str) {
        return p1 + '<span class="py-func">' + p2 + '</span>';
    });

    // 10. 类定义名
    html = html.replace(/(class\s+)(\w+)/g, function(match, p1, p2) {
        return p1 + '<span class="py-class">' + p2 + '</span>';
    });

    return html;
}

// 同步高亮渲染
function syncHighlight() {
    var editor = document.getElementById('codeEditor');
    var highlight = document.getElementById('codeHighlightCode');
    if (!editor || !highlight) return;
    highlight.innerHTML = highlightPython(editor.value) + '\n';
}

// 同步滚动
function syncScroll() {
    var editor = document.getElementById('codeEditor');
    var highlight = document.getElementById('codeHighlight');
    if (!editor || !highlight) return;
    highlight.scrollTop = editor.scrollTop;
    highlight.scrollLeft = editor.scrollLeft;
}

// 绑定编辑器事件
document.addEventListener('DOMContentLoaded', function() {
    var editor = document.getElementById('codeEditor');
    if (editor) {
        editor.addEventListener('input', syncHighlight);
        editor.addEventListener('scroll', syncScroll);
        // 初始高亮
        setTimeout(syncHighlight, 100);
    }
});

// 运行自定义算法
function handleRunCustomAlgorithm() {
    var editor = document.getElementById('codeEditor');
    var statusEl = document.getElementById('customAlgoStatus');
    if (!editor || !editor.value.trim()) {
        statusEl.textContent = '代码不能为空';
        statusEl.style.color = '#dc3545';
        return;
    }

    statusEl.textContent = '正在提交代码...';
    statusEl.style.color = '#2C5AA0';
    var btn = document.getElementById('runCustomBtn');
    if (btn) btn.disabled = true;

    fetch('/api/prediction/run-custom-algorithm', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: editor.value})
    })
    .then(function(resp) { return resp.json(); })
    .then(function(result) {
        if (result.success && result.async) {
            statusEl.textContent = '算法运行中（服务器后台运行中）...';
            statusEl.style.color = '#e67e22';
            pollCustomAlgoDone();
        } else if (result.success) {
            statusEl.textContent = '运行完成';
            statusEl.style.color = '#28a745';
            if (btn) btn.disabled = false;
            loadCustomResults();
        } else {
            statusEl.textContent = '失败: ' + result.message;
            statusEl.style.color = '#dc3545';
            if (btn) btn.disabled = false;
        }
    })
    .catch(function() {
        statusEl.textContent = '后端服务未响应';
        statusEl.style.color = '#dc3545';
        if (btn) btn.disabled = false;
    });
}

// 轮询自定义算法状态
function pollCustomAlgoDone() {
    var statusEl = document.getElementById('customAlgoStatus');
    var btn = document.getElementById('runCustomBtn');
    var interval = setInterval(function() {
        fetch('/api/prediction/status')
            .then(function(resp) { return resp.json(); })
            .then(function(status) {
                if (!status.running) {
                    clearInterval(interval);
                    if (btn) btn.disabled = false;
                    if (status.success) {
                        statusEl.textContent = '自定义算法运行完成！';
                        statusEl.style.color = '#28a745';
                        showSuccessToast('自定义算法运行完成！');
                        loadCustomResults();
                    } else {
                        statusEl.textContent = '运行失败: ' + status.message;
                        statusEl.style.color = '#dc3545';
                    }
                }
            })
            .catch(function() {});
    }, 2000);
}

// 加载自定义算法结果并展示
function loadCustomResults() {
    fetch('/api/prediction/get-custom-results')
        .then(function(resp) { return resp.json(); })
        .then(function(result) {
            if (result.success && result.data) {
                var d = result.data;
                var resultDisplay = document.getElementById('resultDisplay');
                var chartsPath = '/api/prediction/charts/';
                var ts = Date.now();
                resultDisplay.innerHTML =
                    '<div style="padding: 15px;">' +
                    '<h4 style="color: #e67e22; margin-bottom: 15px;">🧪 自定义算法实验结果</h4>' +
                    '<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 15px;">' +
                    '<div style="background: #fff3e0; padding: 12px; border-radius: 6px; text-align: center;">' +
                    '<div style="font-size: 12px; color: #e65100;">算法</div>' +
                    '<div style="font-size: 16px; font-weight: bold; color: #e67e22;">' + (d.algorithm || '--') + '</div></div>' +
                    '<div style="background: #e8f5e9; padding: 12px; border-radius: 6px; text-align: center;">' +
                    '<div style="font-size: 12px; color: #2e7d32;">R²</div>' +
                    '<div style="font-size: 20px; font-weight: bold; color: #28a745;">' + (d.r2 || '--') + '</div></div>' +
                    '<div style="background: #e3f2fd; padding: 12px; border-radius: 6px; text-align: center;">' +
                    '<div style="font-size: 12px; color: #1565c0;">RMSE</div>' +
                    '<div style="font-size: 20px; font-weight: bold; color: #2C5AA0;">' + (d.rmse || '--') + '</div></div>' +
                    '</div>' +
                    '<div style="font-size: 13px; color: #666; margin-bottom: 10px;">参数: ' + (d.params || '--') + ' | MAE: ' + (d.mae || '--') + ' | 耗时: ' + (d.time || '--') + 's</div>' +
                    '<div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; background: #fafafa;">' +
                    '<h5 style="color: #333; margin-bottom: 10px;">📊 预测结果对比图</h5>' +
                    '<img src="' + chartsPath + 'custom_result.jpg?t=' + ts + '" style="width: 100%; max-width: 800px; border-radius: 4px; cursor: pointer;" onclick="window.open(this.src, \'_blank\')" ' +
                    'onerror="this.src=\'data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22600%22 height=%22300%22><rect fill=%22%23f0f0f0%22 width=%22600%22 height=%22300%22/><text x=%2250%%22 y=%2250%%22 text-anchor=%22middle%22 fill=%22%23999%22>图片生成中...</text></svg>\'">' +
                    '</div></div>';
            }
        })
        .catch(function() {});
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
