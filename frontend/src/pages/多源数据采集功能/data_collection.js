/**
 * 车辆检测跟踪功能 - JavaScript
 * 基于YOLO11 + BoTSORT的多目标车辆检测与跟踪
 */

// 后端API地址（统一使用主后端8000端口）
const API_BASE_URL = '';

// 每个浏览器标签页使用独立的数据采集传输会话，避免多个学生互相覆盖状态。
const COLLECTION_SESSION_KEY = 'zxk_data_collection_session_id';
const COLLECTION_SESSION_TOKEN_KEY = 'zxk_data_collection_session_token';
function createCollectionSessionId() {
    try {
        if (window.crypto && typeof window.crypto.randomUUID === 'function') {
            return window.crypto.randomUUID().replace(/-/g, '');
        }
        if (window.crypto && typeof window.crypto.getRandomValues === 'function') {
            const bytes = new Uint8Array(16);
            window.crypto.getRandomValues(bytes);
            return Array.from(bytes).map(function (value) {
                return value.toString(16).padStart(2, '0');
            }).join('');
        }
    } catch (error) {
        console.warn('无法使用浏览器安全随机数，改用时间戳会话标识', error);
    }
    return String(Date.now()) + String(Math.random()).slice(2);
}

let collectionSessionId = null;
let collectionSessionToken = null;
try {
    collectionSessionId = sessionStorage.getItem(COLLECTION_SESSION_KEY);
    collectionSessionToken = sessionStorage.getItem(COLLECTION_SESSION_TOKEN_KEY);
} catch (error) {
    console.warn('无法读取数据采集会话缓存', error);
}
if (!collectionSessionId || !/^[A-Za-z0-9_-]{16,128}$/.test(collectionSessionId)) {
    collectionSessionId = createCollectionSessionId();
    try { sessionStorage.setItem(COLLECTION_SESSION_KEY, collectionSessionId); } catch (error) { /* 隐私模式 */ }
}

// 仅为数据采集 API 自动附加会话头，不改变其他页面的请求。
const nativeCollectionFetch = window.fetch.bind(window);
window.fetch = function (input, init) {
    const requestUrl = typeof input === 'string' ? input : (input && input.url) || '';
    if (requestUrl.indexOf('/api/collection/') === -1) {
        return nativeCollectionFetch(input, init);
    }
    let transportUrl = requestUrl;
    try {
        const parsed = new URL(requestUrl, window.location.href);
        if (parsed.pathname.indexOf('/api/collection/session') !== 0) {
            const suffix = parsed.pathname.slice('/api/collection'.length);
            parsed.pathname = `/api/collection/session/${collectionSessionId}${suffix}`;
            transportUrl = parsed.toString();
        }
    } catch (error) {
        console.warn('数据采集请求地址解析失败:', requestUrl, error);
    }
    const options = Object.assign({}, init || {});
    const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
    headers.set('X-Client-Session', collectionSessionId);
    if (collectionSessionToken) headers.set('X-Client-Session-Token', collectionSessionToken);
    options.headers = headers;
    return nativeCollectionFetch(transportUrl, options);
};

async function establishCollectionSession() {
    try {
        const response = await nativeCollectionFetch(`${API_BASE_URL}/api/collection/session`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Client-Session': collectionSessionId,
                'X-Client-Session-Token': collectionSessionToken || ''
            },
            body: JSON.stringify({ session_id: collectionSessionId, session_token: collectionSessionToken })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (data && data.session_id && data.session_id !== collectionSessionId) {
            collectionSessionId = data.session_id;
            try { sessionStorage.setItem(COLLECTION_SESSION_KEY, collectionSessionId); } catch (error) { /* ignore */ }
        }
        if (data && data.session_token) {
            collectionSessionToken = data.session_token;
            try { sessionStorage.setItem(COLLECTION_SESSION_TOKEN_KEY, collectionSessionToken); } catch (error) { /* ignore */ }
        }
        return data;
    } catch (error) {
        console.warn('数据采集会话建立失败，将使用本地会话标识继续请求:', error);
        return null;
    }
}

function collectionSessionUrl(path) {
    const suffix = String(path || '').startsWith('/') ? String(path) : '/' + String(path || '');
    const token = encodeURIComponent(collectionSessionToken || '');
    return `${API_BASE_URL}/api/collection/session/${collectionSessionId}${suffix}${suffix.indexOf('?') >= 0 ? '&' : '?'}token=${token}`;
}

// 全局变量
let isDetecting = false;
let statusCheckInterval = null;
let selectedVideoFile = null;
let useDefaultVideo = true;  // 默认使用内置场景视频
let defaultVideoInfo = null;
let scenarioCatalog = [];
let selectedScenario = null;

function getDefaultVideoLabel() {
    return defaultVideoInfo && defaultVideoInfo.filename ? defaultVideoInfo.filename : '内置默认视频';
}

function updateDefaultVideoDisplay() {
    const videoInfo = document.getElementById('videoInfo');
    const videoSourceSelect = document.getElementById('videoSourceSelect');
    const defaultOption = videoSourceSelect ? videoSourceSelect.querySelector('option[value="default"]') : null;
    const label = getDefaultVideoLabel();

    if (defaultOption) {
        defaultOption.textContent = selectedScenario ? `内置场景视频（${selectedScenario.name}）` : `默认视频 (${label})`;
    }

    if (!videoInfo || !useDefaultVideo) {
        return;
    }

    if (selectedScenario) {
        videoInfo.innerHTML = `<p class="hint-text">当前场景: <strong>${selectedScenario.name}</strong> · ${Math.round(selectedScenario.durationSeconds || 45)} 秒</p>`;
        return;
    }

    if (defaultVideoInfo && defaultVideoInfo.success) {
        const sizeText = defaultVideoInfo.sizeMB ? `，${defaultVideoInfo.sizeMB}` : '';
        videoInfo.innerHTML = `<p class="hint-text">当前: 默认视频 ${label}${sizeText}</p>`;
        return;
    }

    const message = defaultVideoInfo && defaultVideoInfo.message ? defaultVideoInfo.message : '正在查找默认视频...';
    videoInfo.innerHTML = `<p class="hint-text">${message}</p>`;
}

async function loadDefaultVideoInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/collection/default-video`);
        defaultVideoInfo = await response.json();
    } catch (error) {
        defaultVideoInfo = { success: false, message: '无法获取默认视频信息' };
        console.error('获取默认视频信息失败:', error);
    }
    updateDefaultVideoDisplay();
}

async function loadScenarioCatalog() {
    const grid = document.getElementById('scenarioGrid');
    try {
        const response = await fetch(`${API_BASE_URL}/api/collection/scenarios`);
        const data = await response.json();
        if (!data.success || !Array.isArray(data.scenarios) || data.scenarios.length === 0) {
            throw new Error(data.message || '暂无内置场景');
        }
        scenarioCatalog = data.scenarios;
        renderScenarioCards();
        selectScenario(scenarioCatalog[0]);
    } catch (error) {
        console.error('加载内置场景失败:', error);
        if (grid) grid.innerHTML = '<div class="scenario-loading scenario-error">内置场景加载失败，可使用手动选择文件</div>';
    }
}

function renderScenarioCards() {
    const grid = document.getElementById('scenarioGrid');
    if (!grid) return;
    grid.innerHTML = scenarioCatalog.map(scenario => `
        <button type="button" class="scenario-card" data-scenario-id="${scenario.id}">
            <span class="scenario-card-title">${scenario.name}</span>
            <span class="scenario-card-description">${scenario.description}</span>
            <span class="scenario-card-meta">约 ${Math.round(scenario.durationSeconds || 45)} 秒 · ${scenario.sizeMB || ''}</span>
        </button>
    `).join('');
    grid.querySelectorAll('.scenario-card').forEach(card => {
        card.addEventListener('click', () => {
            const scenario = scenarioCatalog.find(item => item.id === card.dataset.scenarioId);
            if (scenario) selectScenario(scenario);
        });
    });
}

function selectScenario(scenario) {
    selectedScenario = scenario;
    useDefaultVideo = true;
    selectedVideoFile = null;
    const sourceSelect = document.getElementById('videoSourceSelect');
    const customSection = document.getElementById('customFileSection');
    if (sourceSelect) sourceSelect.value = 'default';
    if (customSection) customSection.style.display = 'none';
    document.querySelectorAll('.scenario-card').forEach(card => {
        card.classList.toggle('selected', card.dataset.scenarioId === scenario.id);
    });
    const videoInfo = document.getElementById('videoInfo');
    if (videoInfo) {
        videoInfo.innerHTML = `<p class="hint-text">当前场景: <strong>${scenario.name}</strong> · ${Math.round(scenario.durationSeconds || 45)} 秒</p>`;
    }
    updateDefaultVideoDisplay();
}

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
    ['startBtn', 'stopBtn', 'statsBtn'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.classList.remove('step-done');
        }
    });
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    establishCollectionSession().finally(function() {
    console.log('初始化车辆检测跟踪页面');
    
    // 初始化页面
    initPage();
    
    // 绑定事件
    bindEvents();
    
    // 检查服务器状态
    checkServerStatus();
    });
});

/**
 * 初始化页面
 */
function initPage() {
    // 初始化参数显示
    updateParamDisplay();
    
    // 更新状态显示
    updateStatusDisplay('就绪', 'ready');
    updateDefaultVideoDisplay();
    loadDefaultVideoInfo();
    loadScenarioCatalog();
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

    // 文件选择器
    const videoFileInput = document.getElementById('videoFileInput');
    if (videoFileInput) {
        videoFileInput.addEventListener('change', handleFileSelect);
    }

    // 开始检测按钮
    const startBtn = document.getElementById('startBtn');
    if (startBtn) {
        startBtn.addEventListener('click', startDetection);
    }

    // 停止检测按钮
    const stopBtn = document.getElementById('stopBtn');
    if (stopBtn) {
        stopBtn.addEventListener('click', stopDetection);
    }

    // 重置参数按钮
    const resetBtn = document.getElementById('resetBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', resetParameters);
    }

    // 查看检测结果按钮
    const generateDashboardBtn = document.getElementById('generateDashboardBtn');
    if (generateDashboardBtn) {
        generateDashboardBtn.addEventListener('click', loadDetectionResults);
    }

    // 下载结果按钮
    const downloadResultBtn = document.getElementById('downloadResultBtn');
    if (downloadResultBtn) {
        downloadResultBtn.addEventListener('click', downloadResults);
    }

    // 输出视频控制按钮
    const loadOutputBtn = document.getElementById('loadOutputBtn');
    if (loadOutputBtn) {
        loadOutputBtn.addEventListener('click', loadOutputVideo);
    }

    const refreshOutputBtn = document.getElementById('refreshOutputBtn');
    if (refreshOutputBtn) {
        refreshOutputBtn.addEventListener('click', refreshOutputVideo);
    }

    // 数据统计按钮
    const statsBtn = document.getElementById('statsBtn');
    if (statsBtn) {
        statsBtn.addEventListener('click', loadStatistics);
    }

    // 视频来源选择
    const videoSourceSelect = document.getElementById('videoSourceSelect');
    if (videoSourceSelect) {
        videoSourceSelect.addEventListener('change', function() {
            const customSection = document.getElementById('customFileSection');
            const videoInfo = document.getElementById('videoInfo');
            if (this.value === 'default') {
                useDefaultVideo = true;
                selectedVideoFile = null;
                if (customSection) customSection.style.display = 'none';
                if (videoInfo) updateDefaultVideoDisplay();
                if (!defaultVideoInfo || !defaultVideoInfo.success) {
                    loadDefaultVideoInfo();
                }
            } else {
                useDefaultVideo = false;
                selectedScenario = null;
                document.querySelectorAll('.scenario-card').forEach(card => card.classList.remove('selected'));
                if (customSection) customSection.style.display = 'block';
                if (videoInfo) videoInfo.innerHTML = '<p class="hint-text">请选择视频文件 (MP4, AVI, MOV, MKV)</p>';
            }
        });
    }
}

/**
 * 检查服务器状态（自动）
 */
async function checkServerStatus() {
    const statusEl = document.getElementById('serverStatus');
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/collection/health`, {
            method: 'GET'
        });
        
        if (response.ok) {
            statusEl.textContent = '服务器: 已连接 ✓';
            statusEl.style.color = '#28a745';
            updateStatusDisplay('后端已连接', 'ready');
        } else {
            throw new Error('服务器响应异常');
        }
    } catch (error) {
        statusEl.textContent = '服务器: 未连接 ✗';
        statusEl.style.color = '#dc3545';
        updateStatusDisplay('后端未连接', 'error');
        console.error('服务器连接失败:', error);
    }
}

/**
 * 处理文件选择
 */
function handleFileSelect(event) {
    const file = event.target.files[0];
    const fileText = document.getElementById('fileText');
    const fileLabel = document.querySelector('.file-input-label');
    const videoInfo = document.getElementById('videoInfo');
    
    if (file) {
        selectedVideoFile = file;
        
        // 更新显示
        fileText.textContent = file.name;
        fileLabel.classList.add('has-file');
        
        // 显示文件信息
        const sizeMB = (file.size / 1024 / 1024).toFixed(2);
        videoInfo.innerHTML = `
            <p><strong>已选择：</strong>${file.name}</p>
            <p><strong>大小：</strong>${sizeMB} MB</p>
            <p><strong>类型：</strong>${file.type || '视频文件'}</p>
        `;
        
        console.log('选择了视频文件:', file.name);
        
        // 在视频预览区域显示视频
        loadVideoPreview(file);
    } else {
        selectedVideoFile = null;
        fileText.textContent = '点击选择视频文件...';
        fileLabel.classList.remove('has-file');
        videoInfo.innerHTML = '<p class="hint-text">支持格式: MP4, AVI, MOV, MKV</p>';
        
        // 隐藏视频预览
        hideVideoPreview();
    }
}

/**
 * 加载视频预览（仅更新文件信息，不预览原始视频）
 */
function loadVideoPreview(file) {
    // 不再预览原始视频，只记录文件信息
    console.log('已选择视频文件:', file.name);
}

/**
 * 隐藏视频预览
 */
function hideVideoPreview() {
    const outputVideoPreview = document.getElementById('outputVideoPreview');
    const videoPlaceholder = document.getElementById('videoPlaceholder');
    
    if (outputVideoPreview) {
        outputVideoPreview.classList.remove('active');
        outputVideoPreview.src = '';
    }
    if (videoPlaceholder) {
        videoPlaceholder.classList.remove('hidden');
    }
}

/**
 * 更新参数显示
 */
function updateParamDisplay() {
    // 参数已简化，无需更新
}

/**
 * 更新状态显示
 */
function updateStatusDisplay(status, className) {
    const statusValue = document.getElementById('statusValue');
    if (statusValue) {
        statusValue.textContent = status;
        statusValue.className = `status-value ${className}`;
    }
}

/**
 * 开始检测
 */
async function startDetection() {
    if (!useDefaultVideo && !selectedVideoFile) {
        alert('请先选择要检测的视频文件');
        return;
    }
    
    try {
        // 更新UI状态
        isDetecting = true;
        updateDetectionUI(true);
        
        // 添加检测中样式
        const videoWrapper = document.getElementById('videoPreviewWrapper');
        if (videoWrapper) {
            videoWrapper.classList.add('detecting');
        }
        
        let videoFilename;
        
        if (useDefaultVideo) {
            if (selectedScenario && selectedScenario.filename) {
                updateStatusDisplay(`正在准备${selectedScenario.name}...`, 'detecting');
                videoFilename = selectedScenario.filename;
            } else {
                // 兼容没有场景目录时的旧默认视频
                updateStatusDisplay('正在准备默认视频...', 'detecting');
                const defaultResp = await fetch(`${API_BASE_URL}/api/collection/use-default-video`, { method: 'POST' });
                const defaultResult = await defaultResp.json();
                if (!defaultResult.success) throw new Error(defaultResult.message || '默认视频准备失败');
                defaultVideoInfo = defaultResult;
                updateDefaultVideoDisplay();
                videoFilename = defaultResult.filename;
            }
            console.log('使用内置视频:', videoFilename);
        } else {
            // 上传用户选择的视频
            updateStatusDisplay('正在上传视频...', 'detecting');
            const formData = new FormData();
            formData.append('video', selectedVideoFile, collectionSessionId + '_' + selectedVideoFile.name);
            
            const uploadResponse = await fetch(`${API_BASE_URL}/api/collection/upload-video`, {
                method: 'POST',
                body: formData
            });
            const uploadResult = await uploadResponse.json();
            if (!uploadResult.success) {
                throw new Error(uploadResult.message || '视频上传失败');
            }
            videoFilename = uploadResult.filename;
            console.log('视频上传成功:', videoFilename);
        }
        
        updateStatusDisplay('正在检测...', 'detecting');
        
        // 开始检测
        const outputName = collectionSessionId + '_' + videoFilename.replace(/\.[^.]+$/, '_output.mp4');
        const modelSelect = document.getElementById('modelSelect');
        const selectedModel = modelSelect ? modelSelect.value : 'yolo11n.pt';
        const params = {
            video: videoFilename,
            output: outputName,
            model: selectedModel,
            iou: 0.45,
            score: 0.50
        };
        
        const response = await fetch(`${API_BASE_URL}/api/collection/detection/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(params)
        });
        
        const result = await response.json();
        
        if (result.success) {
            console.log('检测任务已启动:', result);
            
            // 开始轮询检测状态和帧
            startStatusPolling();
            startFramePolling();
        } else {
            throw new Error(result.message || '启动检测失败');
        }
    } catch (error) {
        console.error('开始交通流采集失败:', error);
        alert('开始交通流采集失败: ' + error.message);
        isDetecting = false;
        updateDetectionUI(false);
        updateStatusDisplay('检测失败', 'error');
        
        // 移除检测中样式
        const videoWrapper = document.getElementById('videoPreviewWrapper');
        if (videoWrapper) {
            videoWrapper.classList.remove('detecting');
        }
    }
}

// 帧轮询定时器
let framePollingInterval = null;

/**
 * 开始轮询检测帧
 */
function startFramePolling() {
    if (framePollingInterval) {
        clearInterval(framePollingInterval);
    }
    
    console.log('开始轮询检测帧...');
    
    framePollingInterval = setInterval(async () => {
        if (!isDetecting) {
            stopFramePolling();
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}/api/collection/detection/frame`);
            const data = await response.json();
            
            console.log('获取帧数据:', data.frameNum, '帧是否存在:', !!data.frame);
            
            if (data.success) {
                // 更新检测帧显示（即使没有帧图像也更新统计数据）
                updateDetectionFrame(data);
            }
        } catch (error) {
            console.error('获取检测帧失败:', error);
        }
    }, 300); // 每300ms获取一帧
}

/**
 * 停止帧轮询
 */
function stopFramePolling() {
    if (framePollingInterval) {
        clearInterval(framePollingInterval);
        framePollingInterval = null;
    }
}

/**
 * 更新检测帧显示
 */
function updateDetectionFrame(data) {
    const frameInfo = document.getElementById('frameInfo');
    const fpsInfo = document.getElementById('fpsInfo');
    const detectionInfo = document.getElementById('detectionInfo');
    const realtimeFrame = document.getElementById('realtimeFrame');
    const videoPlaceholder = document.getElementById('videoPlaceholder');
    const outputVideoPreview = document.getElementById('outputVideoPreview');
    
    // 更新信息栏
    if (frameInfo && data.frameNum !== undefined) {
        frameInfo.textContent = `帧: ${data.frameNum}/${data.totalFrames || '?'}`;
    }
    if (fpsInfo && data.fps !== undefined) {
        const fpsValue = typeof data.fps === 'number' ? data.fps.toFixed(1) : data.fps;
        fpsInfo.textContent = `FPS: ${fpsValue}`;
    }
    if (detectionInfo && data.objectCount !== undefined) {
        detectionInfo.textContent = `检测中: ${data.objectCount} 辆`;
        detectionInfo.classList.add('detecting');
    }
    
    // 更新实时统计
    if (data.carCount !== undefined) {
        document.getElementById('carCount').textContent = data.carCount;
    }
    if (data.busCount !== undefined) {
        document.getElementById('busCount').textContent = data.busCount;
    }
    if (data.truckCount !== undefined) {
        document.getElementById('truckCount').textContent = data.truckCount;
    }
    if (data.totalCount !== undefined) {
        document.getElementById('totalDetections').textContent = data.totalCount;
    }
    
    // 显示实时帧图像
    if (data.frame && realtimeFrame) {
        // 设置图像源
        realtimeFrame.src = 'data:image/jpeg;base64,' + data.frame;
        realtimeFrame.classList.add('active');
        
        // 隐藏占位符和输出视频
        if (videoPlaceholder) {
            videoPlaceholder.classList.add('hidden');
        }
        if (outputVideoPreview) {
            outputVideoPreview.classList.remove('active');
        }
        
        console.log('实时帧已更新，帧号:', data.frameNum);
    }
}

/**
 * 停止检测
 */
async function stopDetection() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/collection/detection/stop`, {
            method: 'POST'
        });
        
        const result = await response.json();
        console.log('停止检测:', result);
        
        isDetecting = false;
        stopStatusPolling();
        stopFramePolling();
        updateDetectionUI(false);
        updateStatusDisplay('已停止', 'stopped');
        
        // 标记停止按钮完成
        markStepDone('stopBtn');
        
        // 移除检测中样式
        const videoWrapper = document.getElementById('videoPreviewWrapper');
        if (videoWrapper) {
            videoWrapper.classList.remove('detecting');
        }
        
        if (result.success) {
            alert('检测已停止');
        }
    } catch (error) {
        console.error('停止检测失败:', error);
        // 即使API调用失败也要更新本地状态
        isDetecting = false;
        stopStatusPolling();
        stopFramePolling();
        updateDetectionUI(false);
        updateStatusDisplay('已停止', 'stopped');
        
        // 标记停止按钮完成
        markStepDone('stopBtn');
        
        // 移除检测中样式
        const videoWrapper = document.getElementById('videoPreviewWrapper');
        if (videoWrapper) {
            videoWrapper.classList.remove('detecting');
        }
    }
}

/**
 * 开始轮询检测状态
 */
function startStatusPolling() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
    }
    
    statusCheckInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/collection/detection/status`);
            const data = await response.json();
            
            if (data.success) {
                updateProgress(data.progress || 50);
                updateStatusDisplay(data.message || '检测中...', 'detecting');
                
                if (data.status === 'completed') {
                    // 检测完成
                    stopStatusPolling();
                    stopFramePolling();
                    isDetecting = false;
                    updateDetectionUI(false);
                    updateStatusDisplay('检测完成', 'completed');
                    updateProgress(100);
                    
                    // 标记开始检测按钮完成
                    markStepDone('startBtn');
                    
                    // 移除检测中样式
                    const videoWrapper = document.getElementById('videoPreviewWrapper');
                    if (videoWrapper) {
                        videoWrapper.classList.remove('detecting');
                    }
                    
                    // 隐藏实时帧，显示输出视频
                    const realtimeFrame = document.getElementById('realtimeFrame');
                    if (realtimeFrame) {
                        realtimeFrame.classList.remove('active');
                    }
                    
                    // 自动加载输出视频
                    setTimeout(() => {
                        loadOutputVideo();
                    }, 500);
                    
                    // 加载检测结果
                    loadDetectionResults();
                    
                    alert('车辆检测完成！输出视频已生成，可在视频区域查看');
                } else if (data.status === 'failed' || data.status === 'error') {
                    // 检测失败
                    stopStatusPolling();
                    isDetecting = false;
                    updateDetectionUI(false);
                    updateStatusDisplay('检测失败', 'error');
                    
                    alert('检测失败: ' + data.message);
                }
            }
        } catch (error) {
            console.error('获取状态失败:', error);
        }
    }, 2000); // 每2秒检查一次
}

/**
 * 停止轮询
 */
function stopStatusPolling() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
        statusCheckInterval = null;
    }
}

/**
 * 更新检测UI状态
 */
function updateDetectionUI(detecting) {
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const videoFileInput = document.getElementById('videoFileInput');
    
    if (startBtn) {
        startBtn.disabled = detecting;
        startBtn.textContent = detecting ? '采集中...' : '开始交通流采集';
    }
    if (stopBtn) {
        stopBtn.disabled = !detecting;
    }
    if (videoFileInput) {
        videoFileInput.disabled = detecting;
    }
}

/**
 * 更新进度（保留接口但不显示进度条）
 */
function updateProgress(percent) {
    // 进度条已移除，此函数保留用于状态轮询兼容
    console.log('检测进度:', Math.round(percent) + '%');
}


/**
 * 加载检测结果
 */
async function loadDetectionResults() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/collection/get-results`);
        const data = await response.json();
        
        if (data.success) {
            displayResults(data.results);
            
            // 启用下载按钮
            const downloadBtn = document.getElementById('downloadResultBtn');
            if (downloadBtn && data.results.length > 0) {
                downloadBtn.disabled = false;
            }
        }
    } catch (error) {
        console.error('加载检测结果失败:', error);
    }
}

/**
 * 显示检测结果
 */
function displayResults(results) {
    const visualizationDisplay = document.getElementById('visualizationDisplay');
    const dataTableBody = document.getElementById('dataTableBody');
    
    // 分离统计文件和视频文件
    const statsFiles = results.filter(r => r.type === 'statistics');
    const videoFiles = results.filter(r => r.type === 'video');
    
    // 解析统计数据
    let totalCar = 0, totalBus = 0, totalTruck = 0, totalAll = 0;
    let tableRows = '';
    
    statsFiles.forEach(file => {
        if (file.content) {
            const lines = file.content.trim().split('\n');
            lines.forEach(line => {
                const parts = line.trim().split(/\s+/);
                if (parts.length >= 6) {
                    const period = parts[0];
                    const interval = parts[1];
                    const car = parseInt(parts[2]) || 0;
                    const bus = parseInt(parts[3]) || 0;
                    const truck = parseInt(parts[4]) || 0;
                    const total = parseInt(parts[5]) || 0;
                    
                    totalCar += car;
                    totalBus += bus;
                    totalTruck += truck;
                    totalAll += total;
                    
                    tableRows += `
                        <tr>
                            <td>${period}</td>
                            <td>${interval}</td>
                            <td>${car}</td>
                            <td>${bus}</td>
                            <td>${truck}</td>
                            <td>${total}</td>
                        </tr>
                    `;
                }
            });
        }
    });
    
    // 更新统计卡片
    document.getElementById('carCount').textContent = totalCar;
    document.getElementById('busCount').textContent = totalBus;
    document.getElementById('truckCount').textContent = totalTruck;
    document.getElementById('totalDetections').textContent = totalAll;
    
    // 更新表格
    if (tableRows) {
        dataTableBody.innerHTML = tableRows;
    } else {
        dataTableBody.innerHTML = '<tr class="no-data"><td colspan="6">暂无检测数据</td></tr>';
    }
    
    // 更新可视化区域
    let visualContent = `
        <div class="results-container" style="padding: 20px;">
            <h4 style="color: #2C5AA0; margin-bottom: 15px;">检测结果汇总</h4>
            
            <!-- 统计摘要 -->
            <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px;">
                <div style="background: linear-gradient(135deg, #2C5AA0 0%, #1e3d72 100%); padding: 15px; border-radius: 10px; color: white; text-align: center;">
                    <div style="font-size: 24px; font-weight: bold;">${totalCar}</div>
                    <div style="font-size: 12px; margin-top: 5px;">🚗 小汽车</div>
                </div>
                <div style="background: linear-gradient(135deg, #2C5AA0 0%, #1e3d72 100%); padding: 15px; border-radius: 10px; color: white; text-align: center;">
                    <div style="font-size: 24px; font-weight: bold;">${totalBus}</div>
                    <div style="font-size: 12px; margin-top: 5px;">🚌 公交车</div>
                </div>
                <div style="background: linear-gradient(135deg, #2C5AA0 0%, #1e3d72 100%); padding: 15px; border-radius: 10px; color: white; text-align: center;">
                    <div style="font-size: 24px; font-weight: bold;">${totalTruck}</div>
                    <div style="font-size: 12px; margin-top: 5px;">🚚 卡车</div>
                </div>
                <div style="background: linear-gradient(135deg, #2C5AA0 0%, #1e3d72 100%); padding: 15px; border-radius: 10px; color: white; text-align: center;">
                    <div style="font-size: 24px; font-weight: bold;">${totalAll}</div>
                    <div style="font-size: 12px; margin-top: 5px;">📈 总流量</div>
                </div>
            </div>
    `;
    
    // 显示统计文件列表
    if (statsFiles.length > 0) {
        visualContent += `
            <div style="margin-bottom: 20px;">
                <h5 style="color: #333; margin-bottom: 10px;">📄 统计文件</h5>
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
        `;
        statsFiles.forEach(file => {
            visualContent += `
                <div style="display: flex; align-items: center; padding: 8px; border-bottom: 1px solid #eee;">
                    <span style="margin-right: 10px;">📊</span>
                    <span style="flex: 1;">${file.name}</span>
                    <button onclick="downloadFile('${file.name}')" style="padding: 5px 10px; background: #2C5AA0; color: white; border: none; border-radius: 4px; cursor: pointer;">下载</button>
                </div>
            `;
        });
        visualContent += `</div></div>`;
    }
    
    // 显示视频文件列表
    if (videoFiles.length > 0) {
        visualContent += `
            <div>
                <h5 style="color: #333; margin-bottom: 10px;">🎬 输出视频</h5>
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
        `;
        videoFiles.forEach(file => {
            visualContent += `
                <div style="display: flex; align-items: center; padding: 8px; border-bottom: 1px solid #eee;">
                    <span style="margin-right: 10px;">🎬</span>
                    <span style="flex: 1;">${file.name} (${file.size})</span>
                    <button onclick="downloadFile('${file.name}')" style="padding: 5px 10px; background: #2C5AA0; color: white; border: none; border-radius: 4px; cursor: pointer;">下载</button>
                </div>
            `;
        });
        visualContent += `</div></div>`;
    }
    
    if (statsFiles.length === 0 && videoFiles.length === 0) {
        visualContent += `
            <div style="text-align: center; padding: 40px; color: #666;">
                <div style="font-size: 48px; margin-bottom: 15px;">📭</div>
                <p>暂无检测结果</p>
                <p style="font-size: 12px;">请先选择视频并开始交通流采集</p>
            </div>
        `;
    }
    
    visualContent += `</div>`;
    
    if (visualizationDisplay) {
        visualizationDisplay.innerHTML = visualContent;
    }
}

/**
 * 下载文件
 */
function downloadFile(filename) {
    window.open(collectionSessionUrl(`/download/${encodeURIComponent(filename)}`), '_blank');
}

/**
 * 下载所有结果
 */
async function downloadResults() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/collection/get-results`);
        const data = await response.json();
        
        if (data.success && data.results.length > 0) {
            // 下载第一个统计文件
            const statsFile = data.results.find(r => r.type === 'statistics');
            if (statsFile) {
                downloadFile(statsFile.name);
            }
        } else {
            alert('暂无可下载的结果文件');
        }
    } catch (error) {
        console.error('下载失败:', error);
        alert('下载失败: ' + error.message);
    }
}

/**
 * 重置参数
 */
function resetParameters() {
    // 如果正在检测，先停止
    if (isDetecting) {
        stopDetection();
    }
    
    // 调用后端重置接口，清理共享文件和任务状态
    fetch(`${API_BASE_URL}/api/collection/detection/reset`, { method: 'POST' })
        .catch(err => console.error('后端重置失败:', err));
    
    // 重置文件选择
    const videoFileInput = document.getElementById('videoFileInput');
    const fileText = document.getElementById('fileText');
    const fileLabel = document.querySelector('.file-input-label');
    const videoInfo = document.getElementById('videoInfo');
    
    if (videoFileInput) {
        videoFileInput.value = '';
    }
    selectedVideoFile = null;
    useDefaultVideo = true;
    selectedScenario = scenarioCatalog[0] || null;
    if (fileText) {
        fileText.textContent = '点击选择视频文件...';
    }
    if (fileLabel) {
        fileLabel.classList.remove('has-file');
    }
    // 重置视频来源选择
    const videoSourceSelect = document.getElementById('videoSourceSelect');
    if (videoSourceSelect) {
        videoSourceSelect.value = 'default';
    }
    if (videoInfo) {
        updateDefaultVideoDisplay();
        if (selectedScenario) selectScenario(selectedScenario);
    }
    loadDefaultVideoInfo();
    const customFileSection = document.getElementById('customFileSection');
    if (customFileSection) {
        customFileSection.style.display = 'none';
    }

    // 重置统计显示
    document.getElementById('carCount').textContent = '0';
    document.getElementById('busCount').textContent = '0';
    document.getElementById('truckCount').textContent = '0';
    document.getElementById('totalDetections').textContent = '0';
    
    // 重置表格
    document.getElementById('dataTableBody').innerHTML = '<tr class="no-data"><td colspan="6">暂无检测数据，请先进行车辆检测</td></tr>';
    
    // 重置可视化区域
    const visualizationDisplay = document.getElementById('visualizationDisplay');
    if (visualizationDisplay) {
        visualizationDisplay.innerHTML = `
            <div class="placeholder-content">
                <div class="placeholder-icon">🎬</div>
                <p>检测结果展示区</p>
                <p class="placeholder-hint">完成检测后显示输出视频和统计结果</p>
            </div>
        `;
    }
    
    // 重置视频预览区域
    hideVideoPreview();
    
    // 隐藏输出视频和实时帧
    const outputVideoPreview = document.getElementById('outputVideoPreview');
    if (outputVideoPreview) {
        outputVideoPreview.classList.remove('active');
        outputVideoPreview.src = '';
    }
    
    const realtimeFrame = document.getElementById('realtimeFrame');
    if (realtimeFrame) {
        realtimeFrame.classList.remove('active');
        realtimeFrame.src = '';
    }
    
    // 显示占位符
    const videoPlaceholder = document.getElementById('videoPlaceholder');
    if (videoPlaceholder) {
        videoPlaceholder.classList.remove('hidden');
    }
    
    const frameInfo = document.getElementById('frameInfo');
    const fpsInfo = document.getElementById('fpsInfo');
    const detectionInfo = document.getElementById('detectionInfo');
    if (frameInfo) frameInfo.textContent = '帧: 0/0';
    if (fpsInfo) fpsInfo.textContent = 'FPS: --';
    if (detectionInfo) {
        detectionInfo.textContent = '检测中: 0 辆';
        detectionInfo.classList.remove('detecting');
    }
    
    // 移除检测中样式
    const videoWrapper = document.getElementById('videoPreviewWrapper');
    if (videoWrapper) {
        videoWrapper.classList.remove('detecting');
    }
    
    // 重置所有步骤按钮样式（恢复为蓝底）
    resetAllStepButtons();
    
    // 禁用下载按钮
    const downloadBtn = document.getElementById('downloadResultBtn');
    if (downloadBtn) {
        downloadBtn.disabled = true;
    }
    
    // 重置UI状态
    updateDetectionUI(false);
    updateStatusDisplay('已重置', 'ready');

    alert('已重置为初始状态');
}

// 页面卸载时停止检测
window.addEventListener('beforeunload', function() {
    if (isDetecting) {
        stopDetection();
    }
    stopStatusPolling();
});



/**
 * 加载输出视频
 */
async function loadOutputVideo() {
    const outputVideoPreview = document.getElementById('outputVideoPreview');
    const videoPlaceholder = document.getElementById('videoPlaceholder');
    
    try {
        // 尝试从后端获取输出视频
        const response = await fetch(`${API_BASE_URL}/api/collection/output-video`);
        const data = await response.json();
        
        if (data.success && data.videoUrl) {
            if (outputVideoPreview) {
                outputVideoPreview.src = data.videoUrl;
                outputVideoPreview.classList.add('active');
                outputVideoPreview.load();
            }
            if (videoPlaceholder) {
                videoPlaceholder.classList.add('hidden');
            }
            console.log('输出视频加载成功:', data.videoUrl);
        } else {
            // 如果后端没有返回视频URL，尝试直接访问默认路径
            const defaultOutputUrl = collectionSessionUrl('/outputs/output.mp4');
            if (outputVideoPreview) {
                outputVideoPreview.src = defaultOutputUrl;
                outputVideoPreview.classList.add('active');
                outputVideoPreview.load();
                
                // 监听加载错误
                outputVideoPreview.onerror = function() {
                    console.error('输出视频加载失败');
                    alert('输出视频尚未生成或无法访问，请先完成检测');
                    outputVideoPreview.classList.remove('active');
                    if (videoPlaceholder) {
                        videoPlaceholder.classList.remove('hidden');
                    }
                };
            }
            if (videoPlaceholder) {
                videoPlaceholder.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('加载输出视频失败:', error);
        // 尝试直接访问静态文件
        const defaultOutputUrl = collectionSessionUrl('/outputs/output.mp4');
        if (outputVideoPreview) {
            outputVideoPreview.src = defaultOutputUrl;
            outputVideoPreview.classList.add('active');
            outputVideoPreview.load();
        }
        if (videoPlaceholder) {
            videoPlaceholder.classList.add('hidden');
        }
    }
}

/**
 * 刷新输出视频
 */
function refreshOutputVideo() {
    const outputVideoPreview = document.getElementById('outputVideoPreview');
    
    if (outputVideoPreview) {
        // 添加时间戳避免缓存
        const timestamp = new Date().getTime();
    const baseUrl = collectionSessionUrl('/outputs/output.mp4');
        outputVideoPreview.src = `${baseUrl}&t=${timestamp}`;
        outputVideoPreview.load();
        console.log('刷新输出视频');
    }
    
    // 同时刷新检测结果
    loadDetectionResults();
}

/**
 * 加载数据统计 - 从检测结果文件读取并显示
 */
async function loadStatistics() {
    console.log('加载数据统计...');
    updateStatusDisplay('正在加载统计数据...', 'detecting');
    
    try {
        // 从后端获取统计数据
        const response = await fetch(`${API_BASE_URL}/api/collection/statistics`);
        const data = await response.json();
        
        if (data.success) {
            // 更新车辆流量统计卡片
            document.getElementById('carCount').textContent = data.carCount || 0;
            document.getElementById('busCount').textContent = data.busCount || 0;
            document.getElementById('truckCount').textContent = data.truckCount || 0;
            document.getElementById('totalDetections').textContent = data.totalCount || 0;
            
            // 更新分时段统计表格
            const dataTableBody = document.getElementById('dataTableBody');
            if (data.timeSlots && data.timeSlots.length > 0) {
                let tableRows = '';
                data.timeSlots.forEach((slot, index) => {
                    tableRows += `
                        <tr>
                            <td>${slot.period || '第' + (index + 1) + '组'}</td>
                            <td>${slot.interval || '--'}</td>
                            <td>${slot.car || 0}</td>
                            <td>${slot.bus || 0}</td>
                            <td>${slot.truck || 0}</td>
                            <td>${slot.total || 0}</td>
                        </tr>
                    `;
                });
                dataTableBody.innerHTML = tableRows;
            } else {
                dataTableBody.innerHTML = '<tr class="no-data"><td colspan="6">暂无分时段数据</td></tr>';
            }
            
            updateStatusDisplay('统计数据已加载', 'completed');
            // 标记数据统计按钮完成
            markStepDone('statsBtn');
            alert(`数据统计完成！\n\n小汽车: ${data.carCount || 0}\n公交车: ${data.busCount || 0}\n卡车: ${data.truckCount || 0}\n总计: ${data.totalCount || 0}`);
        } else {
            throw new Error(data.message || '获取统计数据失败');
        }
    } catch (error) {
        console.error('加载统计数据失败:', error);
        
        // 尝试从本地检测数据文件读取
        try {
            const frameResponse = await fetch(`${API_BASE_URL}/api/collection/detection/frame`);
            const frameData = await frameResponse.json();
            
            if (frameData.success && frameData.totalCount > 0) {
                document.getElementById('carCount').textContent = frameData.carCount || 0;
                document.getElementById('busCount').textContent = frameData.busCount || 0;
                document.getElementById('truckCount').textContent = frameData.truckCount || 0;
                document.getElementById('totalDetections').textContent = frameData.totalCount || 0;
                
                updateStatusDisplay('统计数据已加载', 'completed');
                // 标记数据统计按钮完成
                markStepDone('statsBtn');
                alert(`数据统计完成！\n\n小汽车: ${frameData.carCount || 0}\n公交车: ${frameData.busCount || 0}\n卡车: ${frameData.truckCount || 0}\n总计: ${frameData.totalCount || 0}`);
            } else {
                updateStatusDisplay('无统计数据', 'error');
                alert('暂无检测统计数据，请先运行检测');
            }
        } catch (e) {
            updateStatusDisplay('加载失败', 'error');
            alert('加载统计数据失败: ' + error.message);
        }
    }
}


