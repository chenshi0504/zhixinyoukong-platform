// 基于虚实结合仿真的算法测试功能教学模块
class AlgorithmTestingSystem {
    constructor() {
        this.isTesting = false;
        this.testTimer = null;
        this.testStartTime = null;
        this.testDuration = 0;
        this.simulatorTools = {};
        this.uploadedSimulatorFiles = [];
        this.selectedSimulatorFile = null;
        this.currentUploadId = null;
        this.currentConfig = {
            algorithm: 'baseline',
            scenario: 'urban',
            parameters: {
                searchRadius: 100,
                optimizationLevel: 3,
                convergenceThreshold: 0.01
            },
            dataSources: {
                topology: false,
                traffic: false,
                od: false
            }
        };
        
        this.algorithmData = {
            baseline: {
                name: 'Dijkstra最短路径算法',
                description: '经典的单源最短路径算法，通过逐步扩展最短路径树来找到从起点到所有其他节点的最短路径。适用于静态路网环境下的路径规划。',
                features: [
                    '时间复杂度：O((V+E)logV)',
                    '空间复杂度：O(V)',
                    '适用场景：静态路网、确定性权重'
                ],
                performance: { efficiency: 78, length: 12.5, time: 24 }
            },
            optimization: {
                name: 'A*启发式搜索算法',
                description: '基于启发式函数的最短路径算法，通过估计函数指导搜索方向，能够更快地找到最优路径。适用于大规模路网的高效路径规划。',
                features: [
                    '时间复杂度：O(b^d)，实际性能更优',
                    '空间复杂度：O(b^d)',
                    '适用场景：大规模路网、实时路径规划'
                ],
                performance: { efficiency: 42, length: 10.2, time: 18 }
            },
            advanced: {
                name: '动态时间依赖路径规划算法',
                description: '考虑时间变化因素的高级路径规划算法，能够根据交通流量的时间变化动态调整路径选择，适用于复杂的城市交通环境。',
                features: [
                    '时间复杂度：O(n²logn)',
                    '空间复杂度：O(n²)',
                    '适用场景：动态交通、时变路网'
                ],
                performance: { efficiency: 35, length: 9.8, time: 15 }
            },
            custom: {
                name: '自定义算法',
                description: '用户自定义的路径规划算法，可以根据特定需求和场景进行定制化开发和测试。',
                features: [
                    '复杂度：取决于具体实现',
                    '适用场景：特定需求场景',
                    '可扩展性：高度可定制'
                ],
                performance: { efficiency: 50, length: 11.0, time: 20 }
            }
        };
        
        this.init();
    }

    // 初始化系统
    init() {
        this.bindEvents();
        this.updateAlgorithmInfo();
        this.updatePerformanceDisplay();
        this.updateResultsSummary();
        this.refreshSimulatorStatus();
    }

    // 绑定事件监听器
    bindEvents() {
        // 算法选择事件
        document.getElementById('algorithm-type').addEventListener('change', this.handleAlgorithmChange.bind(this));
        document.getElementById('test-scenario').addEventListener('change', this.handleScenarioChange.bind(this));
        
        // 参数配置事件
        document.getElementById('search-radius').addEventListener('input', this.handleParameterChange.bind(this));
        document.getElementById('optimization-level').addEventListener('input', this.handleOptimizationLevelChange.bind(this));
        document.getElementById('convergence-threshold').addEventListener('input', this.handleParameterChange.bind(this));
        
        // 控制按钮事件
        document.getElementById('start-test').addEventListener('click', this.toggleTest.bind(this));
        document.getElementById('analysis-results-btn').addEventListener('click', this.analyzeResults.bind(this));
        document.getElementById('download-report-btn').addEventListener('click', this.downloadReport.bind(this));
        document.getElementById('reset-config').addEventListener('click', this.resetConfiguration.bind(this));

        const chooseFilesBtn = document.getElementById('choose-simulator-files');
        const uploadFilesBtn = document.getElementById('upload-simulator-files');
        const fileInput = document.getElementById('simulator-file-input');
        const refreshBtn = document.getElementById('refresh-simulator-status');
        const launchSumoBtn = document.getElementById('launch-sumo-gui');
        const launchNeteditBtn = document.getElementById('launch-netedit');
        const launchCarlaBtn = document.getElementById('launch-carla');

        if (chooseFilesBtn && fileInput) {
            chooseFilesBtn.addEventListener('click', () => fileInput.click());
            fileInput.addEventListener('change', this.handleSimulatorFileSelection.bind(this));
        }
        if (uploadFilesBtn) uploadFilesBtn.addEventListener('click', this.uploadSimulatorFiles.bind(this));
        if (refreshBtn) refreshBtn.addEventListener('click', this.refreshSimulatorStatus.bind(this));
        if (launchSumoBtn) launchSumoBtn.addEventListener('click', () => this.launchSimulatorTool('sumo-gui'));
        if (launchNeteditBtn) launchNeteditBtn.addEventListener('click', () => this.launchSimulatorTool('netedit'));
        if (launchCarlaBtn) launchCarlaBtn.addEventListener('click', () => this.launchSimulatorTool('carla'));
    }

    // 处理算法选择变化
    handleAlgorithmChange(event) {
        this.currentConfig.algorithm = event.target.value;
        this.updateAlgorithmInfo();
        this.updatePerformanceDisplay();
        this.updateResultsSummary();
    }

    // 处理测试场景变化
    handleScenarioChange(event) {
        this.currentConfig.scenario = event.target.value;
        this.updateResultsSummary();
    }

    // 处理参数变化
    handleParameterChange(event) {
        const paramName = event.target.id.replace('-', '');
        const value = parseFloat(event.target.value);
        
        if (paramName === 'searchradius') {
            this.currentConfig.parameters.searchRadius = value;
        } else if (paramName === 'convergencethreshold') {
            this.currentConfig.parameters.convergenceThreshold = value;
        }
    }

    // 处理优化等级变化
    handleOptimizationLevelChange(event) {
        const level = parseInt(event.target.value);
        this.currentConfig.parameters.optimizationLevel = level;
        document.getElementById('optimization-value').textContent = level;
    }

    // 更新算法信息显示
    updateAlgorithmInfo() {
        const algorithm = this.algorithmData[this.currentConfig.algorithm];
        const infoContainer = document.getElementById('algorithm-info');
        
        infoContainer.innerHTML = `
            <h4>${algorithm.name}</h4>
            <p>${algorithm.description}</p>
            <ul>
                ${algorithm.features.map(feature => `<li>${feature}</li>`).join('')}
            </ul>
        `;
    }

    // 更新性能显示
    updatePerformanceDisplay() {
        const baselinePerf = this.algorithmData.baseline.performance;
        const currentPerf = this.algorithmData[this.currentConfig.algorithm].performance;
        
        // 更新效率对比
        document.getElementById('baseline-efficiency').textContent = baselinePerf.efficiency;
        document.getElementById('current-efficiency').textContent = currentPerf.efficiency;
        const efficiencyImprovement = ((baselinePerf.efficiency - currentPerf.efficiency) / baselinePerf.efficiency * 100).toFixed(0);
        document.getElementById('efficiency-improvement').textContent = `+${efficiencyImprovement}% 提升`;
        
        // 更新路径长度对比
        document.getElementById('baseline-length').textContent = baselinePerf.length;
        document.getElementById('current-length').textContent = currentPerf.length;
        const lengthImprovement = ((baselinePerf.length - currentPerf.length) / baselinePerf.length * 100).toFixed(0);
        document.getElementById('length-improvement').textContent = `-${lengthImprovement}% 优化`;
        
        // 更新通行时间对比
        document.getElementById('baseline-time').textContent = baselinePerf.time;
        document.getElementById('current-time').textContent = currentPerf.time;
        const timeImprovement = ((baselinePerf.time - currentPerf.time) / baselinePerf.time * 100).toFixed(0);
        document.getElementById('time-improvement').textContent = `-${timeImprovement}% 优化`;
    }

    // 更新结果汇总
    updateResultsSummary() {
        const scenarioNames = {
            urban: '城市路网场景',
            highway: '高速公路场景',
            intersection: '交叉口场景',
            mixed: '混合交通场景'
        };
        
        document.getElementById('result-scenario').textContent = scenarioNames[this.currentConfig.scenario];
        document.getElementById('result-algorithm').textContent = this.algorithmData[this.currentConfig.algorithm].name;
        document.getElementById('result-duration').textContent = `${this.testDuration} 秒`;
        
        // 计算综合评分
        const currentPerf = this.algorithmData[this.currentConfig.algorithm].performance;
        const score = Math.round((100 - currentPerf.efficiency/2) + (15 - currentPerf.length) * 2 + (30 - currentPerf.time));
        document.getElementById('result-score').textContent = `${score}分`;
        
        // 更新评分样式
        const scoreElement = document.getElementById('result-score');
        scoreElement.className = 'result-value';
        if (score >= 85) {
            scoreElement.classList.add('score-excellent');
        } else if (score >= 70) {
            scoreElement.classList.add('score-good');
        } else {
            scoreElement.classList.add('score-poor');
        }
    }

    // 切换测试状态
    toggleTest() {
        this.startTest();
    }

    // 更新服务器仿真工具状态
    async refreshSimulatorStatus() {
        const refreshBtn = document.getElementById('refresh-simulator-status');
        const originalText = refreshBtn ? refreshBtn.textContent : '';
        if (refreshBtn) {
            refreshBtn.textContent = '检测中...';
            refreshBtn.disabled = true;
        }

        try {
            const response = await fetch('/api/v1/simulators/status', {
                method: 'GET',
                signal: AbortSignal.timeout(5000)
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.detail || result.message || '检测失败');
            }
            this.simulatorTools = result.tools || {};
            this.renderSimulatorToolStatus();
            this.updateSimulatorLaunchButtons();
        } catch (error) {
            ['sumo-gui', 'netedit', 'carla'].forEach(tool => this.setToolStatus(tool, '检测失败', 'status-pending'));
            this.showMessage(`服务器仿真环境检测失败: ${error.message}`, 'warning');
        } finally {
            if (refreshBtn) {
                refreshBtn.textContent = originalText || '检测服务器环境';
                refreshBtn.disabled = false;
            }
        }
    }

    renderSimulatorToolStatus() {
        ['sumo-gui', 'netedit', 'carla'].forEach(tool => {
            const item = this.simulatorTools[tool];
            if (!item || !item.installed) {
                this.setToolStatus(tool, '未安装', 'status-pending');
            } else if (item.running) {
                this.setToolStatus(tool, '运行中', 'status-selected');
            } else {
                this.setToolStatus(tool, '已安装', 'status-loading');
            }
        });
    }

    setToolStatus(tool, text, className) {
        const row = document.querySelector(`[data-tool-status="${tool}"]`);
        if (!row) return;
        const state = row.querySelector('.tool-state');
        if (!state) return;
        state.textContent = text;
        state.className = `tool-state ${className}`;
        const toolInfo = this.simulatorTools[tool];
        if (toolInfo && toolInfo.executable_path) {
            state.title = toolInfo.executable_path;
        }
    }

    handleSimulatorFileSelection(event) {
        const files = Array.from(event.target.files || []);
        const status = document.getElementById('simulator-upload-status');
        const uploadBtn = document.getElementById('upload-simulator-files');
        if (!files.length) {
            if (status) status.textContent = '尚未选择文件';
            if (uploadBtn) uploadBtn.disabled = true;
            return;
        }
        if (status) status.textContent = `已选择 ${files.length} 个文件，等待上传`;
        if (uploadBtn) uploadBtn.disabled = false;
    }

    async uploadSimulatorFiles() {
        const input = document.getElementById('simulator-file-input');
        const uploadBtn = document.getElementById('upload-simulator-files');
        const status = document.getElementById('simulator-upload-status');
        const files = input ? Array.from(input.files || []) : [];
        if (!files.length) {
            this.showMessage('请先选择仿真文件', 'warning');
            return;
        }

        const originalText = uploadBtn ? uploadBtn.textContent : '';
        if (uploadBtn) {
            uploadBtn.textContent = '上传中...';
            uploadBtn.disabled = true;
        }
        if (status) status.textContent = '正在上传到服务器...';

        const formData = new FormData();
        files.forEach(file => formData.append('files', file));

        try {
            const response = await fetch('/api/v1/simulators/uploads', {
                method: 'POST',
                body: formData
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                const detail = typeof result.detail === 'string' ? result.detail : (result.detail && result.detail.message);
                throw new Error(detail || result.message || '上传失败');
            }

            this.currentUploadId = result.upload_id;
            this.uploadedSimulatorFiles = result.files || [];
            this.selectedSimulatorFile = this.pickDefaultSimulatorFile(this.uploadedSimulatorFiles);
            this.renderUploadedSimulatorFiles();
            this.updateActiveSimulatorConfig();
            this.updateSimulatorLaunchButtons();
            if (status) status.textContent = `已上传 ${this.uploadedSimulatorFiles.length} 个服务器文件`;

            const rejected = result.rejected && result.rejected.length ? `，${result.rejected.length} 个文件被跳过` : '';
            this.showMessage(`仿真文件上传成功${rejected}`, 'success');
        } catch (error) {
            if (status) status.textContent = '上传失败';
            this.showMessage(`上传失败: ${error.message}`, 'error');
        } finally {
            if (uploadBtn) {
                uploadBtn.textContent = originalText || '上传到服务器';
                uploadBtn.disabled = false;
            }
        }
    }

    pickDefaultSimulatorFile(files) {
        return files.find(file => file.filename.toLowerCase().endsWith('.sumocfg'))
            || files.find(file => file.filename.toLowerCase().endsWith('.net.xml'))
            || files.find(file => file.launchable_with && file.launchable_with.length)
            || files[0]
            || null;
    }

    renderUploadedSimulatorFiles() {
        const list = document.getElementById('uploaded-simulator-files');
        if (!list) return;
        if (!this.uploadedSimulatorFiles.length) {
            list.innerHTML = '<div class="empty-upload-state">支持 .sumocfg、.net.xml、.rou.xml、.xodr、.json、.zip 等文件。</div>';
            return;
        }

        list.innerHTML = this.uploadedSimulatorFiles.map((file, index) => {
            const checked = this.selectedSimulatorFile && this.selectedSimulatorFile.file_id === file.file_id ? 'checked' : '';
            return `
                <label class="uploaded-file-item">
                    <input type="radio" name="uploaded-simulator-file" value="${index}" ${checked}>
                    <span class="uploaded-file-main">
                        <span class="uploaded-file-name" title="${this.escapeHtml(file.filename)}">${this.escapeHtml(file.filename)}</span>
                        <span class="uploaded-file-meta">${this.formatFileSize(file.size)} · ${this.escapeHtml(file.relative_path || file.file_id)}</span>
                    </span>
                    <span class="file-role-tag">${this.fileRoleText(file.role)}</span>
                </label>
            `;
        }).join('');

        list.querySelectorAll('input[name="uploaded-simulator-file"]').forEach(input => {
            input.addEventListener('change', (event) => {
                const index = Number(event.target.value);
                this.selectedSimulatorFile = this.uploadedSimulatorFiles[index] || null;
                this.updateActiveSimulatorConfig();
                this.updateSimulatorLaunchButtons();
            });
        });
    }

    updateActiveSimulatorConfig() {
        const active = document.getElementById('active-sim-config');
        if (!active) return;
        if (this.selectedSimulatorFile) {
            active.textContent = `自定义 ${this.selectedSimulatorFile.filename}`;
            active.title = this.selectedSimulatorFile.server_path || '';
        } else {
            active.textContent = '内置 siouxfalls_2.5.sumocfg';
            active.title = '';
        }
    }

    updateSimulatorLaunchButtons() {
        const hasTool = (tool) => Boolean(this.simulatorTools[tool] && this.simulatorTools[tool].installed);
        const selected = this.selectedSimulatorFile;
        const selectedName = selected ? selected.filename.toLowerCase() : '';

        const sumoBtn = document.getElementById('launch-sumo-gui');
        const neteditBtn = document.getElementById('launch-netedit');
        const carlaBtn = document.getElementById('launch-carla');
        if (sumoBtn) sumoBtn.disabled = !(hasTool('sumo-gui') && selectedName.endsWith('.sumocfg'));
        if (neteditBtn) neteditBtn.disabled = !(hasTool('netedit') && selected && (
            selectedName.endsWith('.net.xml') || selectedName.endsWith('.sumocfg') || selectedName.endsWith('.netccfg') || selectedName.endsWith('.xml') || selectedName.endsWith('.osm')
        ));
        if (carlaBtn) carlaBtn.disabled = !hasTool('carla');
    }

    launchPayloadForSelectedFile(tool) {
        const payload = {};
        if (this.currentUploadId && this.selectedSimulatorFile && tool !== 'carla') {
            payload.upload_id = this.currentUploadId;
            payload.file_id = this.selectedSimulatorFile.file_id;
        }
        return payload;
    }

    async launchSimulatorTool(tool) {
        const buttonMap = {
            'sumo-gui': 'launch-sumo-gui',
            'netedit': 'launch-netedit',
            'carla': 'launch-carla'
        };
        const button = document.getElementById(buttonMap[tool]);
        const originalText = button ? button.textContent : '';
        if (button) {
            button.disabled = true;
            button.textContent = '启动中...';
        }

        try {
            const response = await fetch(`/api/v1/simulators/${tool}/launch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.launchPayloadForSelectedFile(tool))
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.detail || result.message || '启动失败');
            }
            const statusText = document.getElementById('sumo-status-text');
            if (statusText && tool === 'sumo-gui') {
                statusText.textContent = this.selectedSimulatorFile
                    ? `服务器已用 ${this.selectedSimulatorFile.filename} 启动 SUMO-GUI`
                    : '服务器已启动 SUMO-GUI';
                statusText.style.color = '#28A745';
            }
            this.showMessage(result.message || '已向服务器发送启动命令', 'success');
            await this.refreshSimulatorStatus();
            return true;
        } catch (error) {
            this.showMessage(`启动失败: ${error.message}`, 'error');
            return false;
        } finally {
            if (button) {
                button.textContent = originalText;
            }
            this.updateSimulatorLaunchButtons();
        }
    }

    // 开始测试
    async startTest() {
        if (this.isTesting) {
            this.showMessage('仿真正在运行，请等待当前操作完成', 'warning');
            return;
        }
        this.isTesting = true;
        this.testStartTime = Date.now();

        // 显示SUMO仿真界面图片
        this.showSimulationImage();
        
        // 更新按钮状态
        const startBtn = document.getElementById('start-test');
        startBtn.textContent = '检查中...';
        startBtn.disabled = true;
        
        // 更新状态显示
        document.getElementById('test-status-value').textContent = '正在检查后端服务...';
        document.getElementById('test-status-value').style.color = '#FFC107';
        
        try {
            // 检查后端服务是否已启动
            let backendRunning = false;
            try {
                const healthCheck = await fetch('/api/simulation/health', {
                    method: 'GET',
                    signal: AbortSignal.timeout(3000) // 3秒超时
                });
                backendRunning = healthCheck.ok;
            } catch (e) {
                backendRunning = false;
            }
            
            // 如果服务器仿真服务不可用，给出远程用户可理解的状态反馈
            if (!backendRunning) {
                // 恢复按钮状态
                startBtn.textContent = '开始测试';
                startBtn.disabled = false;
                this.isTesting = false;
                
                // 更新状态显示
                document.getElementById('test-status-value').textContent = '服务不可用';
                document.getElementById('test-status-value').style.color = '#DC3545';
                
                this.showMessage('服务器后端服务暂不可用，请检查服务器运行状态', 'warning');
                
                return;
            }
            
            // 后端已启动，继续启动SUMO仿真
            this.showMessage('后端服务已就绪，正在启动服务器端 SUMO 仿真...', 'success');
            document.getElementById('test-status-value').textContent = '正在启动SUMO仿真...';

            if (this.selectedSimulatorFile && this.selectedSimulatorFile.filename.toLowerCase().endsWith('.sumocfg')) {
                const launched = await this.launchSimulatorTool('sumo-gui');
                if (!launched) {
                    document.getElementById('test-status-value').textContent = '启动失败';
                    document.getElementById('test-status-value').style.color = '#DC3545';
                    startBtn.textContent = '开始测试';
                    startBtn.disabled = false;
                    this.isTesting = false;
                    return;
                }
                document.getElementById('test-status-value').textContent = '已用自定义配置启动';
                document.getElementById('test-status-value').style.color = '#28A745';
                startBtn.textContent = '开始测试';
                startBtn.disabled = false;
                this.isTesting = false;
                return;
            }
            
            const response = await fetch('/api/simulation/start_simulation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    algorithm: this.currentConfig.algorithm,
                    scenario: this.currentConfig.scenario,
                    parameters: this.currentConfig.parameters,
                    simulatorFile: this.selectedSimulatorFile,
                    uploadId: this.currentUploadId
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.isTesting = false;
                this.testDuration = Math.floor((Date.now() - this.testStartTime) / 1000);
                this.updateResultsSummary();
                // 更新状态显示
                document.getElementById('test-status-value').textContent = 'SUMO已启动';
                document.getElementById('test-status-value').style.color = '#28A745';
                
                // 更新SUMO状态显示
                const sumoStatusText = document.getElementById('sumo-status-text');
                if (sumoStatusText) {
                    sumoStatusText.textContent = 'SUMO GUI已启动';
                    sumoStatusText.style.color = '#28A745';
                }
                
                // 恢复按钮状态
                startBtn.textContent = '开始测试';
                startBtn.disabled = false;
                this.isTesting = false;
                
                this.showMessage('SUMO仿真已启动，可随时点击"仿真结果"按钮查看分析', 'success');
            } else {
                throw new Error(result.message || '启动SUMO失败');
            }
        } catch (error) {
            console.error('启动仿真失败:', error);
            
            // 恢复按钮状态
            startBtn.textContent = '开始测试';
            startBtn.disabled = false;
            this.isTesting = false;
            
            // 更新状态显示
            document.getElementById('test-status-value').textContent = '启动失败';
            document.getElementById('test-status-value').style.color = '#DC3545';
            
            // 显示详细错误信息
            let errorMessage = '启动仿真失败';
            if (error.message) {
                errorMessage += `: ${error.message}`;
            }
            
            this.showMessage(errorMessage, 'error');
        }
    }
    
    // 显示服务器服务检查说明
    showManualStartupGuide() {
        const guideDiv = document.createElement('div');
        guideDiv.className = 'startup-guide-modal';
        guideDiv.innerHTML = `
            <div class="guide-content">
                <div class="guide-header">
                    <span class="guide-icon">⚠️</span>
                    <h3>服务器服务暂不可用</h3>
                </div>
                <div class="guide-body">
                    <p class="guide-intro">请检查服务器上的主平台服务和 SUMO 仿真子服务运行状态。</p>
                    <ol class="guide-steps">
                        <li>
                            <strong>检查服务状态</strong>
                            <p>访问 /api/simulation/health 确认仿真服务是否可用。</p>
                        </li>
                        <li>
                            <strong>检查服务日志</strong>
                            <p>查看 backend/logs 下的服务日志。</p>
                        </li>
                        <li>
                            <strong>重新启动平台服务</strong>
                            <p><code>Web\\启动本地平台Web访问.bat</code></p>
                        </li>
                        <li>
                            <strong>等待服务启动</strong>
                            <p>看到 "服务已启动" 提示后即可</p>
                        </li>
                        <li>
                            <strong>返回页面测试</strong>
                            <p>再次点击"开始测试"按钮</p>
                        </li>
                    </ol>
                </div>
                <div class="guide-footer">
                    <button onclick="this.closest('.startup-guide-modal').remove(); document.querySelector('.startup-guide-overlay').remove();" class="btn btn-primary">知道了</button>
                </div>
            </div>
        `;
        
        // 添加样式
        const style = document.createElement('style');
        style.textContent = `
            .startup-guide-modal {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                z-index: 2000;
                max-width: 600px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
            }
            
            .guide-content {
                padding: 0;
            }
            
            .guide-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 24px;
                border-radius: 12px 12px 0 0;
                display: flex;
                align-items: center;
                gap: 12px;
            }
            
            .guide-icon {
                font-size: 32px;
            }
            
            .guide-header h3 {
                margin: 0;
                font-size: 20px;
                font-weight: 600;
            }
            
            .guide-body {
                padding: 24px;
            }
            
            .guide-intro {
                margin: 0 0 16px 0;
                color: #666;
                font-size: 14px;
            }
            
            .guide-steps {
                margin: 0;
                padding-left: 20px;
                list-style: none;
                counter-reset: step-counter;
            }
            
            .guide-steps li {
                counter-increment: step-counter;
                margin-bottom: 20px;
                position: relative;
                padding-left: 40px;
            }
            
            .guide-steps li::before {
                content: counter(step-counter);
                position: absolute;
                left: 0;
                top: 0;
                width: 28px;
                height: 28px;
                background: #667eea;
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 600;
                font-size: 14px;
            }
            
            .guide-steps li strong {
                display: block;
                margin-bottom: 4px;
                color: #333;
                font-size: 15px;
            }
            
            .guide-steps li p {
                margin: 0;
                color: #666;
                font-size: 13px;
                line-height: 1.5;
            }
            
            .guide-steps li code {
                background: #f5f5f5;
                padding: 2px 8px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                color: #e83e8c;
                font-size: 13px;
            }
            
            .guide-footer {
                padding: 16px 24px;
                border-top: 1px solid #eee;
                text-align: right;
            }
            
            .guide-footer .btn {
                padding: 10px 24px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s;
            }
            
            .guide-footer .btn-primary {
                background: #667eea;
                color: white;
            }
            
            .guide-footer .btn-primary:hover {
                background: #5568d3;
            }
            
            .startup-guide-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.6);
                z-index: 1999;
                backdrop-filter: blur(2px);
            }
        `;
        
        if (!document.getElementById('startup-guide-styles')) {
            style.id = 'startup-guide-styles';
            document.head.appendChild(style);
        }
        
        const overlay = document.createElement('div');
        overlay.className = 'startup-guide-overlay';
        overlay.onclick = () => {
            document.body.removeChild(overlay);
            document.body.removeChild(guideDiv);
        };
        
        document.body.appendChild(overlay);
        document.body.appendChild(guideDiv);
    }
    
    // 显示SUMO仿真界面图片
    showSimulationImage() {
        const placeholderContent = document.getElementById('placeholderContent');
        const sumoImage = document.getElementById('sumoSimulationImage');
        const viewport = document.querySelector('.simulation-viewport');
        
        if (placeholderContent && sumoImage && viewport) {
            // 隐藏占位符
            placeholderContent.style.display = 'none';
            
            // 显示SUMO仿真界面图片
            sumoImage.style.display = 'block';
            
            // 调整视口样式以适应图片
            viewport.classList.add('showing-image');
        }
    }
    
    // 隐藏SUMO仿真界面图片
    hideSimulationImage() {
        const placeholderContent = document.getElementById('placeholderContent');
        const sumoImage = document.getElementById('sumoSimulationImage');
        const viewport = document.querySelector('.simulation-viewport');
        
        if (placeholderContent && sumoImage && viewport) {
            // 显示占位符
            placeholderContent.style.display = 'block';
            
            // 隐藏SUMO仿真界面图片
            sumoImage.style.display = 'none';
            
            // 恢复视口样式
            viewport.classList.remove('showing-image');
        }
    }

    // 停止测试
    stopTest() {
        this.isTesting = false;
        
        // 清除定时器
        if (this.testTimer) {
            clearInterval(this.testTimer);
            this.testTimer = null;
        }
        
        // 更新按钮状态
        const startBtn = document.getElementById('start-test');
        startBtn.textContent = '开始测试';
        startBtn.className = 'btn btn-primary';
        
        // 更新状态显示
        document.getElementById('test-status-value').textContent = '已完成';
        document.getElementById('test-status-value').style.color = '#2C5AA0';
        
        // 启用配置输入
        this.setConfigInputsEnabled(true);
        
        // 计算测试时长
        this.testDuration = Math.floor((Date.now() - this.testStartTime) / 1000);
        this.updateResultsSummary();
        
        this.showMessage('算法测试已完成', 'success');
    }

    // 开始仿真监控
    startSimulationMonitoring() {
        if (!this.currentSessionId) return;
        
        this.testTimer = setInterval(async () => {
            try {
                const response = await fetch(`/api/simulation/status?session_id=${this.currentSessionId}`);
                const result = await response.json();
                
                if (result.success) {
                    const status = result.data.status;
                    
                    if (status === 'completed') {
                        // 仿真完成，显示分析结果按钮
                        this.onSimulationCompleted();
                    } else if (status === 'failed') {
                        this.showMessage('仿真执行失败', 'error');
                        this.stopTest();
                    }
                    
                    // 更新状态显示
                    const statusText = {
                        'running': '仿真运行中',
                        'completed': '仿真已完成',
                        'failed': '仿真失败',
                        'analyzing': '结果分析中'
                    };
                    
                    document.getElementById('test-status-value').textContent = statusText[status] || status;
                }
            } catch (error) {
                console.error('查询仿真状态失败:', error);
            }
        }, 2000); // 每2秒查询一次状态
    }
    
    // 仿真完成处理
    onSimulationCompleted() {
        if (this.testTimer) {
            clearInterval(this.testTimer);
            this.testTimer = null;
        }
        
        this.isTesting = false;
        
        // 更新按钮状态
        const startBtn = document.getElementById('start-test');
        startBtn.textContent = '开始测试';
        startBtn.className = 'btn btn-primary';
        
        // 按钮已静态存在，无需动态创建
        
        // 启用配置输入
        this.setConfigInputsEnabled(true);
        
        // 计算测试时长
        this.testDuration = Math.floor((Date.now() - this.testStartTime) / 1000);
        this.updateResultsSummary();
        
        // 更新SUMO状态显示
        const sumoStatusText = document.getElementById('sumo-status-text');
        if (sumoStatusText) {
            sumoStatusText.textContent = '仿真已完成';
            sumoStatusText.style.color = '#2C5AA0';
        }
        
        this.showMessage('仿真已完成，可以查看分析结果', 'success');
    }
    

    
    // 分析仿真结果
    async analyzeResults() {
        try {
            // 更新按钮状态
            const analysisBtn = document.getElementById('analysis-results-btn');
            const originalText = analysisBtn.textContent;
            analysisBtn.textContent = '加载中...';
            analysisBtn.disabled = true;
            
            this.showMessage('正在加载仿真结果...', 'info');
            
            // 先尝试从后端获取结果
            let hasBackendResults = false;
            try {
                const response = await fetch('/api/simulation/analyze_results', {
                    method: 'POST',
                    signal: AbortSignal.timeout(3000) // 3秒超时
                });
                
                const result = await response.json();
                
                if (result.success && result.data && result.data.has_results) {
                    this.displaySVGResults(result.data);
                    hasBackendResults = true;
                    
                    // 导出按钮始终可见，无需操作
                    
                    this.showMessage('分析完成，结果已显示', 'success');
                }
            } catch (error) {
                console.log('后端服务未响应，使用默认结果展示');
            }
            
            // 如果后端没有结果，显示默认的示例图表
            if (!hasBackendResults) {
                this.displayDefaultResults();
                this.showMessage('显示示例仿真结果', 'info');
            }
            
            // 恢复按钮状态
            analysisBtn.textContent = '刷新结果';
            analysisBtn.disabled = false;
            
        } catch (error) {
            console.error('分析失败:', error);
            
            // 即使出错也显示默认结果
            this.displayDefaultResults();
            
            const analysisBtn = document.getElementById('analysis-results-btn');
            analysisBtn.textContent = '仿真结果';
            analysisBtn.disabled = false;
        }
    }
    
    // 监控分析进度
    monitorAnalysisProgress() {
        const progressTimer = setInterval(async () => {
            try {
                const response = await fetch(`/api/simulation/status?session_id=${this.currentSessionId}`);
                const result = await response.json();
                
                if (result.success) {
                    const status = result.data.status;
                    
                    if (status === 'completed') {
                        // 分析完成，获取结果
                        clearInterval(progressTimer);
                        await this.displayResults();
                    } else if (status === 'failed') {
                        clearInterval(progressTimer);
                        this.showMessage('结果分析失败', 'error');
                        
                        const analysisBtn = document.getElementById('analysis-results-btn');
                        analysisBtn.textContent = '仿真结果';
                        analysisBtn.disabled = false;
                    }
                }
            } catch (error) {
                console.error('查询分析状态失败:', error);
            }
        }, 3000); // 每3秒查询一次
    }
    
    // 显示分析结果
    async displayResults() {
        try {
            const response = await fetch(`/api/simulation/results?session_id=${this.currentSessionId}`);
            const result = await response.json();
            
            if (result.success && result.data.has_results) {
                // 显示SVG图表
                this.displaySVGResults(result.data);
                
                // 更新按钮状态
                const analysisBtn = document.getElementById('analysis-results-btn');
                analysisBtn.textContent = '查看结果';
                analysisBtn.disabled = false;
                
                // 导出按钮始终可见，无需操作
                
                this.showMessage('分析结果已生成，可以导出报告', 'success');
            } else {
                this.showMessage('未找到分析结果', 'warning');
            }
        } catch (error) {
            console.error('获取分析结果失败:', error);
            this.showMessage('获取分析结果失败', 'error');
        }
    }
    
    // 显示SVG结果
    displaySVGResults(data) {
        const viewportElement = document.querySelector('.simulation-viewport .placeholder-content');
        
        if (viewportElement && (data.time_series_svg || data.trip_analysis_svg)) {
            // 创建结果显示容器
            const resultsContainer = document.createElement('div');
            resultsContainer.className = 'simulation-results';
            resultsContainer.innerHTML = `
                <div class="results-header">
                    <h4>仿真分析结果</h4>
                    <div class="results-tabs">
                        <button class="tab-btn active" onclick="showResultTab('time-series')">时间序列分析</button>
                        <button class="tab-btn" onclick="showResultTab('trip-analysis')">行程分析</button>
                    </div>
                </div>
                <div class="results-content">
                    <div id="time-series-result" class="result-tab active">
                        ${data.time_series_svg || '<p>时间序列分析图表未生成</p>'}
                    </div>
                    <div id="trip-analysis-result" class="result-tab">
                        ${data.trip_analysis_svg || '<p>行程分析图表未生成</p>'}
                    </div>
                </div>
            `;
            
            // 替换占位符内容
            viewportElement.innerHTML = '';
            viewportElement.appendChild(resultsContainer);
            
            // 添加样式
            this.addResultsStyles();
        }
    }
    
    // 显示默认示例结果 - 直接显示图片
    displayDefaultResults() {
        // 直接显示图片，不需要异步加载
        const timeSeriesContainer = document.getElementById('time-series-image-container');
        const tripAnalysisContainer = document.getElementById('trip-analysis-image-container');
        
        if (timeSeriesContainer) {
            timeSeriesContainer.innerHTML = '<img src="时间序列分析.svg" alt="时间序列分析" class="result-image">';
        }
        
        if (tripAnalysisContainer) {
            tripAnalysisContainer.innerHTML = '<img src="行程分析.svg" alt="行程分析" class="result-image">';
        }
        
        this.showMessage('仿真结果已显示', 'success');
    }
    
    // 生成时间序列图表
    generateTimeSeriesChart() {
        const algorithm = this.algorithmData[this.currentConfig.algorithm];
        const algorithmName = algorithm ? algorithm.name : '当前算法';
        
        return `
            <div class="chart-container">
                <h5>交通流量时间序列分析</h5>
                <svg viewBox="0 0 800 400" xmlns="http://www.w3.org/2000/svg">
                    <!-- 背景 -->
                    <rect width="800" height="400" fill="#f8f9fa"/>
                    
                    <!-- 网格线 -->
                    <g stroke="#e0e0e0" stroke-width="1">
                        ${Array.from({length: 5}, (_, i) => `<line x1="80" y1="${80 + i * 60}" x2="750" y2="${80 + i * 60}"/>`).join('')}
                        ${Array.from({length: 8}, (_, i) => `<line x1="${80 + i * 95}" y1="80" x2="${80 + i * 95}" y2="320"/>`).join('')}
                    </g>
                    
                    <!-- 坐标轴 -->
                    <line x1="80" y1="320" x2="750" y2="320" stroke="#333" stroke-width="2"/>
                    <line x1="80" y1="80" x2="80" y2="320" stroke="#333" stroke-width="2"/>
                    
                    <!-- Y轴标签 -->
                    <text x="40" y="85" font-size="12" fill="#666">100</text>
                    <text x="40" y="145" font-size="12" fill="#666">80</text>
                    <text x="40" y="205" font-size="12" fill="#666">60</text>
                    <text x="40" y="265" font-size="12" fill="#666">40</text>
                    <text x="40" y="325" font-size="12" fill="#666">20</text>
                    <text x="20" y="200" font-size="14" fill="#333" transform="rotate(-90 20 200)">流量 (辆/小时)</text>
                    
                    <!-- X轴标签 -->
                    ${Array.from({length: 8}, (_, i) => `<text x="${70 + i * 95}" y="345" font-size="12" fill="#666">${i * 3}:00</text>`).join('')}
                    <text x="400" y="375" font-size="14" fill="#333" text-anchor="middle">时间</text>
                    
                    <!-- 基线算法曲线 -->
                    <polyline points="80,200 175,180 270,160 365,140 460,170 555,190 650,210 745,220" 
                              fill="none" stroke="#dc3545" stroke-width="2" stroke-dasharray="5,5"/>
                    
                    <!-- 当前算法曲线 -->
                    <polyline points="80,220 175,200 270,170 365,150 460,160 555,170 650,180 745,185" 
                              fill="none" stroke="#28a745" stroke-width="3"/>
                    
                    <!-- 图例 -->
                    <rect x="600" y="30" width="140" height="50" fill="white" stroke="#ddd" rx="4"/>
                    <line x1="610" y1="45" x2="640" y2="45" stroke="#dc3545" stroke-width="2" stroke-dasharray="5,5"/>
                    <text x="650" y="50" font-size="12" fill="#666">基线算法</text>
                    <line x1="610" y1="65" x2="640" y2="65" stroke="#28a745" stroke-width="3"/>
                    <text x="650" y="70" font-size="12" fill="#666">${algorithmName}</text>
                    
                    <!-- 标题 -->
                    <text x="400" y="30" font-size="16" font-weight="bold" fill="#333" text-anchor="middle">
                        交通流量对比分析
                    </text>
                </svg>
                <div class="chart-description">
                    <p><strong>分析说明：</strong></p>
                    <ul>
                        <li>绿色实线表示${algorithmName}的交通流量变化</li>
                        <li>红色虚线表示基线算法的交通流量变化</li>
                        <li>当前算法在高峰时段（9:00-15:00）表现更优，流量分布更均衡</li>
                        <li>平均流量降低约15%，表明交通拥堵得到有效缓解</li>
                    </ul>
                </div>
            </div>
        `;
    }
    
    // 生成行程分析图表
    generateTripAnalysisChart() {
        const algorithm = this.algorithmData[this.currentConfig.algorithm];
        const perf = algorithm ? algorithm.performance : { time: 20, length: 11 };
        
        return `
            <div class="chart-container">
                <h5>行程时间与距离分析</h5>
                <svg viewBox="0 0 800 400" xmlns="http://www.w3.org/2000/svg">
                    <!-- 背景 -->
                    <rect width="800" height="400" fill="#f8f9fa"/>
                    
                    <!-- 标题 -->
                    <text x="400" y="30" font-size="16" font-weight="bold" fill="#333" text-anchor="middle">
                        行程性能对比
                    </text>
                    
                    <!-- 行程时间对比 -->
                    <g transform="translate(100, 80)">
                        <text x="0" y="0" font-size="14" font-weight="bold" fill="#333">平均行程时间 (分钟)</text>
                        
                        <!-- 基线算法 -->
                        <rect x="0" y="20" width="240" height="40" fill="#dc3545" rx="4"/>
                        <text x="250" y="45" font-size="14" fill="#333">24 分钟</text>
                        <text x="10" y="45" font-size="12" fill="white">基线算法</text>
                        
                        <!-- 当前算法 -->
                        <rect x="0" y="70" width="${perf.time * 10}" height="40" fill="#28a745" rx="4"/>
                        <text x="${perf.time * 10 + 10}" y="95" font-size="14" fill="#333">${perf.time} 分钟</text>
                        <text x="10" y="95" font-size="12" fill="white">当前算法</text>
                        
                        <!-- 改进百分比 -->
                        <text x="350" y="95" font-size="14" font-weight="bold" fill="#28a745">
                            ↓ ${Math.round((24 - perf.time) / 24 * 100)}% 优化
                        </text>
                    </g>
                    
                    <!-- 行程距离对比 -->
                    <g transform="translate(100, 240)">
                        <text x="0" y="0" font-size="14" font-weight="bold" fill="#333">平均行程距离 (公里)</text>
                        
                        <!-- 基线算法 -->
                        <rect x="0" y="20" width="250" height="40" fill="#dc3545" rx="4"/>
                        <text x="260" y="45" font-size="14" fill="#333">12.5 公里</text>
                        <text x="10" y="45" font-size="12" fill="white">基线算法</text>
                        
                        <!-- 当前算法 -->
                        <rect x="0" y="70" width="${perf.length * 20}" height="40" fill="#28a745" rx="4"/>
                        <text x="${perf.length * 20 + 10}" y="95" font-size="14" fill="#333">${perf.length} 公里</text>
                        <text x="10" y="95" font-size="12" fill="white">当前算法</text>
                        
                        <!-- 改进百分比 -->
                        <text x="350" y="95" font-size="14" font-weight="bold" fill="#28a745">
                            ↓ ${Math.round((12.5 - perf.length) / 12.5 * 100)}% 优化
                        </text>
                    </g>
                </svg>
                <div class="chart-description">
                    <p><strong>分析说明：</strong></p>
                    <ul>
                        <li>当前算法在行程时间上优化了${Math.round((24 - perf.time) / 24 * 100)}%</li>
                        <li>行程距离减少了${Math.round((12.5 - perf.length) / 12.5 * 100)}%，路径规划更优</li>
                        <li>综合性能提升显著，用户体验明显改善</li>
                    </ul>
                </div>
            </div>
        `;
    }
    
    // 生成性能对比
    generatePerformanceComparison() {
        const algorithm = this.algorithmData[this.currentConfig.algorithm];
        const algorithmName = algorithm ? algorithm.name : '当前算法';
        
        return `
            <div class="chart-container">
                <h5>综合性能对比分析</h5>
                <div class="performance-comparison-grid">
                    <div class="comparison-card">
                        <div class="metric-icon">⚡</div>
                        <div class="metric-title">计算效率</div>
                        <div class="metric-bars">
                            <div class="bar-item">
                                <span class="bar-label">基线</span>
                                <div class="bar-bg">
                                    <div class="bar-fill baseline" style="width: 78%">78ms</div>
                                </div>
                            </div>
                            <div class="bar-item">
                                <span class="bar-label">当前</span>
                                <div class="bar-bg">
                                    <div class="bar-fill current" style="width: ${algorithm ? algorithm.performance.efficiency : 50}%">
                                        ${algorithm ? algorithm.performance.efficiency : 50}ms
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="improvement-badge positive">提升 ${algorithm ? Math.round((78 - algorithm.performance.efficiency) / 78 * 100) : 36}%</div>
                    </div>
                    
                    <div class="comparison-card">
                        <div class="metric-icon">🎯</div>
                        <div class="metric-title">路径优化度</div>
                        <div class="metric-bars">
                            <div class="bar-item">
                                <span class="bar-label">基线</span>
                                <div class="bar-bg">
                                    <div class="bar-fill baseline" style="width: 60%">60分</div>
                                </div>
                            </div>
                            <div class="bar-item">
                                <span class="bar-label">当前</span>
                                <div class="bar-bg">
                                    <div class="bar-fill current" style="width: 85%">85分</div>
                                </div>
                            </div>
                        </div>
                        <div class="improvement-badge positive">提升 42%</div>
                    </div>
                    
                    <div class="comparison-card">
                        <div class="metric-icon">🔋</div>
                        <div class="metric-title">能耗效率</div>
                        <div class="metric-bars">
                            <div class="bar-item">
                                <span class="bar-label">基线</span>
                                <div class="bar-bg">
                                    <div class="bar-fill baseline" style="width: 70%">70%</div>
                                </div>
                            </div>
                            <div class="bar-item">
                                <span class="bar-label">当前</span>
                                <div class="bar-bg">
                                    <div class="bar-fill current" style="width: 88%">88%</div>
                                </div>
                            </div>
                        </div>
                        <div class="improvement-badge positive">提升 26%</div>
                    </div>
                    
                    <div class="comparison-card">
                        <div class="metric-icon">📊</div>
                        <div class="metric-title">综合评分</div>
                        <div class="score-display">
                            <div class="score-circle">
                                <svg viewBox="0 0 100 100">
                                    <circle cx="50" cy="50" r="45" fill="none" stroke="#e0e0e0" stroke-width="8"/>
                                    <circle cx="50" cy="50" r="45" fill="none" stroke="#28a745" stroke-width="8"
                                            stroke-dasharray="283" stroke-dashoffset="${283 - (283 * 0.85)}"
                                            transform="rotate(-90 50 50)"/>
                                    <text x="50" y="55" text-anchor="middle" font-size="20" font-weight="bold" fill="#333">85</text>
                                </svg>
                            </div>
                            <div class="score-label">优秀</div>
                        </div>
                    </div>
                </div>
                <div class="chart-description">
                    <p><strong>综合评价：</strong></p>
                    <p>${algorithmName}在多个维度上都表现出色，特别是在计算效率和路径优化方面有显著提升。
                    该算法适合应用于实时交通管理场景，能够有效提升整体交通效率。</p>
                </div>
            </div>
        `;
    }
    
    // 添加结果显示样式
    addResultsStyles() {
        if (!document.getElementById('results-styles')) {
            const style = document.createElement('style');
            style.id = 'results-styles';
            style.textContent = `
                .simulation-results {
                    width: 100%;
                    height: 100%;
                }
                
                .results-header {
                    padding: 10px;
                    border-bottom: 1px solid #ddd;
                }
                
                .results-tabs {
                    margin-top: 10px;
                }
                
                .tab-btn {
                    padding: 8px 16px;
                    margin-right: 5px;
                    border: 1px solid #ddd;
                    background: #f8f9fa;
                    cursor: pointer;
                    border-radius: 4px;
                }
                
                .tab-btn.active {
                    background: #2C5AA0;
                    color: white;
                    border-color: #2C5AA0;
                }
                
                .results-content {
                    padding: 20px;
                    height: calc(100% - 100px);
                    overflow: auto;
                }
                
                .result-tab {
                    display: none;
                    width: 100%;
                    height: 100%;
                }
                
                .result-tab.active {
                    display: block;
                }
                
                .result-tab svg {
                    max-width: 100%;
                    height: auto;
                }
            `;
            document.head.appendChild(style);
        }
    }

    // 检查数据源
    checkDataSources() {
        // 模拟检查，实际应用中可以根据需要调整
        return true;
    }

    escapeHtml(value) {
        return String(value || '').replace(/[&<>"']/g, char => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[char]));
    }

    formatFileSize(size) {
        const bytes = Number(size || 0);
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }

    fileRoleText(role) {
        const map = {
            sumo_config: 'SUMO配置',
            sumo_network: '路网',
            sumo_route: '车流',
            sumo_related: 'SUMO文件',
            opendrive: 'OpenDRIVE',
            scenario_json: '场景JSON',
            archive: '压缩包',
            supporting_file: '辅助文件'
        };
        return map[role] || '文件';
    }

    // 设置配置输入是否可用
    setConfigInputsEnabled(enabled) {
        const inputs = [
            'algorithm-type', 'test-scenario', 'search-radius', 
            'optimization-level', 'convergence-threshold'
        ];
        
        inputs.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.disabled = !enabled;
            }
        });
        
        document.getElementById('reset-config').disabled = !enabled;
    }

    // 重置配置
    resetConfiguration() {
        if (this.isTesting) {
            this.stopTest();
        }
        
        // 隐藏SUMO仿真界面图片
        this.hideSimulationImage();
        
        // 重置配置参数
        this.currentConfig = {
            algorithm: 'baseline',
            scenario: 'urban',
            parameters: {
                searchRadius: 100,
                optimizationLevel: 3,
                convergenceThreshold: 0.01
            },
            dataSources: {
                topology: false,
                traffic: false,
                od: false
            }
        };
        
        // 重置界面元素
        document.getElementById('algorithm-type').value = 'baseline';
        document.getElementById('test-scenario').value = 'urban';
        document.getElementById('search-radius').value = 100;
        document.getElementById('optimization-level').value = 3;
        document.getElementById('optimization-value').textContent = '3';
        document.getElementById('convergence-threshold').value = 0.01;
        
        // 重置数据源状态
        ['topology', 'traffic', 'od'].forEach(source => {
            const statusElement = document.getElementById(`${source}-status`);
            if (statusElement) {
                statusElement.textContent = '未选择文件';
                statusElement.className = 'data-status status-pending';
            }
        });

        this.uploadedSimulatorFiles = [];
        this.selectedSimulatorFile = null;
        this.currentUploadId = null;
        this.renderUploadedSimulatorFiles();
        this.updateActiveSimulatorConfig();
        this.updateSimulatorLaunchButtons();
        const uploadStatus = document.getElementById('simulator-upload-status');
        const fileInput = document.getElementById('simulator-file-input');
        const uploadBtn = document.getElementById('upload-simulator-files');
        if (uploadStatus) uploadStatus.textContent = '尚未选择文件';
        if (fileInput) fileInput.value = '';
        if (uploadBtn) uploadBtn.disabled = true;
        
        // 重置进度（如果存在）
        const progressBar = document.getElementById('test-progress');
        const progressText = document.getElementById('progress-percentage');
        if (progressBar) progressBar.style.width = '0%';
        if (progressText) progressText.textContent = '0%';
        
        // 重置状态
        document.getElementById('test-status-value').textContent = '就绪';
        document.getElementById('test-status-value').style.color = '#2C5AA0';
        
        // 重置SUMO状态文本
        const sumoStatusText = document.getElementById('sumo-status-text');
        if (sumoStatusText) {
            sumoStatusText.textContent = '等待启动';
            sumoStatusText.style.color = '';
        }
        
        this.testDuration = 0;
        
        // 更新显示
        this.updateAlgorithmInfo();
        this.updatePerformanceDisplay();
        this.updateResultsSummary();
        
        this.showMessage('配置已重置', 'info');
    }

    // 下载实验报告（纯前端实现，无需仿真和后端）
    async downloadReport() {
        try {
            // 检查docx库是否加载
            if (typeof docx === 'undefined') {
                this.showMessage('Word生成库未加载，请刷新页面重试', 'error');
                return;
            }

            // 更新按钮状态
            const downloadBtn = document.getElementById('download-report-btn');
            const originalText = downloadBtn ? downloadBtn.textContent : '导出报告';
            if (downloadBtn) {
                downloadBtn.textContent = '生成中...';
                downloadBtn.disabled = true;
            }
            
            this.showMessage('正在生成Word文档（含示例图表）...', 'info');

            // 获取配置信息（如果没有则使用默认值）
            const algorithmType = document.getElementById('algorithm-type') ? 
                document.getElementById('algorithm-type').selectedOptions[0].text : 'A*启发式搜索';
            const testRegion = document.getElementById('test-region') ? 
                document.getElementById('test-region').selectedOptions[0].text : '校园核心区域';
            const testScenario = document.getElementById('test-scenario') ? 
                document.getElementById('test-scenario').selectedOptions[0].text : '城市路网场景';
            
            // 尝试获取SVG图表，如果没有则生成示例图表
            let timeSeriesImageData = null;
            let tripAnalysisImageData = null;
            
            const timeSeriesSvg = document.querySelector('#time-series-image-container svg');
            const tripAnalysisSvg = document.querySelector('#trip-analysis-image-container svg');
            
            if (timeSeriesSvg) {
                timeSeriesImageData = await this.svgToImageData(timeSeriesSvg);
            } else {
                // 生成示例时间序列图表
                timeSeriesImageData = await this.generateSampleChart('时间序列分析');
            }
            
            if (tripAnalysisSvg) {
                tripAnalysisImageData = await this.svgToImageData(tripAnalysisSvg);
            } else {
                // 生成示例行程分析图表
                tripAnalysisImageData = await this.generateSampleChart('行程分析');
            }

            // 创建Word文档
            const doc = new docx.Document({
                sections: [{
                    properties: {},
                    children: [
                        // 标题
                        new docx.Paragraph({
                            text: "SUMO交通仿真实验结果报告",
                            heading: docx.HeadingLevel.TITLE,
                            alignment: docx.AlignmentType.CENTER,
                            spacing: { after: 400 }
                        }),

                        // 一、实验信息
                        new docx.Paragraph({
                            text: "一、实验信息",
                            heading: docx.HeadingLevel.HEADING_1,
                            spacing: { before: 300, after: 200 }
                        }),
                        this.createTableRow("实验名称", "基于虚实结合仿真的算法测试"),
                        this.createTableRow("算法类型", algorithmType),
                        this.createTableRow("测试区域", testRegion),
                        this.createTableRow("测试场景", testScenario),
                        this.createTableRow("实验时间", new Date().toLocaleString('zh-CN')),

                        // 二、仿真结果
                        new docx.Paragraph({
                            text: "二、仿真结果",
                            heading: docx.HeadingLevel.HEADING_1,
                            spacing: { before: 300, after: 200 }
                        }),

                        // 时间序列分析图
                        ...(timeSeriesImageData ? [
                            new docx.Paragraph({
                                text: "图1：时间序列分析",
                                heading: docx.HeadingLevel.HEADING_2,
                                spacing: { before: 200, after: 100 }
                            }),
                            new docx.Paragraph({
                                children: [
                                    new docx.ImageRun({
                                        data: timeSeriesImageData,
                                        transformation: {
                                            width: 550,
                                            height: 400
                                        }
                                    })
                                ],
                                spacing: { after: 300 }
                            })
                        ] : []),

                        // 行程分析图
                        ...(tripAnalysisImageData ? [
                            new docx.Paragraph({
                                text: "图2：行程分析",
                                heading: docx.HeadingLevel.HEADING_2,
                                spacing: { before: 200, after: 100 }
                            }),
                            new docx.Paragraph({
                                children: [
                                    new docx.ImageRun({
                                        data: tripAnalysisImageData,
                                        transformation: {
                                            width: 550,
                                            height: 400
                                        }
                                    })
                                ],
                                spacing: { after: 300 }
                            })
                        ] : []),

                        // 三、实验分析
                        new docx.Paragraph({
                            text: "三、实验分析",
                            heading: docx.HeadingLevel.HEADING_1,
                            spacing: { before: 300, after: 200 }
                        }),
                        new docx.Paragraph({
                            text: "本次实验通过SUMO仿真平台验证了所选算法在虚实结合场景下的性能表现。",
                            spacing: { after: 150 }
                        }),
                        new docx.Paragraph({
                            text: "时间序列分析：展示了仿真过程中各项指标随时间的变化趋势，包括车辆数量、平均速度、等待时间等关键参数。",
                            spacing: { after: 150 }
                        }),
                        new docx.Paragraph({
                            text: "行程分析：统计了车辆行程时间、行程距离等数据，反映了路网的整体运行效率。",
                            spacing: { after: 150 }
                        }),

                        // 四、实验结论
                        new docx.Paragraph({
                            text: "四、实验结论",
                            heading: docx.HeadingLevel.HEADING_1,
                            spacing: { before: 300, after: 200 }
                        }),
                        new docx.Paragraph({
                            text: "实验成功验证了算法在虚实结合仿真环境下的有效性，仿真结果符合预期，为实际应用提供了理论支撑。",
                            spacing: { after: 150 }
                        })
                    ]
                }]
            });

            // 生成并下载文档
            const blob = await docx.Packer.toBlob(doc);
            const filename = `SUMO仿真实验报告_${new Date().getTime()}.docx`;
            
            // 使用FileSaver下载
            if (typeof saveAs !== 'undefined') {
                saveAs(blob, filename);
            } else {
                // 备用下载方法
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            }
            
            this.showMessage('报告下载成功！', 'success');
            
            // 恢复按钮状态
            downloadBtn.textContent = originalText;
            downloadBtn.disabled = false;
            
        } catch (error) {
            console.error('下载报告失败:', error);
            this.showMessage(`下载报告失败: ${error.message}`, 'error');
            
            // 恢复按钮状态
            const downloadBtn = document.getElementById('download-report-btn');
            if (downloadBtn) {
                downloadBtn.textContent = '导出报告';
                downloadBtn.disabled = false;
            }
        }
    }

    // 辅助函数：创建表格行
    createTableRow(label, value) {
        return new docx.Paragraph({
            children: [
                new docx.TextRun({
                    text: label + "：",
                    bold: true
                }),
                new docx.TextRun({
                    text: value
                })
            ],
            spacing: { after: 100 }
        });
    }

    // 辅助函数：将SVG转换为图片数据
    async svgToImageData(svgElement) {
        return new Promise((resolve, reject) => {
            try {
                // 获取SVG的XML字符串
                const svgData = new XMLSerializer().serializeToString(svgElement);
                const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
                const url = URL.createObjectURL(svgBlob);
                
                // 创建图片
                const img = new Image();
                img.onload = () => {
                    // 创建canvas
                    const canvas = document.createElement('canvas');
                    canvas.width = svgElement.width.baseVal.value || 800;
                    canvas.height = svgElement.height.baseVal.value || 600;
                    
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0);
                    
                    // 转换为PNG
                    canvas.toBlob((blob) => {
                        const reader = new FileReader();
                        reader.onloadend = () => {
                            const base64data = reader.result.split(',')[1];
                            const binaryString = atob(base64data);
                            const bytes = new Uint8Array(binaryString.length);
                            for (let i = 0; i < binaryString.length; i++) {
                                bytes[i] = binaryString.charCodeAt(i);
                            }
                            URL.revokeObjectURL(url);
                            resolve(bytes);
                        };
                        reader.onerror = reject;
                        reader.readAsDataURL(blob);
                    }, 'image/png');
                };
                img.onerror = () => {
                    URL.revokeObjectURL(url);
                    reject(new Error('SVG加载失败'));
                };
                img.src = url;
            } catch (error) {
                reject(error);
            }
        });
    }

    // 辅助函数：生成示例图表（当没有真实数据时）
    async generateSampleChart(chartType) {
        return new Promise((resolve) => {
            try {
                const canvas = document.createElement('canvas');
                canvas.width = 800;
                canvas.height = 600;
                const ctx = canvas.getContext('2d');
                
                // 背景
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, 800, 600);
                
                // 标题
                ctx.fillStyle = '#333333';
                ctx.font = 'bold 24px Arial';
                ctx.textAlign = 'center';
                ctx.fillText(chartType + '（示例数据）', 400, 40);
                
                // 绘制坐标轴
                ctx.strokeStyle = '#666666';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.moveTo(80, 80);
                ctx.lineTo(80, 520);
                ctx.lineTo(720, 520);
                ctx.stroke();
                
                // Y轴标签
                ctx.font = '14px Arial';
                ctx.textAlign = 'right';
                ctx.fillStyle = '#666666';
                for (let i = 0; i <= 5; i++) {
                    const y = 520 - (i * 88);
                    ctx.fillText((i * 20).toString(), 70, y + 5);
                    ctx.beginPath();
                    ctx.moveTo(75, y);
                    ctx.lineTo(80, y);
                    ctx.stroke();
                }
                
                // X轴标签
                ctx.textAlign = 'center';
                for (let i = 0; i <= 10; i++) {
                    const x = 80 + (i * 64);
                    ctx.fillText(i.toString(), x, 540);
                    ctx.beginPath();
                    ctx.moveTo(x, 520);
                    ctx.lineTo(x, 525);
                    ctx.stroke();
                }
                
                // 绘制示例数据曲线
                ctx.strokeStyle = '#2196F3';
                ctx.lineWidth = 3;
                ctx.beginPath();
                for (let i = 0; i <= 10; i++) {
                    const x = 80 + (i * 64);
                    const y = 520 - (Math.sin(i * 0.5) * 100 + 150 + Math.random() * 50);
                    if (i === 0) {
                        ctx.moveTo(x, y);
                    } else {
                        ctx.lineTo(x, y);
                    }
                }
                ctx.stroke();
                
                // 添加图例
                ctx.fillStyle = '#2196F3';
                ctx.fillRect(600, 100, 20, 10);
                ctx.fillStyle = '#333333';
                ctx.font = '14px Arial';
                ctx.textAlign = 'left';
                ctx.fillText('示例数据', 625, 109);
                
                // 添加说明文字
                ctx.fillStyle = '#999999';
                ctx.font = '12px Arial';
                ctx.textAlign = 'center';
                ctx.fillText('注：此为示例图表，实际数据需运行仿真后生成', 400, 570);
                
                // 转换为图片数据
                canvas.toBlob((blob) => {
                    const reader = new FileReader();
                    reader.onloadend = () => {
                        const base64data = reader.result.split(',')[1];
                        const binaryString = atob(base64data);
                        const bytes = new Uint8Array(binaryString.length);
                        for (let i = 0; i < binaryString.length; i++) {
                            bytes[i] = binaryString.charCodeAt(i);
                        }
                        resolve(bytes);
                    };
                    reader.readAsDataURL(blob);
                }, 'image/png');
            } catch (error) {
                console.error('生成示例图表失败:', error);
                // 返回空数据
                resolve(new Uint8Array(0));
            }
        });
    }

    // 显示消息提示
    showMessage(message, type = 'info') {
        // 创建消息元素
        const messageEl = document.createElement('div');
        messageEl.className = `message message-${type}`;
        messageEl.textContent = message;
        
        // 添加样式
        messageEl.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 4px;
            color: white;
            font-size: 14px;
            z-index: 1000;
            transition: all 0.3s ease;
        `;
        
        // 根据类型设置颜色
        switch (type) {
            case 'success':
                messageEl.style.backgroundColor = '#28A745';
                break;
            case 'warning':
                messageEl.style.backgroundColor = '#FFC107';
                messageEl.style.color = '#333';
                break;
            case 'error':
                messageEl.style.backgroundColor = '#DC3545';
                break;
            default:
                messageEl.style.backgroundColor = '#2C5AA0';
        }
        
        // 添加到页面
        document.body.appendChild(messageEl);
        
        // 3秒后自动移除
        setTimeout(() => {
            if (messageEl.parentNode) {
                messageEl.style.opacity = '0';
                setTimeout(() => {
                    messageEl.parentNode.removeChild(messageEl);
                }, 300);
            }
        }, 3000);
    }
}

AlgorithmTestingSystem.prototype.startServerBackedTest = AlgorithmTestingSystem.prototype.startTest;

// 数据源选择函数
function selectDataSource(sourceType) {
    const statusElement = document.getElementById(`${sourceType}-status`);
    
    // 定义数据文件映射
    const dataFiles = {
        topology: {
            name: '路网拓扑数据',
            files: ['Tianjin.net.xml', 'input_node.csv', 'input_link.csv', 'node.csv', 'link.csv'],
            path: 'algorithm/交通流重构/原始文件备份/'
        },
        traffic: {
            name: '交通流量数据',
            files: ['sensor_count.csv', 'link_performance.csv', 'output_LinkMOE.csv', 'output_LinkTDMOE.csv'],
            path: 'algorithm/交通流重构/原始文件备份/'
        },
        od: {
            name: 'OD需求矩阵',
            files: ['input_demand.csv', 'ODME_final_result.csv', 'output_ODMOE.csv', 'output_ODTDMOE.csv'],
            path: 'algorithm/交通流重构/原始文件备份/'
        }
    };
    
    const dataSource = dataFiles[sourceType];
    
    if (dataSource) {
        // 显示加载动画
        statusElement.textContent = '加载中...';
        statusElement.className = 'data-status status-loading';
        
        // 模拟加载过程
        setTimeout(() => {
            // 更新状态为已加载
            const fileCount = dataSource.files.length;
            statusElement.textContent = `✓ 已加载 (${fileCount}个文件)`;
            statusElement.className = 'data-status status-selected';
            statusElement.title = `文件列表:\n${dataSource.files.join('\n')}`;
            
            // 更新系统状态
            if (window.algorithmTestingSystem) {
                window.algorithmTestingSystem.currentConfig.dataSources[sourceType] = true;
                
                // 显示详细信息
                const fileList = dataSource.files.map(f => `  • ${f}`).join('\n');
                window.algorithmTestingSystem.showMessage(
                    `${dataSource.name}已加载\n包含${fileCount}个文件:\n${fileList}`, 
                    'success'
                );
                
                // 在控制台输出详细信息
                console.log(`=== ${dataSource.name}加载成功 ===`);
                console.log(`数据路径: ${dataSource.path}`);
                console.log(`文件列表:`);
                dataSource.files.forEach(file => {
                    console.log(`  - ${file}`);
                });
                console.log('========================\n');
            }
        }, 500); // 模拟500ms的加载时间
    }
}

// 获取数据源名称
function getSourceName(sourceType) {
    const names = {
        topology: '路网拓扑数据',
        traffic: '交通流量数据',
        od: 'OD需求矩阵'
    };
    return names[sourceType] || sourceType;
}

// 页面加载完成后初始化系统
document.addEventListener('DOMContentLoaded', () => {
    window.algorithmTestingSystem = new AlgorithmTestingSystem();
    console.log('基于虚实结合仿真的算法测试功能教学模块已初始化');
});
// 结果标
签切换函数
function showResultTab(tabName) {
    // 隐藏所有标签内容
    document.querySelectorAll('.result-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // 移除所有按钮的active状态
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // 显示选中的标签内容
    const targetTab = document.getElementById(`${tabName}-result`);
    if (targetTab) {
        targetTab.classList.add('active');
    }
    
    // 激活对应的按钮
    event.target.classList.add('active');
}// 扩展算法数据以
支持三层级协同算法
const extendedAlgorithmData = {
    'three-level': {
        name: '三层级协同优化算法',
        description: '集成信号优化、路径诱导和车速控制的协同优化算法，通过多层级协调实现整体交通效率最大化。适用于复杂的车路协同场景。',
        features: [
            '上层：信号配时优化 - MPC-TuRBO算法',
            '中层：路径诱导优化 - KSP+MSA算法', 
            '下层：车速控制优化 - MPC-TuRBO算法',
            '协同机制：多目标优化与实时协调'
        ],
        performance: { efficiency: 28, length: 8.9, time: 14 }
    }
};

// 校园区域配置数据
const campusRegionData = {
    'campus-core': {
        name: '校园核心区域',
        description: '包含主要教学楼、图书馆、行政楼等核心设施的区域，交通流量密集，适合测试协同优化效果。',
        characteristics: ['高密度交通流', '多交叉口协同', '复杂路网结构']
    },
    'teaching-area': {
        name: '教学区',
        description: '主要包含各学院教学楼、实验楼等教学设施，具有明显的潮汐交通特征。',
        characteristics: ['潮汐交通流', '时段性拥堵', '多起终点分布']
    },
    'living-area': {
        name: '生活区',
        description: '包含学生宿舍、食堂、商业区等生活设施，交通需求相对稳定。',
        characteristics: ['稳定交通需求', '短距离出行', '多模式交通']
    },
    'full-campus': {
        name: '全校园',
        description: '覆盖整个校园的综合测试区域，包含所有功能分区，适合大规模协同优化测试。',
        characteristics: ['全域覆盖', '多场景融合', '综合性测试']
    }
};

// 关键性能指标管理
class KPIManager {
    constructor() {
        this.kpiData = {
            signalOptimization: 0,
            pathOptimization: 0,
            speedOptimization: 0,
            cooperativeGain: 0
        };
        this.kpiElements = {
            signalOptimization: document.getElementById('signalOptimization'),
            pathOptimization: document.getElementById('pathOptimization'),
            speedOptimization: document.getElementById('speedOptimization'),
            cooperativeGain: document.getElementById('cooperativeGain'),
            signalTrend: document.getElementById('signalTrend'),
            pathTrend: document.getElementById('pathTrend'),
            speedTrend: document.getElementById('speedTrend'),
            cooperativeTrend: document.getElementById('cooperativeTrend')
        };
    }

    updateKPI(algorithm, region) {
        // 根据算法类型和测试区域计算KPI
        let baseValues = this.calculateBaseKPI(algorithm, region);
        
        // 更新KPI数据
        this.kpiData = baseValues;
        
        // 更新UI显示
        this.updateKPIDisplay();
    }

    calculateBaseKPI(algorithm, region) {
        let multiplier = 1.0;
        
        // 根据算法类型调整基础值
        switch (algorithm) {
            case 'baseline':
                multiplier = 0.6;
                break;
            case 'optimization':
                multiplier = 0.75;
                break;
            case 'advanced':
                multiplier = 0.85;
                break;
            case 'three-level':
                multiplier = 0.95;
                break;
            default:
                multiplier = 0.7;
        }

        // 根据测试区域调整
        switch (region) {
            case 'campus-core':
                multiplier *= 1.1; // 核心区域效果更明显
                break;
            case 'full-campus':
                multiplier *= 1.05; // 全校园略有提升
                break;
        }

        return {
            signalOptimization: Math.round(65 * multiplier + Math.random() * 10),
            pathOptimization: Math.round(70 * multiplier + Math.random() * 10),
            speedOptimization: Math.round(68 * multiplier + Math.random() * 10),
            cooperativeGain: Math.round(72 * multiplier + Math.random() * 8)
        };
    }

    updateKPIDisplay() {
        Object.keys(this.kpiData).forEach(key => {
            const element = this.kpiElements[key];
            const trendElement = this.kpiElements[key + 'Trend'];
            
            if (element) {
                element.textContent = this.kpiData[key] + '%';
            }
            
            if (trendElement) {
                const trend = this.calculateTrend(this.kpiData[key]);
                trendElement.textContent = trend.text;
                trendElement.className = 'kpi-trend ' + trend.class;
            }
        });
    }

    calculateTrend(value) {
        if (value >= 80) {
            return { text: '↗ 优秀', class: 'positive' };
        } else if (value >= 60) {
            return { text: '→ 良好', class: 'neutral' };
        } else {
            return { text: '↘ 待优化', class: 'negative' };
        }
    }
}

// 扩展原有的AlgorithmTestingSystem类
AlgorithmTestingSystem.prototype.initializeExtendedFeatures = function() {
    this.kpiManager = new KPIManager();
    
    // 合并扩展的算法数据
    Object.assign(this.algorithmData, extendedAlgorithmData);
    
    // 添加新的配置项
    this.currentConfig.testRegion = 'campus-core';
    this.currentConfig.optimizationObjective = 'min-time';
    this.currentConfig.weights = {
        time: 0.4,
        distance: 0.3,
        energy: 0.3
    };
    
    // 设置新的事件监听器
    this.setupExtendedEventListeners();
    if (this.kpiManager) {
        this.kpiManager.updateKPI(this.currentConfig.algorithm, this.currentConfig.testRegion);
    }
};

AlgorithmTestingSystem.prototype.setupExtendedEventListeners = function() {
    // 测试区域选择
    const testRegionSelect = document.getElementById('test-region');
    if (testRegionSelect) {
        testRegionSelect.addEventListener('change', (e) => {
            this.currentConfig.testRegion = e.target.value;
            this.updateRegionInfo(e.target.value);
        });
    }

    // 优化目标选择
    const optimizationObjectiveSelect = document.getElementById('optimization-objective');
    if (optimizationObjectiveSelect) {
        optimizationObjectiveSelect.addEventListener('change', (e) => {
            this.currentConfig.optimizationObjective = e.target.value;
            this.updateWeightVisibility(e.target.value);
        });
    }

    // 权重滑块
    ['time', 'distance', 'energy'].forEach(type => {
        const slider = document.getElementById(`weight-${type}`);
        const valueDisplay = document.getElementById(`weight-${type}-value`);
        
        if (slider && valueDisplay) {
            slider.addEventListener('input', (e) => {
                const value = parseFloat(e.target.value);
                this.currentConfig.weights[type] = value;
                valueDisplay.textContent = value.toFixed(1);
                this.normalizeWeights(type);
            });
        }
    });
};

AlgorithmTestingSystem.prototype.updateRegionInfo = function(region) {
    const regionData = campusRegionData[region];
    if (!regionData) return;

    // 显示区域信息
    const regionHighlight = document.querySelector('.region-highlight');
    if (regionHighlight) {
        regionHighlight.innerHTML = `
            <strong>${regionData.name}</strong>
            <p>${regionData.description}</p>
            <ul>
                ${regionData.characteristics.map(char => `<li>${char}</li>`).join('')}
            </ul>
        `;
        regionHighlight.classList.add('active');
    }
};

AlgorithmTestingSystem.prototype.updateWeightVisibility = function(objective) {
    const weightControls = document.querySelectorAll('[id^="weight-"]');
    
    if (objective === 'balanced') {
        weightControls.forEach(control => {
            control.closest('.form-group').style.display = 'block';
        });
    } else {
        weightControls.forEach(control => {
            control.closest('.form-group').style.display = 'none';
        });
    }
};

AlgorithmTestingSystem.prototype.normalizeWeights = function(changedType) {
    const weights = this.currentConfig.weights;
    const total = Object.values(weights).reduce((sum, val) => sum + val, 0);
    
    if (total > 1.0) {
        // 按比例调整其他权重
        const excess = total - 1.0;
        const otherTypes = Object.keys(weights).filter(type => type !== changedType);
        
        otherTypes.forEach(type => {
            const reduction = (weights[type] / (total - weights[changedType])) * excess;
            weights[type] = Math.max(0, weights[type] - reduction);
            
            const slider = document.getElementById(`weight-${type}`);
            const valueDisplay = document.getElementById(`weight-${type}-value`);
            
            if (slider && valueDisplay) {
                slider.value = weights[type].toFixed(1);
                valueDisplay.textContent = weights[type].toFixed(1);
            }
        });
    }
};

AlgorithmTestingSystem.prototype.updateAlgorithmInfo = function(algorithmType) {
    algorithmType = algorithmType || this.currentConfig.algorithm || 'baseline';
    const algorithmData = this.algorithmData[algorithmType];
    if (!algorithmData) return;

    const infoContainer = document.getElementById('algorithm-info');
    if (infoContainer) {
        infoContainer.innerHTML = `
            <h4>${algorithmData.name}</h4>
            <p>${algorithmData.description}</p>
            <ul>
                ${algorithmData.features.map(feature => `<li>${feature}</li>`).join('')}
            </ul>
        `;
    }

    // 显示三层级协同算法的特殊配置
    const threeLevelConfig = document.querySelector('.three-level-config');
    if (threeLevelConfig) {
        if (algorithmType === 'three-level') {
            threeLevelConfig.classList.add('active');
        } else {
            threeLevelConfig.classList.remove('active');
        }
    }
};

AlgorithmTestingSystem.prototype.startTest = function() {
    if (typeof this.startServerBackedTest === 'function') {
        return this.startServerBackedTest();
    }
};

AlgorithmTestingSystem.prototype.simulateTestProcess = function() {
    let progress = 0;
    const interval = setInterval(() => {
        progress += 2;
        
        if (progress >= 100) {
            clearInterval(interval);
            this.completeTest();
        } else {
            // 更新进度和中间结果
            this.updateTestProgress(progress);
        }
    }, 100);
};

AlgorithmTestingSystem.prototype.updateTestProgress = function(progress) {
    // 更新SUMO状态
    const statusText = document.getElementById('sumo-status-text');
    if (statusText) {
        if (progress < 30) {
            statusText.textContent = '初始化仿真环境...';
        } else if (progress < 60) {
            statusText.textContent = '运行算法测试...';
        } else if (progress < 90) {
            statusText.textContent = '收集性能数据...';
        } else {
            statusText.textContent = '生成测试报告...';
        }
    }
};

AlgorithmTestingSystem.prototype.completeTest = function() {
    this.isTesting = false;
    this.testDuration = Date.now() - this.testStartTime;
    
    // 更新UI状态
    if (typeof this.updateTestingUI === 'function') {
        this.updateTestingUI(false);
    } else {
        this.setConfigInputsEnabled(true);
        const startBtn = document.getElementById('start-test');
        if (startBtn) {
            startBtn.disabled = false;
            startBtn.textContent = '开始测试';
        }
    }
    
    // 显示最终结果
    this.displayFinalResults();
    
    // 更新SUMO状态
    const statusText = document.getElementById('sumo-status-text');
    if (statusText) {
        statusText.textContent = '测试完成';
    }
};

AlgorithmTestingSystem.prototype.displayFinalResults = function() {
    const algorithmData = this.algorithmData[this.currentConfig.algorithm];
    if (!algorithmData) return;

    // 更新性能对比数据
    const performance = algorithmData.performance;
    
    document.getElementById('current-efficiency').textContent = performance.efficiency;
    document.getElementById('current-length').textContent = performance.length;
    document.getElementById('current-time').textContent = performance.time;
    
    // 计算改进百分比
    const baselinePerf = this.algorithmData.baseline.performance;
    
    const efficiencyImprovement = ((baselinePerf.efficiency - performance.efficiency) / baselinePerf.efficiency * 100).toFixed(0);
    const lengthImprovement = ((baselinePerf.length - performance.length) / baselinePerf.length * 100).toFixed(0);
    const timeImprovement = ((baselinePerf.time - performance.time) / baselinePerf.time * 100).toFixed(0);
    
    document.getElementById('efficiency-improvement').textContent = `+${efficiencyImprovement}% 提升`;
    document.getElementById('length-improvement').textContent = `-${lengthImprovement}% 优化`;
    document.getElementById('time-improvement').textContent = `-${timeImprovement}% 优化`;
};

// 初始化扩展功能
document.addEventListener('DOMContentLoaded', function() {
    if (window.algorithmTestingSystem) {
        window.algorithmTestingSystem.initializeExtendedFeatures();
        window.algorithmTestingSystem.updatePerformanceDisplay();
        window.algorithmTestingSystem.updateResultsSummary();
    }
});

// 导出仿真报告功能 - 简化版
async function exportSimulationReport() {
    const exportBtn = document.getElementById('export-report-btn');
    const originalText = exportBtn.textContent;
    exportBtn.textContent = '📥 导出中...';
    exportBtn.disabled = true;
    
    try {
        const response = await fetch('/api/simulation/download_report', {
            method: 'GET',
            signal: AbortSignal.timeout(5000)
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `SUMO仿真报告_${new Date().toISOString().slice(0,10)}.docx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            showExportMessage('Word报告导出成功！', 'success');
        } else {
            throw new Error('后端服务返回错误');
        }
    } catch (error) {
        console.log('导出失败:', error);
        showExportMessage('服务器后端服务暂不可用，无法导出Word报告', 'warning');
    } finally {
        exportBtn.textContent = originalText;
        exportBtn.disabled = false;
    }
}

// 显示服务器服务检查说明 - 已废弃，保留给旧调用兼容
function showBackendGuide_deprecated() {
    const guideDiv = document.createElement('div');
    guideDiv.className = 'backend-guide-modal';
    guideDiv.innerHTML = `
        <div class="guide-content">
            <div class="guide-header">
                <span class="guide-icon">📄</span>
                <h3>服务器后端服务暂不可用</h3>
            </div>
            <div class="guide-body">
                <p class="guide-intro">请检查服务器上的主平台服务和 SUMO 仿真子服务运行状态。</p>
                <ol class="guide-steps">
                    <li>
                        <strong>检查服务状态</strong>
                        <p>访问 /api/simulation/health 确认仿真服务是否可用。</p>
                    </li>
                    <li>
                        <strong>重新启动平台服务</strong>
                        <p><code>Web\\启动本地平台Web访问.bat</code></p>
                    </li>
                    <li>
                        <strong>等待服务启动</strong>
                        <p>看到 "服务已启动" 提示后即可</p>
                    </li>
                    <li>
                        <strong>返回页面导出</strong>
                        <p>再次点击"导出报告"按钮</p>
                    </li>
                </ol>
                <div class="guide-note">
                    <p><strong>💡 提示：</strong>后端服务会自动生成包含图表的Word文档</p>
                </div>
            </div>
            <div class="guide-footer">
                <button onclick="this.closest('.backend-guide-modal').remove(); document.querySelector('.backend-guide-overlay').remove();" class="btn btn-primary">知道了</button>
            </div>
        </div>
    `;
    
    // 添加样式
    if (!document.getElementById('backend-guide-styles')) {
        const style = document.createElement('style');
        style.id = 'backend-guide-styles';
        style.textContent = `
            .backend-guide-modal {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                border-radius: 12px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                z-index: 2000;
                max-width: 600px;
                width: 90%;
                max-height: 80vh;
                overflow-y: auto;
            }
            
            .backend-guide-modal .guide-content {
                padding: 0;
            }
            
            .backend-guide-modal .guide-header {
                background: linear-gradient(135deg, #2C5AA0 0%, #1e3f73 100%);
                color: white;
                padding: 24px;
                border-radius: 12px 12px 0 0;
                display: flex;
                align-items: center;
                gap: 12px;
            }
            
            .backend-guide-modal .guide-icon {
                font-size: 32px;
            }
            
            .backend-guide-modal .guide-header h3 {
                margin: 0;
                font-size: 18px;
                font-weight: 600;
            }
            
            .backend-guide-modal .guide-body {
                padding: 24px;
            }
            
            .backend-guide-modal .guide-intro {
                margin: 0 0 16px 0;
                color: #666;
                font-size: 14px;
            }
            
            .backend-guide-modal .guide-steps {
                margin: 0;
                padding-left: 20px;
                list-style: none;
                counter-reset: step-counter;
            }
            
            .backend-guide-modal .guide-steps li {
                counter-increment: step-counter;
                margin-bottom: 20px;
                position: relative;
                padding-left: 40px;
            }
            
            .backend-guide-modal .guide-steps li::before {
                content: counter(step-counter);
                position: absolute;
                left: 0;
                top: 0;
                width: 28px;
                height: 28px;
                background: #2C5AA0;
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 600;
                font-size: 14px;
            }
            
            .backend-guide-modal .guide-steps li strong {
                display: block;
                margin-bottom: 4px;
                color: #333;
                font-size: 15px;
            }
            
            .backend-guide-modal .guide-steps li p {
                margin: 0;
                color: #666;
                font-size: 13px;
                line-height: 1.5;
            }
            
            .backend-guide-modal .guide-steps li code {
                background: #f5f5f5;
                padding: 2px 8px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                color: #2C5AA0;
                font-size: 12px;
                display: block;
                margin-top: 4px;
                word-break: break-all;
            }
            
            .backend-guide-modal .guide-note {
                background: #E3F2FD;
                padding: 12px 16px;
                border-radius: 6px;
                border-left: 4px solid #2C5AA0;
                margin-top: 16px;
            }
            
            .backend-guide-modal .guide-note p {
                margin: 0;
                color: #1565C0;
                font-size: 13px;
            }
            
            .backend-guide-modal .guide-footer {
                padding: 16px 24px;
                border-top: 1px solid #eee;
                text-align: right;
            }
            
            .backend-guide-modal .guide-footer .btn {
                padding: 10px 24px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s;
            }
            
            .backend-guide-modal .guide-footer .btn-primary {
                background: #2C5AA0;
                color: white;
            }
            
            .backend-guide-modal .guide-footer .btn-primary:hover {
                background: #1e3f73;
            }
            
            .backend-guide-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.6);
                z-index: 1999;
                backdrop-filter: blur(2px);
            }
        `;
        document.head.appendChild(style);
    }
    
    const overlay = document.createElement('div');
    overlay.className = 'backend-guide-overlay';
    overlay.onclick = () => {
        document.body.removeChild(overlay);
        document.body.removeChild(guideDiv);
    };
    
    document.body.appendChild(overlay);
    document.body.appendChild(guideDiv);
}

// 显示导出消息
function showExportMessage(message, type) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `export-message export-${type}`;
    messageDiv.textContent = message;
    messageDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 24px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 500;
        z-index: 10000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: slideIn 0.3s ease;
    `;
    
    if (type === 'success') {
        messageDiv.style.background = '#E3F2FD';
        messageDiv.style.color = '#1565C0';
        messageDiv.style.border = '1px solid #90CAF9';
    } else if (type === 'warning') {
        messageDiv.style.background = '#FFF3E0';
        messageDiv.style.color = '#E65100';
        messageDiv.style.border = '1px solid #FFB74D';
    } else {
        messageDiv.style.background = '#FFEBEE';
        messageDiv.style.color = '#C62828';
        messageDiv.style.border = '1px solid #EF9A9A';
    }
    
    document.body.appendChild(messageDiv);
    
    setTimeout(() => {
        messageDiv.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(messageDiv);
        }, 300);
    }, 3000);
}

// 旧的HTML导出函数（已废弃，保留供参考）
async function exportHTMLReport_deprecated(system) {
    const algorithm = system.algorithmData[system.currentConfig.algorithm];
    const algorithmName = algorithm ? algorithm.name : '当前算法';
    const timestamp = new Date().toLocaleString('zh-CN');
    
    // 获取已加载的图片
    const timeSeriesImage = system.loadedImages ? system.loadedImages['时间序列分析'] : '';
    const tripAnalysisImage = system.loadedImages ? system.loadedImages['行程分析'] : '';
    
    // 生成HTML报告内容
    const htmlContent = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SUMO仿真测试报告</title>
    <style>
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #f5f5f5;
            color: #333;
        }
        .report-container {
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .report-header {
            text-align: center;
            border-bottom: 3px solid #2C5AA0;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .report-title {
            font-size: 28px;
            font-weight: bold;
            color: #2C5AA0;
            margin-bottom: 10px;
        }
        .report-subtitle {
            font-size: 14px;
            color: #666;
        }
        .section {
            margin-bottom: 30px;
        }
        .section-title {
            font-size: 20px;
            font-weight: bold;
            color: #2C5AA0;
            border-left: 4px solid #2C5AA0;
            padding-left: 12px;
            margin-bottom: 16px;
        }
        .info-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 16px;
            margin-bottom: 20px;
        }
        .info-item {
            padding: 12px;
            background: #f8f9fa;
            border-radius: 4px;
            border-left: 3px solid #2C5AA0;
        }
        .info-label {
            font-size: 12px;
            color: #666;
            margin-bottom: 4px;
        }
        .info-value {
            font-size: 16px;
            font-weight: 600;
            color: #333;
        }
        .image-section {
            margin: 30px 0;
            page-break-inside: avoid;
        }
        .image-title {
            font-size: 16px;
            font-weight: 600;
            color: #333;
            margin-bottom: 12px;
            padding: 8px 12px;
            background: #E3F2FD;
            border-left: 4px solid #2C5AA0;
        }
        .image-container {
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 20px;
            background: white;
            text-align: center;
        }
        .image-container svg {
            max-width: 100%;
            height: auto;
        }
        .no-image {
            padding: 40px;
            text-align: center;
            color: #999;
            background: #f8f9fa;
            border-radius: 4px;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            text-align: center;
            font-size: 12px;
            color: #999;
        }
        @media print {
            body {
                background: white;
            }
            .report-container {
                box-shadow: none;
            }
        }
    </style>
</head>
<body>
    <div class="report-container">
        <div class="report-header">
            <div class="report-title">SUMO仿真测试报告</div>
            <div class="report-subtitle">基于虚实结合仿真的算法测试</div>
            <div class="report-subtitle">生成时间: ${timestamp}</div>
        </div>

        <div class="section">
            <div class="section-title">测试配置信息</div>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">算法类型</div>
                    <div class="info-value">${algorithmName}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">测试场景</div>
                    <div class="info-value">${document.getElementById('result-scenario').textContent}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">测试时长</div>
                    <div class="info-value">${document.getElementById('result-duration').textContent}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">综合评分</div>
                    <div class="info-value">${document.getElementById('result-score').textContent}</div>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">算法性能对比</div>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">路径规划效率</div>
                    <div class="info-value">
                        基线: ${document.getElementById('baseline-efficiency').textContent}ms → 
                        当前: ${document.getElementById('current-efficiency').textContent}ms
                        (${document.getElementById('efficiency-improvement').textContent})
                    </div>
                </div>
                <div class="info-item">
                    <div class="info-label">路径长度优化</div>
                    <div class="info-value">
                        基线: ${document.getElementById('baseline-length').textContent}km → 
                        当前: ${document.getElementById('current-length').textContent}km
                        (${document.getElementById('length-improvement').textContent})
                    </div>
                </div>
                <div class="info-item">
                    <div class="info-label">通行时间优化</div>
                    <div class="info-value">
                        基线: ${document.getElementById('baseline-time').textContent}min → 
                        当前: ${document.getElementById('current-time').textContent}min
                        (${document.getElementById('time-improvement').textContent})
                    </div>
                </div>
            </div>
        </div>

        <div class="image-section">
            <div class="image-title">📊 时间序列分析</div>
            <div class="image-container">
                ${timeSeriesImage || '<div class="no-image">图片未加载</div>'}
            </div>
        </div>

        <div class="image-section">
            <div class="image-title">🚗 行程分析</div>
            <div class="image-container">
                ${tripAnalysisImage || '<div class="no-image">图片未加载</div>'}
            </div>
        </div>

        <div class="footer">
            <p>本报告由车路协同虚实结合仿真教学平台自动生成</p>
            <p>© 2025 面向车路协同的虚实结合仿真教学平台 v2.0</p>
        </div>
    </div>
</body>
</html>
    `;
    
    // 创建Blob并下载
    const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `SUMO仿真报告_${new Date().toISOString().slice(0,10)}.html`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    
    // 注释：HTML导出功能已废弃
}


// 添加动画样式
if (!document.getElementById('export-animations')) {
    const style = document.createElement('style');
    style.id = 'export-animations';
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(400px);
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
                transform: translateX(400px);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}


