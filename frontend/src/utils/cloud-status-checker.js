/**
 * 云端平台连接状态检测模块
 * 用于检测云端教学管理平台后端是否在线
 */

// 云端 API 配置
const CLOUD_API_URL = window.ZXYK_CLOUD_API_URL || (window.location.protocol + '//' + window.location.hostname + ':9100');
const CLOUD_HEALTH_ENDPOINT = '/api/cloud/health';
const CHECK_INTERVAL = 10000; // 10秒检测一次

/**
 * 创建云端连接状态检测器
 * @param {Object} options 配置选项
 * @param {HTMLElement} options.dotElement 状态指示点元素
 * @param {HTMLElement} options.textElement 状态文本元素
 * @param {Function} options.onStatusChange 状态变化回调 (isOnline) => void
 * @param {boolean} options.autoStart 是否自动开始检测，默认 true
 * @returns {Object} 检测器对象，包含 start/stop/check 方法
 */
function createCloudStatusChecker(options) {
    const {
        dotElement,
        textElement,
        onStatusChange,
        autoStart = true
    } = options;

    let intervalId = null;
    let lastStatus = null;

    /**
     * 执行一次云端连接检测
     */
    async function check() {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000); // 5秒超时

            const response = await fetch(CLOUD_API_URL + CLOUD_HEALTH_ENDPOINT, {
                method: 'GET',
                signal: controller.signal,
                // 忽略 SSL 证书验证（本地开发环境）
                mode: 'cors',
                cache: 'no-cache'
            });

            clearTimeout(timeoutId);

            if (response.ok) {
                const data = await response.json();
                if (data.status === 'ok') {
                    updateStatus(true, '云端平台已连接');
                    return true;
                }
            }

            updateStatus(false, '云端平台响应异常');
            return false;
        } catch (error) {
            // 连接失败
            if (error.name === 'AbortError') {
                updateStatus(false, '云端平台连接超时');
            } else {
                updateStatus(false, '云端平台未启动');
            }
            return false;
        }
    }

    /**
     * 更新状态显示
     */
    function updateStatus(isOnline, message) {
        // 只在状态变化时触发回调
        if (lastStatus !== isOnline && onStatusChange) {
            onStatusChange(isOnline);
        }
        lastStatus = isOnline;

        if (dotElement) {
            dotElement.style.background = isOnline ? '#28a745' : '#dc3545';
        }

        if (textElement) {
            textElement.textContent = message;
            textElement.style.color = isOnline ? '#28a745' : '#dc3545';
        }
    }

    /**
     * 开始定时检测
     */
    function start() {
        if (intervalId) return; // 已经在运行

        // 立即执行一次检测
        check();

        // 设置定时检测
        intervalId = setInterval(check, CHECK_INTERVAL);
    }

    /**
     * 停止定时检测
     */
    function stop() {
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
    }

    // 自动开始
    if (autoStart) {
        start();
    }

    // 返回控制接口
    return {
        start,
        stop,
        check,
        getStatus: () => lastStatus
    };
}

/**
 * 简化版：创建带 UI 的云端状态检测器
 * 自动创建状态显示元素并插入到指定容器
 * @param {HTMLElement} container 容器元素
 * @param {Object} options 配置选项
 * @returns {Object} 检测器对象
 */
function createCloudStatusUI(container, options = {}) {
    const {
        position = 'append', // 'append' | 'prepend'
        showLabel = true,
        onStatusChange
    } = options;

    // 创建状态显示元素
    const statusDiv = document.createElement('div');
    statusDiv.style.cssText = 'margin-top:15px;text-align:center;font-size:13px;color:#999;';

    const dotSpan = document.createElement('span');
    dotSpan.style.cssText = 'display:inline-block;width:8px;height:8px;border-radius:50%;background:#ccc;margin-right:6px;vertical-align:middle;';

    const textSpan = document.createElement('span');
    textSpan.textContent = '正在检测云端平台...';

    if (showLabel) {
        const labelSpan = document.createElement('span');
        labelSpan.textContent = '云端平台：';
        labelSpan.style.color = '#666';
        statusDiv.appendChild(labelSpan);
    }

    statusDiv.appendChild(dotSpan);
    statusDiv.appendChild(textSpan);

    // 插入到容器
    if (position === 'prepend') {
        container.insertBefore(statusDiv, container.firstChild);
    } else {
        container.appendChild(statusDiv);
    }

    // 创建检测器
    const checker = createCloudStatusChecker({
        dotElement: dotSpan,
        textElement: textSpan,
        onStatusChange,
        autoStart: true
    });

    return {
        ...checker,
        element: statusDiv,
        remove: () => statusDiv.remove()
    };
}

// 导出（兼容不同的模块系统）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { createCloudStatusChecker, createCloudStatusUI };
}
if (typeof window !== 'undefined') {
    window.CloudStatusChecker = { createCloudStatusChecker, createCloudStatusUI };
}
