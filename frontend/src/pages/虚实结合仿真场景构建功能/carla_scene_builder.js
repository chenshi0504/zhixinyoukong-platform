/**
 * 虚实结合仿真场景构建 - JavaScript
 * 支持Town05 HIL协同仿真与校园底图CARLA-SUMO联合仿真。
 */

const API_BASE = '';
let isSimRunning = false;
let isDemoMode = false;
let statusPollInterval = null;
let logPollInterval = null;
let trajectoryPoints = [];
let scenarios = [];
let selectedSceneId = null;
let nativeVicUrl = getServerUrl(8090);
let nativeVicFrameAttached = false;

function getServerUrl(port) {
    var protocol = window.location.protocol || 'http:';
    var host = window.location.hostname || '127.0.0.1';
    return protocol + '//' + host + ':' + port;
}

function normalizeServerUrl(url, fallbackPort) {
    if (!url) return getServerUrl(fallbackPort);
    try {
        var parsed = new URL(url, window.location.href);
        if (parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost') {
            parsed.hostname = window.location.hostname || parsed.hostname;
        }
        return parsed.toString().replace(/\/$/, '');
    } catch (e) {
        return getServerUrl(fallbackPort);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    bindEvents();
    navigate('home');
    checkServer();
    loadScenarios();
    drawEmptyCanvas();
    loadSoftwareStatus();
});

function bindEvents() {
    document.getElementById('backBtn').addEventListener('click', function() { window.history.back(); });
    document.querySelectorAll('[data-page]').forEach(function(link) {
        link.addEventListener('click', function(event) {
            event.preventDefault();
            navigate(link.dataset.page || 'home');
        });
    });
    document.getElementById('startMqttBtn').addEventListener('click', startMqtt);
    document.getElementById('startReceiverBtn').addEventListener('click', startReceiver);
    document.getElementById('startSimBtn').addEventListener('click', startSimulation);
    document.getElementById('stopSimBtn').addEventListener('click', stopSimulation);
    document.getElementById('resetBtn').addEventListener('click', resetAll);
    document.getElementById('loadTrajectoryBtn').addEventListener('click', loadDemoTrajectory);
    document.getElementById('clearLogBtn').addEventListener('click', clearLogs);
    document.getElementById('refreshFilesBtn').addEventListener('click', loadOutputFiles);
    document.getElementById('refreshSoftwareBtn').addEventListener('click', loadSoftwareStatus);
    document.getElementById('refreshPreviewBtn').addEventListener('click', refreshPreview);
    document.getElementById('startNativeVicBtn').addEventListener('click', startNativeVicSim);
    document.getElementById('startNativeVicBtnInline').addEventListener('click', startNativeVicSim);
    document.getElementById('openNativeVicBtn').addEventListener('click', function() {
        window.open(nativeVicUrl, '_blank', 'noopener');
        attachNativeVicFrame();
        pollNativeVicStatus(4);
    });
}

function navigate(page) {
    var target = page || 'home';
    document.querySelectorAll('.page').forEach(function(panel) {
        panel.classList.toggle('active', panel.id === 'page-' + target);
    });
    document.querySelectorAll('.nav-links a[data-page]').forEach(function(link) {
        link.classList.toggle('active', link.dataset.page === target);
    });
    if (target === 'scenario') {
        setTimeout(function() {
            if (trajectoryPoints.length) drawTrajectory(trajectoryPoints);
            else drawEmptyCanvas();
        }, 40);
    }
}

async function checkServer() {
    var el = document.getElementById('serverStatus');
    var badge = document.getElementById('demoBadge');
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/health');
        if (!resp.ok) throw new Error('health failed');
        var data = await resp.json();
        el.textContent = '服务器: 已连接 ✓';
        el.style.color = '#28a745';
        isDemoMode = !!data.demo_mode;
        if (data.native && data.native.url) nativeVicUrl = normalizeServerUrl(data.native.url, 8090);
        updateNativeVicFrame(data.native || null);
        badge.style.display = isDemoMode ? 'inline-block' : 'none';
        if (isDemoMode) badge.textContent = '可交互演示/环境缺项';
    } catch (e) {
        el.textContent = '服务器: 未连接 ✗';
        el.style.color = '#dc3545';
    }
}

function updateNativeVicFrame(native) {
    var frame = document.getElementById('nativeVicFrame');
    var status = document.getElementById('nativeVicStatus');
    if (!frame || !status) return;
    if (native && native.url) nativeVicUrl = normalizeServerUrl(native.url, 8090);
    if (nativeVicFrameAttached && frame.getAttribute('src') !== nativeVicUrl) frame.src = nativeVicUrl;
    var ready = native && native.running;
    var starting = native && native.starting;
    status.textContent = ready ? 'VIC-Sim 原生服务已连接：' + nativeVicUrl : (starting ? 'VIC-Sim 正在后台启动，页面已打开，稍后自动连接' : 'VIC-Sim 原生服务未启动，可点击启动/连接');
    status.classList.toggle('online', !!ready);
}

function attachNativeVicFrame() {
    var frame = document.getElementById('nativeVicFrame');
    if (!frame) return;
    nativeVicFrameAttached = true;
    if (frame.getAttribute('src') !== nativeVicUrl) frame.src = nativeVicUrl;
}

async function loadNativeVicStatus() {
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/native/status', { cache: 'no-store' });
        if (!resp.ok) throw new Error('native status failed');
        var data = await resp.json();
        updateNativeVicFrame(data);
    } catch (e) {
        updateNativeVicFrame({ url: nativeVicUrl, running: false });
    }
}

function pollNativeVicStatus(times, delay) {
    var remaining = Number(times || 1);
    var wait = Number(delay || 1400);
    if (remaining <= 0) return;
    setTimeout(function() {
        loadNativeVicStatus();
        pollNativeVicStatus(remaining - 1, Math.min(wait + 400, 3000));
    }, wait);
}

async function startNativeVicSim() {
    var status = document.getElementById('nativeVicStatus');
    window.open(nativeVicUrl, '_blank', 'noopener');
    attachNativeVicFrame();
    if (status) status.textContent = '已打开 VIC-Sim 原生页面，正在后台启动/连接...';
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/native/start', { method: 'POST' });
        var data = await resp.json();
        updateNativeVicFrame(data);
        addLocalLog(data.message || 'VIC-Sim 原生服务启动命令已发送', data.success ? 'success' : 'info');
        pollNativeVicStatus(8);
    } catch (e) {
        addLocalLog('VIC-Sim 原生服务启动失败: ' + e.message, 'error');
        pollNativeVicStatus(3);
    }
}

async function loadScenarios() {
    var list = document.getElementById('scenarioList');
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/scenarios');
        var data = await resp.json();
        scenarios = data.scenarios || [];
        if (!scenarios.length) {
            list.innerHTML = '<p class="hint-text">未检测到可用联合仿真场景</p>';
            return;
        }
        list.innerHTML = scenarios.map(function(scene, idx) {
            var missing = Object.keys(scene.resource_status || {}).filter(function(key) {
                return !scene.resource_status[key].exists;
            });
            var statusText = missing.length ? '资源待补齐' : '资源就绪';
            return '<button type="button" class="scenario-option' + (idx === 0 ? ' selected' : '') + '" data-scene-id="' + escapeHtml(scene.id) + '">' +
                '<span class="scenario-title">' + escapeHtml(scene.name) + '</span>' +
                '<span class="scenario-subtitle">' + escapeHtml(scene.subtitle || '') + '</span>' +
                '<span class="scenario-foot">' +
                    '<span>' + escapeHtml(scene.scene_type || '') + '</span>' +
                    '<span>' + statusText + '</span>' +
                '</span>' +
            '</button>';
        }).join('');
        document.querySelectorAll('.scenario-option').forEach(function(btn) {
            btn.addEventListener('click', function() {
                selectScene(btn.dataset.sceneId);
            });
        });
        selectScene(scenarios[0].id);
        highlightStep(1);
    } catch (err) {
        list.innerHTML = '<p class="hint-text">场景加载失败：' + escapeHtml(err.message) + '</p>';
        addLocalLog('场景加载失败: ' + err.message, 'error');
    }
}

function selectScene(sceneId) {
    selectedSceneId = sceneId;
    document.querySelectorAll('.scenario-option').forEach(function(btn) {
        btn.classList.toggle('selected', btn.dataset.sceneId === sceneId);
    });

    var scene = getSelectedScene();
    if (!scene) return;

    document.getElementById('selectedSceneMeta').innerHTML =
        '<strong>' + escapeHtml(scene.name) + '</strong><br>' +
        'CARLA: ' + escapeHtml(scene.carla_map || '-') + ' · SUMO: ' + escapeHtml(lastPathPart(scene.sumo_config || '-'));
    var title = document.getElementById('selectedSceneTitle');
    if (title) title.textContent = scene.name;
    document.getElementById('routeInput').value = scene.default_route || '';
    document.getElementById('targetSpeed').value = scene.default_speed || 5;
    document.getElementById('routeHint').textContent = '当前场景默认路线/车辆标识：' + (scene.default_route || '--');
    document.getElementById('sceneIntro').textContent = (scene.logic || []).join('');

    var objectiveList = document.getElementById('objectiveList');
    objectiveList.innerHTML = (scene.objectives || []).map(function(item) {
        return '<li>' + escapeHtml(item) + '</li>';
    }).join('');

    refreshPreview();
    trajectoryPoints = [];
    drawEmptyCanvas('当前选择：' + scene.name + '，可加载演示轨迹或启动联合仿真。');
    addLocalLog('已选择场景：' + scene.name, 'info');
}

function getSelectedScene() {
    return scenarios.find(function(scene) { return scene.id === selectedSceneId; }) || scenarios[0];
}

function refreshPreview() {
    var scene = getSelectedScene();
    if (!scene) return;
    document.getElementById('sumoPreviewTag').textContent = scene.name;
    document.getElementById('carlaPreviewTag').textContent = nativeVicUrl.replace(/^https?:\/\//, '');
    attachNativeVicFrame();
    loadNativeVicStatus();
}

function updateStatus(text) {
    var el = document.getElementById('statusValue');
    if (el) el.textContent = text;
}

function markStepDone(btnId) {
    var btn = document.getElementById(btnId);
    if (btn && !btn.classList.contains('step-done')) btn.classList.add('step-done');
}

function highlightStep(stepNum) {
    document.querySelectorAll('.step-item').forEach(function(el) {
        var s = parseInt(el.dataset.step, 10);
        if (s <= stepNum) el.classList.add('active');
    });
}

function setCardActive(cardId) {
    var card = document.getElementById(cardId);
    if (card) card.classList.add('card-active');
}

function setArchNodeActive(nodeId) {
    var node = document.getElementById(nodeId);
    if (node) node.classList.add('arch-active');
}

function showProgress(show) {
    document.getElementById('progressContainer').style.display = show ? 'flex' : 'none';
}

function updateProgress(current, total) {
    if (!total) return;
    var pct = Math.round((current / total) * 100);
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressText').textContent = pct + '% (' + current + '/' + total + ')';
}

function formatTime(seconds) {
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return m > 0 ? m + '分' + s + '秒' : s + '秒';
}

function addLocalLog(msg, level) {
    var container = document.getElementById('logContainer');
    var empty = container.querySelector('.log-empty');
    if (empty) empty.remove();

    var div = document.createElement('div');
    div.className = 'log-line log-' + (level || 'info');
    var time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    div.textContent = '[' + time + '] ' + msg;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function clearLogs() {
    document.getElementById('logContainer').innerHTML = '<div class="log-empty">等待操作...</div>';
}

async function pollLogs() {
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/logs');
        var data = await resp.json();
        if (data.success && data.logs) {
            var container = document.getElementById('logContainer');
            var existingCount = container.querySelectorAll('.log-line.log-server').length;
            var newLogs = data.logs.slice(existingCount);
            if (newLogs.length > 0) {
                var empty = container.querySelector('.log-empty');
                if (empty) empty.remove();
                newLogs.forEach(function(log) {
                    var div = document.createElement('div');
                    div.className = 'log-line log-server log-' + (log.level || 'info');
                    div.textContent = '[' + log.time + '] ' + log.message;
                    container.appendChild(div);
                });
                container.scrollTop = container.scrollHeight;
            }
        }
    } catch (e) { /* ignore */ }
}

async function startMqtt() {
    updateStatus('正在准备同步通道...');
    addLocalLog('正在准备CARLA-SUMO同步通道...', 'info');
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/start-mqtt', { method: 'POST' });
        var data = await resp.json();
        if (!data.success) throw new Error(data.message || '准备失败');
        updateStatus('同步通道已准备');
        markStepDone('startMqttBtn');
        document.getElementById('mqttStatus').textContent = '运行中';
        setCardActive('cardMqtt');
        setArchNodeActive('archMqtt');
        highlightStep(1);
        addLocalLog(data.message || '同步通道已准备', 'info');
        startLogPolling();
    } catch (err) {
        addLocalLog('同步通道准备异常: ' + err.message, 'error');
        alert('准备失败: ' + err.message);
    }
}

async function startReceiver() {
    updateStatus('正在启动效果展示传输...');
    addLocalLog('正在启动SUMO/CARLA界面图传输...', 'info');
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/start-receiver', { method: 'POST' });
        var data = await resp.json();
        if (!data.success) throw new Error(data.message || '启动失败');
        refreshPreview();
        updateStatus('效果展示传输已启动');
        markStepDone('startReceiverBtn');
        document.getElementById('receiverStatus').textContent = '运行中';
        setCardActive('cardReceiver');
        setArchNodeActive('archReceiver');
        highlightStep(2);
        addLocalLog(data.message || '效果展示传输已启动', 'info');
    } catch (err) {
        addLocalLog('效果展示传输异常: ' + err.message, 'error');
        alert('启动失败: ' + err.message);
    }
}

async function startSimulation() {
    if (isSimRunning) { alert('仿真已在运行中'); return; }
    var scene = getSelectedScene();
    if (!scene) { alert('请先选择场景'); return; }

    updateStatus('正在启动联合仿真...');
    addLocalLog('正在启动SUMO-CARLA联合仿真: ' + scene.name, 'info');
    var route = document.getElementById('routeInput').value.trim();
    var speed = parseFloat(document.getElementById('targetSpeed').value);

    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scene_id: scene.id,
                route: route,
                speed: speed,
                sumo_gui: true,
                auto_launch_carla: true,
                mode: 'auto'
            })
        });
        var data = await resp.json();
        if (!data.success) throw new Error(data.message || '启动失败');

        isSimRunning = true;
        isDemoMode = !!data.demo;
        document.getElementById('demoBadge').style.display = isDemoMode ? 'inline-block' : 'none';
        document.getElementById('demoBadge').textContent = isDemoMode ? '演示模式' : '真实联调';
        updateStatus('联合仿真运行中');
        markStepDone('startSimBtn');
        document.getElementById('sumoStatus').textContent = '运行中';
        document.getElementById('cavStatus').textContent = '同步中';
        setCardActive('cardSumo');
        setCardActive('cardCav');
        setArchNodeActive('archSumo');
        setArchNodeActive('archDevice');
        highlightStep(3);
        showProgress(true);
        document.getElementById('cavRealtimeSection').style.display = 'block';

        addLocalLog(data.message + (data.demo ? '（演示模式）' : '（真实进程已启动）'), 'info');
        if (data.missing && data.missing.length) {
            addLocalLog('环境缺项: ' + data.missing.join('、'), 'info');
        }
        trajectoryPoints = [];
        refreshPreview();
        startStatusPolling();
        startLogPolling();
        loadOutputFiles();
    } catch (err) {
        addLocalLog('联合仿真启动异常: ' + err.message, 'error');
        alert('启动失败: ' + err.message);
        updateStatus('启动失败');
    }
}

async function stopSimulation() {
    addLocalLog('正在停止仿真...', 'info');
    try {
        await fetch(API_BASE + '/api/carla-sim/stop', { method: 'POST' });
        isSimRunning = false;
        updateStatus('已停止');
        document.getElementById('sumoStatus').textContent = '已停止';
        document.getElementById('cavStatus').textContent = '已停止';
        stopStatusPolling();
        stopLogPolling();
        showProgress(false);
        addLocalLog('仿真已停止', 'info');
        loadOutputFiles();
        if (trajectoryPoints.length > 0) drawTrajectory(trajectoryPoints);
    } catch (err) {
        console.error('停止失败:', err);
    }
}

function resetAll() {
    stopSimulation();
    isSimRunning = false;
    isDemoMode = false;
    document.getElementById('demoBadge').style.display = 'none';
    document.getElementById('demoBadge').textContent = '演示模式';
    updateStatus('就绪');
    showProgress(false);

    ['sumoStatus', 'mqttStatus', 'receiverStatus'].forEach(function(id) {
        document.getElementById(id).textContent = '未启动';
    });
    document.getElementById('cavStatus').textContent = '未创建';

    document.querySelectorAll('.card-active').forEach(function(el) { el.classList.remove('card-active'); });
    document.querySelectorAll('.arch-active').forEach(function(el) { el.classList.remove('arch-active'); });
    ['startMqttBtn', 'startReceiverBtn', 'startSimBtn'].forEach(function(id) {
        var btn = document.getElementById(id);
        if (btn) btn.classList.remove('step-done');
    });
    document.querySelectorAll('.step-item').forEach(function(el) { el.classList.remove('active'); });
    document.getElementById('cavRealtimeSection').style.display = 'none';
    document.getElementById('outputFiles').innerHTML =
        '<p class="hint-text">仿真启动后将在 output/ 目录生成轨迹与摘要文件</p>';

    trajectoryPoints = [];
    drawEmptyCanvas();
    clearLogs();
    if (selectedSceneId) highlightStep(1);
}

function startStatusPolling() {
    if (statusPollInterval) clearInterval(statusPollInterval);
    pollStatus();
    statusPollInterval = setInterval(pollStatus, 1500);
}

function stopStatusPolling() {
    if (statusPollInterval) { clearInterval(statusPollInterval); statusPollInterval = null; }
}

function startLogPolling() {
    if (logPollInterval) clearInterval(logPollInterval);
    pollLogs();
    logPollInterval = setInterval(pollLogs, 2000);
}

function stopLogPolling() {
    if (logPollInterval) { clearInterval(logPollInterval); logPollInterval = null; }
}

async function pollStatus() {
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/status');
        var data = await resp.json();

        if (data.step && data.total_steps) updateProgress(data.step, data.total_steps);

        if (data.cav) {
            document.getElementById('cavEdge').textContent = data.cav.edge || '--';
            document.getElementById('cavSpeed').textContent = (data.cav.speed || '--') + ' m/s';
            document.getElementById('cavX').textContent = data.cav.x || '--';
            document.getElementById('cavY').textContent = data.cav.y || '--';
            document.getElementById('cavHeading').textContent = (data.cav.heading || '--') + '\u00B0';
            trajectoryPoints.push({ x: Number(data.cav.x), y: Number(data.cav.y) });
            drawTrajectory(trajectoryPoints);
        }

        if (data.elapsed) document.getElementById('cavElapsed').textContent = formatTime(data.elapsed);

        if (data.status === 'completed' && isSimRunning) {
            isSimRunning = false;
            updateStatus('仿真完成');
            document.getElementById('sumoStatus').textContent = '已完成';
            document.getElementById('cavStatus').textContent = '已完成';
            stopStatusPolling();
            stopLogPolling();
            showProgress(false);
            addLocalLog(data.message || '仿真已完成', 'info');
            highlightStep(4);
            loadOutputFiles();
        }

        if (data.status === 'error') {
            isSimRunning = false;
            updateStatus('仿真出错');
            stopStatusPolling();
            stopLogPolling();
            showProgress(false);
            addLocalLog('仿真出错: ' + (data.message || ''), 'error');
        }
    } catch (e) { /* ignore */ }
}

function drawEmptyCanvas(message) {
    var canvas = document.getElementById('trajectoryCanvas');
    var ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#f0f4f8';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = '#ddd';
    ctx.lineWidth = 0.5;
    for (var x = 0; x < canvas.width; x += 50) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
    for (var y = 0; y < canvas.height; y += 50) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }
    ctx.fillStyle = '#687385';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(message || '启动联合仿真后将实时显示同步车辆轨迹', canvas.width / 2, canvas.height / 2);
}

function drawTrajectory(points) {
    var clean = (points || []).filter(function(p) {
        return Number.isFinite(p.x) && Number.isFinite(p.y);
    });
    if (clean.length < 2) return;

    var canvas = document.getElementById('trajectoryCanvas');
    var ctx = canvas.getContext('2d');
    var W = canvas.width;
    var H = canvas.height;
    var pad = 40;
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    clean.forEach(function(p) {
        minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
    });

    var rangeX = maxX - minX || 1;
    var rangeY = maxY - minY || 1;
    var scale = Math.min((W - pad * 2) / rangeX, (H - pad * 2) / rangeY);
    function tx(x) { return pad + (x - minX) * scale; }
    function ty(y) { return H - pad - (y - minY) * scale; }

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#f0f4f8';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#e0e0e0';
    ctx.lineWidth = 0.5;
    for (var gx = 0; gx < W; gx += 50) { ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, H); ctx.stroke(); }
    for (var gy = 0; gy < H; gy += 50) { ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(W, gy); ctx.stroke(); }

    ctx.beginPath();
    ctx.strokeStyle = '#2C5AA0';
    ctx.lineWidth = 2.5;
    ctx.lineJoin = 'round';
    ctx.moveTo(tx(clean[0].x), ty(clean[0].y));
    for (var i = 1; i < clean.length; i++) ctx.lineTo(tx(clean[i].x), ty(clean[i].y));
    ctx.stroke();

    ctx.beginPath();
    ctx.fillStyle = '#28A745';
    ctx.arc(tx(clean[0].x), ty(clean[0].y), 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 9px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('S', tx(clean[0].x), ty(clean[0].y) + 3);

    var last = clean[clean.length - 1];
    ctx.beginPath();
    ctx.fillStyle = '#DC3545';
    ctx.arc(tx(last.x), ty(last.y), 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.fillText('E', tx(last.x), ty(last.y) + 3);

    if (isSimRunning) {
        ctx.beginPath();
        ctx.fillStyle = 'rgba(44, 90, 160, 0.3)';
        ctx.arc(tx(last.x), ty(last.y), 12, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.fillStyle = '#2C5AA0';
        ctx.arc(tx(last.x), ty(last.y), 5, 0, Math.PI * 2);
        ctx.fill();
    }
}

async function loadDemoTrajectory() {
    var scene = getSelectedScene();
    if (!scene) return;
    addLocalLog('加载演示轨迹数据: ' + scene.name, 'info');
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/demo-trajectory?scene_id=' + encodeURIComponent(scene.id));
        var data = await resp.json();
        if (data.success && data.trajectory) {
            trajectoryPoints = data.trajectory.map(function(p) { return { x: Number(p.x), y: Number(p.y) }; });
            drawTrajectory(trajectoryPoints);
            addLocalLog('已加载 ' + data.trajectory.length + ' 个轨迹点 — 总时长: ' +
                data.summary.duration + ', 平均速度: ' + data.summary.avg_speed, 'info');
        }
    } catch (err) {
        addLocalLog('加载轨迹失败: ' + err.message, 'error');
    }
}

async function loadOutputFiles() {
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/output-files');
        var data = await resp.json();
        var container = document.getElementById('outputFiles');
        if (data.success && data.files && data.files.length > 0) {
            container.innerHTML = data.files.map(function(f) {
                return '<div class="file-item">' +
                    '<span class="file-icon">📊</span>' +
                    '<span class="file-name">' + escapeHtml(f.name) + '</span>' +
                    '<span class="file-size">' + escapeHtml(f.size) + '</span>' +
                    '<span class="file-time">' + escapeHtml(f.mtime) + '</span>' +
                    '<a class="file-download" href="' + API_BASE + '/api/carla-sim/download/' + encodeURIComponent(f.path) + '" download title="下载">⬇</a>' +
                    '</div>';
            }).join('');
        } else {
            container.innerHTML = '<p class="hint-text">暂无轨迹文件</p>';
        }
    } catch (e) { /* ignore */ }
}

async function loadSoftwareStatus() {
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/software-status');
        var data = await resp.json();
        if (!data.success) return;

        data.software.forEach(function(sw) {
            var card = document.querySelector('.software-card[data-id="' + sw.id + '"]');
            if (!card) return;
            var dot = document.getElementById(sw.id + 'StatusDot');
            var pathEl = document.getElementById(sw.id + 'Path');
            var runTag = document.getElementById(sw.id + 'RunTag');
            var stopBtnId = sw.id === 'carla' ? 'stopCarlaBtn' : sw.id === 'sumo' ? 'stopSumoBtn' : 'stopNextaBtn';
            var stopBtn = document.getElementById(stopBtnId);

            card.classList.remove('sw-running', 'sw-missing');
            if (!sw.installed) {
                card.classList.add('sw-missing');
                if (dot) dot.className = 'sw-status-dot dot-missing';
                if (pathEl) pathEl.textContent = '未安装';
                if (runTag) runTag.style.display = 'none';
                if (stopBtn) stopBtn.style.display = 'none';
            } else if (sw.running) {
                card.classList.add('sw-running');
                if (dot) dot.className = 'sw-status-dot dot-running';
                if (pathEl) pathEl.textContent = sw.path;
                if (runTag) runTag.style.display = 'inline-block';
                if (stopBtn) stopBtn.style.display = 'inline-block';
            } else {
                if (dot) dot.className = 'sw-status-dot dot-installed';
                if (pathEl) pathEl.textContent = sw.path;
                if (runTag) runTag.style.display = 'none';
                if (stopBtn) stopBtn.style.display = 'none';
            }
        });
    } catch (e) {
        console.error('加载软件状态失败:', e);
    }
}

async function launchSoftware(id) {
    addLocalLog('正在启动 ' + id.toUpperCase() + '...', 'info');
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/launch-software', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id, params: {} })
        });
        var data = await resp.json();
        if (data.success) {
            addLocalLog(data.message, 'info');
            setTimeout(loadSoftwareStatus, id === 'carla' ? 8000 : 3000);
        } else {
            addLocalLog('启动失败: ' + data.message, 'error');
            alert(data.message);
        }
    } catch (e) {
        addLocalLog('启动异常: ' + e.message, 'error');
        alert('启动失败: ' + e.message);
    }
}

async function stopSoftware(id) {
    if (!confirm('确定要停止 ' + id.toUpperCase() + ' 吗？')) return;
    addLocalLog('正在停止 ' + id.toUpperCase() + '...', 'info');
    try {
        var resp = await fetch(API_BASE + '/api/carla-sim/stop-software', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        var data = await resp.json();
        if (data.success) {
            addLocalLog(data.message, 'info');
            setTimeout(loadSoftwareStatus, 2000);
        } else {
            addLocalLog('停止失败: ' + data.message, 'error');
        }
    } catch (e) {
        addLocalLog('停止异常: ' + e.message, 'error');
    }
}

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function lastPathPart(path) {
    return String(path || '').split(/[\\/]/).pop();
}
