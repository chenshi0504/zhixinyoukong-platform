// 三层级协同优化控制 JavaScript
var API_SIGNAL = '/api/signal-optimization';
var API_PATH = '/api/path-guidance';
var API_SPEED = '/api/vehicle-speed';
var API_THREE = '/api/three-level';

var LEVEL_NAMES = { signal: '信号优化', path: '路径诱导', speed: '车速控制' };
var SIGNAL_NAMES = { turbo: 'TuRBO', bo: 'BO', dqn: 'DQN', ppo: 'PPO', ga: 'GA', pso: 'PSO' };
var PATH_NAMES = { dijkstra: 'Dijkstra', ssp: 'SSP', astar: 'A*' };
var SPEED_NAMES = { idm: 'IDM', acc: 'ACC', cacc: 'CACC', pid: 'PID' };

var LEVEL_API = {
    signal: { base: API_SIGNAL, names: SIGNAL_NAMES },
    path:   { base: API_PATH,   names: PATH_NAMES },
    speed:  { base: API_SPEED,  names: SPEED_NAMES }
};

var DEFAULT_CONFIGS = {
    net: 'siouxfalls.net.xml',
    cfg: 'siouxfalls.sumocfg'
};

class ThreeLevelControl {
    constructor() {
        this.isRunning = false;
        this.allResults = {};
        this.init();
    }

    init() {
        this.bindEvents();
        this.updateLevelCards();
        this.updateLevelSummary();
    }

    bindEvents() {
        var self = this;
        ['signal', 'path', 'speed'].forEach(function(lv) {
            document.getElementById(lv + 'Enabled').addEventListener('change', function() {
                self.updateLevelCards(); self.updateLevelSummary();
            });
        });
        document.getElementById('startSimulation').addEventListener('click', function() { self.startSimulation(); });
        document.getElementById('resetParams').addEventListener('click', function() { self.resetParams(); });
        var backBtn = document.getElementById('backBtn');
        if (backBtn) backBtn.addEventListener('click', function() { window.history.back(); });

        // 配置文件按钮
        var netBtn = document.getElementById('netFileBtn');
        if (netBtn) netBtn.addEventListener('click', function() { self.loadConfig('net'); });
        var cfgBtn = document.getElementById('cfgFileBtn');
        if (cfgBtn) cfgBtn.addEventListener('click', function() { self.loadConfig('cfg'); });

        var exportBtn = document.getElementById('exportResultsBtn');
        if (exportBtn) exportBtn.addEventListener('click', function() { self.exportResults(); });
        var exportReportBtn = document.getElementById('exportReportBtn');
        if (exportReportBtn) exportReportBtn.addEventListener('click', function() { self.exportReport(); });
    }

    loadConfig(key) {
        var btn = document.getElementById(key === 'net' ? 'netFileBtn' : 'cfgFileBtn');
        var pathEl = document.getElementById(key === 'net' ? 'netFilePath' : 'cfgFilePath');
        if (btn) btn.classList.add('step-done');
        if (pathEl) { pathEl.textContent = ' 已载入: ' + DEFAULT_CONFIGS[key]; pathEl.style.color = '#27ae60'; }
    }

    updateLevelCards() {
        ['signal', 'path', 'speed'].forEach(function(lv) {
            var enabled = document.getElementById(lv + 'Enabled').checked;
            var card = document.getElementById(lv + 'Card');
            if (enabled) { card.classList.add('active'); card.classList.remove('disabled'); }
            else { card.classList.remove('active'); card.classList.add('disabled'); }
        });
    }

    updateLevelSummary() {
        var enabled = this.getEnabledLevels();
        var el = document.getElementById('levelSummary');
        if (enabled.length < 2) {
            el.textContent = ' 请至少选择2个层级';
            el.style.background = '#fff3cd'; el.style.color = '#856404'; el.style.borderColor = '#ffc107';
        } else {
            var names = enabled.map(function(lv) { return LEVEL_NAMES[lv]; });
            el.textContent = '已选择 ' + enabled.length + ' 个层级：' + names.join(' + ');
            el.style.background = '#e8f4f8'; el.style.color = '#2C5AA0'; el.style.borderColor = '#b8d4e3';
        }
    }

    getEnabledLevels() {
        var levels = [];
        if (document.getElementById('signalEnabled').checked) levels.push('signal');
        if (document.getElementById('pathEnabled').checked) levels.push('path');
        if (document.getElementById('speedEnabled').checked) levels.push('speed');
        return levels;
    }

    setStatus(text) { var el = document.getElementById('currentStatus'); if (el) el.textContent = '状态: ' + text; }
    updateTimestamp() { var el = document.getElementById('updateTime'); if (el) el.textContent = new Date().toLocaleString('zh-CN'); }

    // 获取每个层级的API请求参数
    getLevelParams(level) {
        var flowLevel = parseInt(document.getElementById('flowLevel').value);
        var pr = parseInt(document.getElementById('prSelect').value);
        if (level === 'signal') {
            return { algorithm: document.getElementById('signalAlgo').value, flow_level: flowLevel, use_gui: true };
        } else if (level === 'path') {
            return { algorithm: document.getElementById('pathAlgo').value, flow_level: flowLevel, pr: pr, use_gui: true };
        } else {
            return { algorithm: document.getElementById('speedAlgo').value, flow_level: flowLevel, pr: pr, use_gui: true };
        }
    }

    // 获取层级特有的控制参数描述
    getLevelControlDesc(level) {
        if (level === 'signal') {
            return '优化间隔: ' + document.getElementById('signalOptInterval').value + 's';
        } else if (level === 'path') {
            return '重路由间隔: ' + document.getElementById('pathRerouteInterval').value + 's';
        } else {
            return '控制步长: ' + document.getElementById('speedControlDt').value + 's';
        }
    }

    getLevelAlgoName(level) {
        var params = this.getLevelParams(level);
        return LEVEL_API[level].names[params.algorithm] || params.algorithm;
    }

    getUnifiedParams() {
        return {
            signal: document.getElementById('signalAlgo').value,
            path: document.getElementById('pathAlgo').value,
            speed: document.getElementById('speedAlgo').value,
            flow: parseInt(document.getElementById('flowLevel').value),
            pr: parseInt(document.getElementById('prSelect').value),
            accept_rate: parseInt(document.getElementById('acceptRate').value),
            max_time: parseInt(document.getElementById('maxSimTime').value),
            signal_interval: parseInt(document.getElementById('signalOptInterval').value),
            path_interval: parseInt(document.getElementById('pathRerouteInterval').value),
            speed_dt: parseFloat(document.getElementById('speedControlDt').value),
            enable_signal: document.getElementById('signalEnabled').checked,
            enable_path: document.getElementById('pathEnabled').checked,
            enable_speed: document.getElementById('speedEnabled').checked,
            use_gui: true
        };
    }

    // ========== 核心：依次启动各层级仿真 ==========
    async startSimulation() {
        if (this.isRunning) return;
        var levels = this.getEnabledLevels();
        if (levels.length < 2) { alert('请至少选择2个层级'); return; }

        this.isRunning = true;
        this.allResults = {};
        var btn = document.getElementById('startSimulation');
        btn.textContent = '协同仿真中...'; btn.disabled = true;
        this.showRunning(levels);

        try { await fetch(API_THREE + '/reset', { method: 'POST' }); } catch (e) {}
        this.setStatus('正在启动统一三层级仿真CMD...');
        this.updateRunningStep(levels, 0);
        var unifiedSuccess = await this.launchUnifiedAndWait(levels);
        if (!unifiedSuccess) {
            this.setStatus('三层级统一仿真失败，请查看后端CMD输出');
            this.updateRunningStep(levels, 0, true);
            this.resetButton();
            return;
        }
        this.updateRunningStep(levels, levels.length);
        this.setStatus('协同仿真完成，共 ' + levels.length + ' 个层级');
        this.updateTimestamp();
        this.displayAllResults(levels);
        this.resetButton();
        return;

        for (var i = 0; i < levels.length; i++) {
            try { await fetch(LEVEL_API[levels[i]].base + '/reset', { method: 'POST' }); } catch (e) {}
        }

        for (var i = 0; i < levels.length; i++) {
            var lv = levels[i];
            var algoName = this.getLevelAlgoName(lv);
            this.setStatus('正在运行第 ' + (i + 1) + '/' + levels.length + ' 层: ' + LEVEL_NAMES[lv] + ' (' + algoName + ')...');
            this.updateRunningStep(levels, i);

            var success = await this.launchAndWait(lv);
            if (!success) {
                this.setStatus(LEVEL_NAMES[lv] + ' 仿真失败，协同仿真中止');
                this.updateRunningStep(levels, i, true);
                this.resetButton();
                return;
            }
        }

        this.updateRunningStep(levels, levels.length);
        this.setStatus('协同仿真完成！共 ' + levels.length + ' 个层级');
        this.updateTimestamp();
        this.displayAllResults(levels);
        this.resetButton();
    }

    async launchUnifiedAndWait(levels) {
        try {
            var resp = await fetch(API_THREE + '/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.getUnifiedParams())
            });
            var data = await resp.json();
            if (!resp.ok || !data.success) { console.error('三层级启动失败:', data); return false; }
            this.setStatus('统一三层级仿真已在后端CMD启动...');
        } catch (e) { console.error('三层级请求失败:', e); return false; }
        return await this.waitForUnified(levels);
    }

    waitForUnified(levels) {
        var self = this;
        return new Promise(function(resolve) {
            var timer = setInterval(async function() {
                try {
                    var resp = await fetch(API_THREE + '/status');
                    var s = await resp.json();
                    if (s.running) {
                        self.setStatus(s.message || '统一三层级仿真运行中...');
                        var elapsed = s.elapsed || 0;
                        var idx = Math.min(levels.length - 1, Math.floor(elapsed / 20));
                        self.updateRunningStep(levels, idx);
                    } else {
                        clearInterval(timer);
                        if (s.success) {
                            var r = s.results || { message: s.message };
                            r.config_name = s.config_name;
                            levels.forEach(function(lv) { self.allResults[lv] = Object.assign({}, r); });
                        }
                        resolve(!!s.success);
                    }
                } catch (e) {}
            }, 3000);
        });
    }

    async launchAndWait(level) {
        var base = LEVEL_API[level].base;
        var params = this.getLevelParams(level);
        try {
            var resp = await fetch(base + '/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(params)
            });
            var data = await resp.json();
            if (!resp.ok || !data.success) { console.error(level + ' 启动失败:', data); return false; }
        } catch (e) { console.error(level + ' 请求失败:', e); return false; }
        return await this.waitForLevel(level);
    }

    waitForLevel(level) {
        var self = this;
        var base = LEVEL_API[level].base;
        return new Promise(function(resolve) {
            var timer = setInterval(async function() {
                try {
                    var resp = await fetch(base + '/status');
                    var s = await resp.json();
                    if (!s.running) {
                        clearInterval(timer);
                        if (s.success) {
                            self.allResults[level] = s.results || { message: s.message };
                            self.allResults[level].config_name = s.config_name;
                        }
                        resolve(!!s.success);
                    }
                } catch (e) {}
            }, 3000);
        });
    }
    // ========== 运行状态显示 ==========
    showRunning(levels) {
        var self = this;
        var flowLevel = document.getElementById('flowLevel').value;
        var pr = document.getElementById('prSelect').value;
        var acceptRate = document.getElementById('acceptRate').value;
        var maxTime = document.getElementById('maxSimTime').value;
        var html = '<div style="padding:20px;">';
        html += '<div style="text-align:center;font-size:36px;margin-bottom:12px;"></div>';
        html += '<div style="text-align:center;font-size:16px;font-weight:600;color:#2c3e50;margin-bottom:6px;">协同仿真运行中</div>';
        html += '<div style="text-align:center;font-size:13px;color:#888;margin-bottom:16px;">流量: ' + flowLevel + ' | 渗透率: ' + pr + '% | 采纳率: ' + acceptRate + '% | 最大时间: ' + maxTime + 's</div>';
        html += '<div id="levelSteps" style="display:flex;flex-direction:column;gap:10px;">';
        for (var i = 0; i < levels.length; i++) {
            var lv = levels[i];
            var algoName = self.getLevelAlgoName(lv);
            var ctrlDesc = self.getLevelControlDesc(lv);
            html += '<div id="step_' + lv + '" class="sim-step waiting">';
            html += '<span class="step-num">' + (i + 1) + '</span>';
            html += '<span class="step-label">' + LEVEL_NAMES[lv] + '</span>';
            html += '<span class="step-info">' + algoName + ' | ' + ctrlDesc + '</span>';
            html += '<span class="step-status" id="stepStatus_' + lv + '">等待中</span>';
            html += '</div>';
        }
        html += '</div></div>';
        document.getElementById('resultSummary').innerHTML = html;
    }

    updateRunningStep(levels, currentIdx, failed) {
        for (var i = 0; i < levels.length; i++) {
            var el = document.getElementById('step_' + levels[i]);
            var statusEl = document.getElementById('stepStatus_' + levels[i]);
            if (!el) continue;
            if (i < currentIdx) {
                el.className = 'sim-step done';
                if (statusEl) statusEl.textContent = ' 完成';
            } else if (i === currentIdx) {
                if (failed) { el.className = 'sim-step waiting'; if (statusEl) statusEl.textContent = ' 失败'; }
                else { el.className = 'sim-step running'; if (statusEl) statusEl.textContent = ' 运行中...'; }
            } else {
                el.className = 'sim-step waiting';
                if (statusEl) statusEl.textContent = '等待中';
            }
        }
    }

    // ========== 结果展示 ==========
    displayAllResults(levels) {
        var self = this;
        var flowLevel = document.getElementById('flowLevel').value;
        var pr = document.getElementById('prSelect').value;
        var acceptRate = document.getElementById('acceptRate').value;
        var html = '<div style="padding:20px;">';
        html += '<h4 style="color:#2C5AA0;margin-bottom:6px;font-size:16px;"> 协同仿真完成  ' + levels.length + ' 个层级</h4>';
        html += '<div style="font-size:12px;color:#888;margin-bottom:16px;">流量: ' + flowLevel + ' | 渗透率: ' + pr + '% | 采纳率: ' + acceptRate + '%</div>';

        levels.forEach(function(lv) {
            var r = self.allResults[lv] || {};
            var algoName = self.getLevelAlgoName(lv);
            html += '<div style="margin-bottom:16px;padding:14px;background:#f8f9fa;border-radius:8px;border-left:4px solid #2C5AA0;">';
            html += '<div style="font-weight:600;color:#2c3e50;margin-bottom:8px;">' + LEVEL_NAMES[lv] + '  ' + algoName + '</div>';

            if (lv === 'signal') {
                html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">';
                html += self.metricBox('平均延误', r.average_delay, 's', '#2C5AA0');
                html += self.metricBox('吞吐量', r.throughput, '辆', '#27ae60');
                html += self.metricBox('运行时间', r.runtime, 's', '#f39c12');
                html += '</div>';
            } else if (lv === 'path') {
                html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">';
                html += self.metricBox('平均延误', r.average_delay, 's', '#2C5AA0');
                html += self.metricBox('平均行程时间', r.avg_travel_time, 's', '#27ae60');
                html += self.metricBox('吞吐量', r.throughput, '辆', '#f39c12');
                html += '</div>';
            } else {
                html += '<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;">';
                html += self.metricBox('平均延误', r.average_delay, 's', '#2C5AA0');
                html += self.metricBox('平均速度', r.avg_speed, 'km/h', '#27ae60');
                html += self.metricBox('速度标准差', r.speed_std, 'km/h', '#f39c12');
                html += self.metricBox('吞吐量', r.throughput, '辆', '#e74c3c');
                html += '</div>';
            }
            html += '</div>';
        });
        html += '</div>';
        document.getElementById('resultSummary').innerHTML = html;
        this.loadAllOutputFiles(levels);
    }

    metricBox(label, value, unit, color) {
        var display = (value != null && value !== undefined) ? value + ' ' + unit : '--';
        return '<div style="background:white;padding:10px;border-radius:6px;border-left:3px solid ' + color + ';">' +
            '<div style="font-size:11px;color:#888;">' + label + '</div>' +
            '<div style="font-size:17px;font-weight:bold;color:#2c3e50;">' + display + '</div></div>';
    }

    async loadAllOutputFiles(levels) {
        var container = document.getElementById('resultImages');
        if (!container) return;
        var html = '';
        for (var i = 0; i < levels.length; i++) {
            var lv = levels[i];
            var r = this.allResults[lv];
            if (!r || !r.config_name) continue;
            var base = LEVEL_API[lv].base;
            if (String(r.config_name).indexOf('3L_') === 0) base = API_THREE;
            try {
                var resp = await fetch(base + '/output/' + r.config_name);
                if (!resp.ok) continue;
                var data = await resp.json();
                var imgFiles = data.files.filter(function(f) { return f.name.match(/\.(png|jpg|jpeg)$/i); });
                var dataFiles = data.files.filter(function(f) { return f.name.match(/\.(xlsx|csv|json)$/i); });
                if (imgFiles.length > 0 || dataFiles.length > 0) {
                    html += '<div style="margin-bottom:16px;"><h4 style="color:#2C5AA0;font-size:14px;margin-bottom:8px;">' + LEVEL_NAMES[lv] + ' 输出</h4>';
                    imgFiles.forEach(function(f) {
                        html += '<div class="result-image-item"><img src="' + base + '/output-file/' + r.config_name + '/' + f.name + '" alt="' + f.name + '" class="result-img"><p class="result-img-caption">' + f.name + '</p></div>';
                    });
                    if (dataFiles.length > 0) {
                        html += '<div style="padding:8px;">';
                        dataFiles.forEach(function(f) {
                            html += '<a href="' + base + '/output-file/' + r.config_name + '/' + f.name + '" download style="display:block;padding:4px 0;color:#2C5AA0;text-decoration:none;"> ' + f.name + ' (' + (f.size / 1024).toFixed(1) + 'KB)</a>';
                        });
                        html += '</div>';
                    }
                    html += '</div>';
                }
            } catch (e) { console.warn('加载' + lv + '输出失败:', e); }
        }
        container.innerHTML = html || '<p style="color:#999;text-align:center;padding:20px;">暂无输出文件</p>';
    }
    // ========== 重置 ==========
    resetButton() {
        this.isRunning = false;
        var btn = document.getElementById('startSimulation');
        if (btn) { btn.textContent = '▶ 开始协同仿真'; btn.disabled = false; }
    }

    resetParams() {
        this.isRunning = false;
        this.allResults = {};
        document.getElementById('signalAlgo').value = 'turbo';
        document.getElementById('signalOptInterval').value = '600';
        document.getElementById('pathAlgo').value = 'dijkstra';
        document.getElementById('pathRerouteInterval').value = '30';
        document.getElementById('speedAlgo').value = 'idm';
        document.getElementById('speedControlDt').value = '0.5';
        document.getElementById('flowLevel').value = '4';
        document.getElementById('prSelect').value = '40';
        document.getElementById('acceptRate').value = '100';
        document.getElementById('maxSimTime').value = '3600';
        ['signalEnabled', 'pathEnabled', 'speedEnabled'].forEach(function(id) {
            document.getElementById(id).checked = true;
        });
        this.updateLevelCards();
        this.updateLevelSummary();
        // 重置配置文件按钮
        ['netFileBtn', 'cfgFileBtn'].forEach(function(id) {
            var btn = document.getElementById(id);
            if (btn) btn.classList.remove('step-done');
        });
        var netPath = document.getElementById('netFilePath');
        if (netPath) { netPath.textContent = '默认: ' + DEFAULT_CONFIGS.net; netPath.style.color = '#888'; }
        var cfgPath = document.getElementById('cfgFilePath');
        if (cfgPath) { cfgPath.textContent = '默认: ' + DEFAULT_CONFIGS.cfg; cfgPath.style.color = '#888'; }

        document.getElementById('resultSummary').innerHTML = '<p style="color:#999;text-align:center;padding:30px;">选择层级算法后点击"开始协同仿真"，各层级将依次启动仿真，结果汇总展示</p>';
        document.getElementById('resultImages').innerHTML = '<p style="color:#999;text-align:center;padding:40px 20px;">运行仿真后将在此显示各层级输出图表和数据文件</p>';
        this.setStatus('就绪');
        document.getElementById('updateTime').textContent = '--:--:--';
        this.resetButton();
        [API_SIGNAL, API_PATH, API_SPEED].forEach(function(api) {
            fetch(api + '/reset', { method: 'POST' }).catch(function() {});
        });
    }

    // ========== 导出 ==========
    exportResults() {
        var self = this;
        var levels = this.getEnabledLevels();
        var flowLevel = document.getElementById('flowLevel').value;
        var pr = document.getElementById('prSelect').value;
        var acceptRate = document.getElementById('acceptRate').value;
        var csv = '\uFEFF三层级协同优化控制仿真结果\n生成时间,' + new Date().toLocaleString('zh-CN') + '\n流量等级,' + flowLevel + '\nCAV渗透率,' + pr + '%\nCAV采纳率,' + acceptRate + '%\n\n';

        levels.forEach(function(lv) {
            var r = self.allResults[lv] || {};
            var algoName = self.getLevelAlgoName(lv);
            csv += LEVEL_NAMES[lv] + '  ' + algoName + '\n';
            csv += '指标,数值\n';
            if (r.average_delay != null) csv += '平均延误(s),' + r.average_delay + '\n';
            if (r.avg_speed != null) csv += '平均速度(km/h),' + r.avg_speed + '\n';
            if (r.speed_std != null) csv += '速度标准差(km/h),' + r.speed_std + '\n';
            if (r.throughput != null) csv += '吞吐量(辆),' + r.throughput + '\n';
            if (r.avg_travel_time != null) csv += '平均行程时间(s),' + r.avg_travel_time + '\n';
            if (r.runtime != null) csv += '运行时间(s),' + r.runtime + '\n';
            csv += '\n';
        });

        var blob = new Blob([csv], { type: 'text/csv;charset=utf-8-sig' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '三层级协同结果_flow' + flowLevel + '_pr' + pr + '_' + Date.now() + '.csv';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
    }

    exportReport() {
        var self = this;
        var levels = this.getEnabledLevels();
        var flowLevel = document.getElementById('flowLevel').value;
        var pr = document.getElementById('prSelect').value;
        var acceptRate = document.getElementById('acceptRate').value;
        var maxTime = document.getElementById('maxSimTime').value;
        var currentTime = new Date().toLocaleString('zh-CN');

        var html = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>三层级协同优化控制实验报告</title>' +
            '<style>body{font-family:"Microsoft YaHei",Arial,sans-serif;line-height:1.8;margin:40px;}h1{text-align:center;color:#2C5AA0;}h2{color:#2C5AA0;border-bottom:2px solid #2C5AA0;padding-bottom:5px;margin-top:30px;}table{width:100%;border-collapse:collapse;margin:15px 0;}th,td{border:1px solid #ddd;padding:10px;text-align:left;}th{background:#2C5AA0;color:white;}.info-box{background:#E8F4F8;padding:15px;border-left:4px solid #2C5AA0;margin:15px 0;}</style></head><body>' +
            '<h1>三层级协同优化控制实验报告</h1><p style="text-align:center;color:#666;">实验时间：' + currentTime + '</p>';

        html += '<h2>一、实验配置</h2>';
        html += '<div class="info-box">流量等级: ' + flowLevel + ' | CAV渗透率: ' + pr + '% | CAV采纳率: ' + acceptRate + '% | 最大仿真时间: ' + maxTime + 's</div>';
        html += '<table><tr><th>层级</th><th>算法</th><th>控制参数</th></tr>';
        levels.forEach(function(lv) {
            var algoName = self.getLevelAlgoName(lv);
            var ctrlDesc = self.getLevelControlDesc(lv);
            html += '<tr><td>' + LEVEL_NAMES[lv] + '</td><td>' + algoName + '</td><td>' + ctrlDesc + '</td></tr>';
        });
        html += '</table>';

        html += '<h2>二、实验结果</h2>';
        levels.forEach(function(lv) {
            var r = self.allResults[lv] || {};
            var algoName = self.getLevelAlgoName(lv);
            html += '<h3>' + LEVEL_NAMES[lv] + '  ' + algoName + '</h3>';
            html += '<table><tr><th>指标</th><th>数值</th></tr>';
            if (r.average_delay != null) html += '<tr><td>平均延误</td><td>' + r.average_delay + ' s</td></tr>';
            if (r.avg_speed != null) html += '<tr><td>平均速度</td><td>' + r.avg_speed + ' km/h</td></tr>';
            if (r.speed_std != null) html += '<tr><td>速度标准差</td><td>' + r.speed_std + ' km/h</td></tr>';
            if (r.throughput != null) html += '<tr><td>吞吐量</td><td>' + r.throughput + ' 辆</td></tr>';
            if (r.avg_travel_time != null) html += '<tr><td>平均行程时间</td><td>' + r.avg_travel_time + ' s</td></tr>';
            if (r.runtime != null) html += '<tr><td>运行时间</td><td>' + r.runtime + ' s</td></tr>';
            html += '</table>';
        });

        html += '<h2>三、实验心得</h2><p style="min-height:100px;border:1px dashed #ccc;padding:10px;"></p>';
        html += '<div style="margin-top:50px;text-align:right;"><p>实验人员：___________　学号：___________</p><p>指导教师：___________　日期：' + currentTime.split(' ')[0] + '</p></div></body></html>';

        var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '三层级协同实验报告_' + Date.now() + '.doc';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
    }
}

// ========== 初始化 ==========
document.addEventListener('DOMContentLoaded', function() { new ThreeLevelControl(); });

// ========== 服务器状态检查 ==========
(function() {
    function checkServer() {
        var el = document.getElementById('serverStatus');
        if (!el) return;
        fetch('/', { method: 'GET' })
            .then(function(r) { if (r.ok || r.status === 404 || r.status === 405) { el.textContent = '服务器: 已连接 '; el.style.color = '#28a745'; } else { throw new Error(); } })
            .catch(function() { el.textContent = '服务器: 未连接 '; el.style.color = '#dc3545'; });
    }
    document.addEventListener('DOMContentLoaded', function() { checkServer(); setInterval(checkServer, 30000); });
})();
