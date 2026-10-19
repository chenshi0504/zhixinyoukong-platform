// 下层-车速控制功能 JavaScript
const API_BASE = '/api/vehicle-speed';

const ALGO_DESCRIPTIONS = {
    'idm': '<strong>IDM</strong>：智能驾驶员模型（Intelligent Driver Model），基于前车距离和速度差计算加速度，经典跟驰模型，参数物理意义明确。',
    'acc': '<strong>ACC</strong>：自适应巡航控制（Adaptive Cruise Control），基于雷达感知前车状态，PID调节跟车间距和速度。',
    'cacc': '<strong>CACC</strong>：协同自适应巡航控制（Cooperative ACC），利用V2V通信获取前车加速度，实现更紧密的编队行驶。',
    'pid': '<strong>PID</strong>：经典PID速度控制器，基于目标速度误差的比例-积分-微分反馈控制。',
};
const ALGO_NAMES = { 'idm': 'IDM', 'acc': 'ACC', 'cacc': 'CACC', 'pid': 'PID' };

// 流量等级显示映射 (内部值 -> 显示值)
const FLOW_DISPLAY = { '2': '1 (低流量)', '4': '2 (中流量)', '6': '3 (高流量)' };
function flowLabel(v) { return FLOW_DISPLAY[String(v)] || String(v); }

const SPEED_TEMPLATES = {
    idm_tpl: '# IDM 智能驾驶员模型\n# 基于前车距离和速度差的跟驰模型\n\nimport math\n\nclass IDMController:\n    """\n    Intelligent Driver Model\n    经典跟驰模型，参数物理意义明确\n    """\n    def __init__(self, v0=13.89, T=1.5, a_max=1.5, b=2.0, s0=2.0, delta=4):\n        self.v0 = v0        # 期望速度 (m/s) ~50km/h\n        self.T = T           # 安全时距 (s)\n        self.a_max = a_max   # 最大加速度 (m/s^2)\n        self.b = b           # 舒适减速度 (m/s^2)\n        self.s0 = s0         # 最小间距 (m)\n        self.delta = delta   # 加速指数\n\n    def compute_accel(self, v, dv, s):\n        """计算加速度\n        v: 当前速度, dv: 与前车速度差, s: 与前车间距\n        """\n        s_star = self.s0 + max(0, v * self.T + v * dv / (2 * math.sqrt(self.a_max * self.b)))\n        if s < 0.1:\n            s = 0.1\n        a = self.a_max * (1 - (v / self.v0) ** self.delta - (s_star / s) ** 2)\n        return max(-self.b * 2, min(a, self.a_max))\n\n# 参数说明:\n# v0: 期望速度，增大则CAV倾向更快行驶\n# T: 安全时距，增大则跟车距离更大\n# a_max: 最大加速度，影响加速响应\n# b: 舒适减速度，影响制动平顺性\n# s0: 最小间距，停车时的最小距离',
    acc_tpl: '# ACC 自适应巡航控制\n# 雷达感知 + PID调节的跟车控制\n\nclass ACCController:\n    """\n    Adaptive Cruise Control\n    基于雷达感知前车状态，PID调节跟车间距\n    """\n    def __init__(self, v_desired=13.89, k_p=0.4, k_d=0.1,\n                 time_gap=1.8, min_gap=3.0):\n        self.v_desired = v_desired  # 期望速度 (m/s)\n        self.k_p = k_p              # 比例增益\n        self.k_d = k_d              # 微分增益\n        self.time_gap = time_gap    # 时间间距 (s)\n        self.min_gap = min_gap      # 最小间距 (m)\n\n    def compute_accel(self, v, dv, s):\n        """计算加速度\n        v: 当前速度, dv: 速度差, s: 间距\n        """\n        desired_gap = self.min_gap + v * self.time_gap\n        gap_error = s - desired_gap\n        if s < desired_gap * 1.5:  # 跟车模式\n            a = self.k_p * gap_error - self.k_d * dv\n        else:  # 巡航模式\n            speed_error = self.v_desired - v\n            a = self.k_p * speed_error\n        return max(-3.0, min(a, 2.0))\n\n# 参数说明:\n# k_p: 比例增益，增大则响应更快但可能振荡\n# k_d: 微分增益，增大则抑制振荡\n# time_gap: 时间间距，增大则跟车距离更大\n# min_gap: 最小间距，停车时的安全距离',
    cacc_tpl: '# CACC 协同自适应巡航控制\n# V2V通信 + 编队行驶\n\nclass CACCController:\n    """\n    Cooperative Adaptive Cruise Control\n    利用V2V通信获取前车加速度，实现紧密编队\n    """\n    def __init__(self, v_desired=13.89, k_p=0.5, k_d=0.15,\n                 k_a=0.1, time_gap=0.8, min_gap=2.0):\n        self.v_desired = v_desired\n        self.k_p = k_p      # 间距比例增益\n        self.k_d = k_d      # 速度差微分增益\n        self.k_a = k_a      # 前车加速度前馈增益\n        self.time_gap = time_gap  # 时间间距(更小=更紧密)\n        self.min_gap = min_gap\n\n    def compute_accel(self, v, dv, s, leader_a=0):\n        """计算加速度\n        v: 当前速度, dv: 速度差, s: 间距\n        leader_a: 前车加速度(V2V通信获取)\n        """\n        desired_gap = self.min_gap + v * self.time_gap\n        gap_error = s - desired_gap\n        # 间距控制 + 速度差抑制 + 前车加速度前馈\n        a = self.k_p * gap_error - self.k_d * dv + self.k_a * leader_a\n        return max(-3.0, min(a, 2.0))\n\n# CACC vs ACC:\n# - 时间间距更小(0.8s vs 1.8s)，编队更紧密\n# - 利用V2V通信获取前车加速度，提前响应\n# - k_a前馈增益使控制更平顺',
    pid_tpl: '# PID 经典速度控制\n# 目标速度跟踪的PID反馈控制\n\nclass PIDController:\n    """\n    PID Speed Controller\n    经典比例-积分-微分速度跟踪控制\n    """\n    def __init__(self, v_target=13.89, kp=0.5, ki=0.01, kd=0.1):\n        self.v_target = v_target  # 目标速度 (m/s)\n        self.kp = kp    # 比例增益\n        self.ki = ki    # 积分增益\n        self.kd = kd    # 微分增益\n        self.integral = {}   # 积分项(每辆车独立)\n        self.prev_error = {} # 上一步误差\n\n    def compute_accel(self, veh_id, v):\n        """计算加速度\n        veh_id: 车辆ID, v: 当前速度\n        """\n        error = self.v_target - v\n        if veh_id not in self.integral:\n            self.integral[veh_id] = 0\n            self.prev_error[veh_id] = 0\n        # 积分项(带限幅防止积分饱和)\n        self.integral[veh_id] += error\n        self.integral[veh_id] = max(-50, min(50, self.integral[veh_id]))\n        # 微分项\n        d_error = error - self.prev_error[veh_id]\n        self.prev_error[veh_id] = error\n        # PID输出\n        a = self.kp * error + self.ki * self.integral[veh_id] + self.kd * d_error\n        return max(-3.0, min(a, 2.0))\n\n# 参数调节:\n# kp: 增大加快响应，过大会振荡\n# ki: 消除稳态误差，过大会超调\n# kd: 抑制振荡，过大会放大噪声',
    custom: '# 自定义车速控制算法\n# 请在此编写您的算法\n\nimport traci\n\ndef my_speed_controller(sim_step):\n    """\n    自定义车速控制函数\n    在仿真主循环中每步调用\n\n    可用的TraCI接口:\n        traci.vehicle.getSpeed(veh)  # 获取速度\n        traci.vehicle.setSpeed(veh, speed)  # 设置速度\n        traci.vehicle.getLeader(veh, dist)  # 获取前车\n        traci.vehicle.getAcceleration(veh)  # 获取加速度\n        traci.vehicle.getTypeID(veh)  # 获取车辆类型\n    """\n    for veh in traci.vehicle.getIDList():\n        if traci.vehicle.getTypeID(veh) == \'CAV\':\n            v = traci.vehicle.getSpeed(veh)\n            # TODO: 实现您的速度控制逻辑\n            target_speed = 13.89  # 50 km/h\n            error = target_speed - v\n            new_speed = max(0, v + 0.3 * error)\n            traci.vehicle.setSpeed(veh, new_speed)\n'
};

class VehicleSpeedControl {
    constructor() {
        this.isRunning = false;
        this.pollTimer = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.updateAlgorithmDesc();
        this.updateAlgorithmDisplay();
        this.initCodeEditor();
    }

    bindEvents() {
        var self = this;
        var algoSelect = document.getElementById('algorithmSelect');
        if (algoSelect) algoSelect.addEventListener('change', function() { self.updateAlgorithmDesc(); self.updateAlgorithmDisplay(); });

        document.getElementById('startSimulation').addEventListener('click', function() { self.startSimulation(); });
        document.getElementById('resetParams').addEventListener('click', function() { self.resetParams(); });

        var exportBtn = document.getElementById('exportResultsBtn');
        if (exportBtn) exportBtn.addEventListener('click', function() { self.exportResults(); });
        var exportReportBtn = document.getElementById('exportReportBtn');
        if (exportReportBtn) exportReportBtn.addEventListener('click', function() { self.exportReport(); });
        var backBtn = document.getElementById('backBtn');
        if (backBtn) backBtn.addEventListener('click', function() { window.history.back(); });

        document.querySelectorAll('.config-file-btn').forEach(function(btn) {
            btn.addEventListener('click', function(e) { e.currentTarget.classList.toggle('step-done'); });
        });

        var submitCustomBtn = document.getElementById('submitCustomAlgo');
        if (submitCustomBtn) submitCustomBtn.addEventListener('click', function() { self.submitCustomAlgorithm(); });
        var confirmCodeBtn = document.getElementById('confirmCodeBtn');
        if (confirmCodeBtn) confirmCodeBtn.addEventListener('click', function() { self.confirmCode(); });
        var templateSelect = document.getElementById('templateSelect');
        if (templateSelect) templateSelect.addEventListener('change', function() { self.handleTemplateChange(); self.resetConfirm(); });
        var resetTemplateBtn = document.getElementById('resetTemplateBtn');
        if (resetTemplateBtn) resetTemplateBtn.addEventListener('click', function() { self.handleTemplateChange(); self.resetConfirm(); });
        var expandBtn = document.getElementById('expandCodeBtn');
        if (expandBtn) expandBtn.addEventListener('click', function() { self.toggleCodeExpand(); });
        var overlay = document.getElementById('codeFullscreenOverlay');
        if (overlay) overlay.addEventListener('click', function() { self.toggleCodeExpand(); });
    }

    updateAlgorithmDesc() {
        var algo = document.getElementById('algorithmSelect').value;
        var el = document.getElementById('algorithmDesc');
        if (el) el.innerHTML = '<p>' + (ALGO_DESCRIPTIONS[algo] || '') + '</p>';
    }

    updateAlgorithmDisplay() {
        var algo = document.getElementById('algorithmSelect').value;
        var el = document.getElementById('currentAlgorithm');
        if (el) el.textContent = ALGO_NAMES[algo] || '未知';
    }

    setStatus(text) {
        var el = document.getElementById('currentStatus');
        if (el) el.textContent = '状态: ' + text;
    }

    updateTimestamp() {
        var el = document.getElementById('updateTime');
        if (el) el.textContent = new Date().toLocaleString('zh-CN');
    }

    // ========== 代码编辑器 ==========
    initCodeEditor() {
        var self = this;
        var editor = document.getElementById('codeEditor');
        if (!editor) return;
        this.codeConfirmed = false;
        this.handleTemplateChange();
        editor.addEventListener('input', function() { self.updateHighlight(); self.resetConfirm(); });
        editor.addEventListener('scroll', function() {
            var highlight = document.getElementById('codeHighlight');
            if (highlight) { highlight.scrollTop = editor.scrollTop; highlight.scrollLeft = editor.scrollLeft; }
        });
        editor.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                e.preventDefault();
                var start = editor.selectionStart, end = editor.selectionEnd;
                editor.value = editor.value.substring(0, start) + '    ' + editor.value.substring(end);
                editor.selectionStart = editor.selectionEnd = start + 4;
                self.updateHighlight();
            }
        });
    }

    handleTemplateChange() {
        var sel = document.getElementById('templateSelect');
        var editor = document.getElementById('codeEditor');
        if (!sel || !editor) return;
        editor.value = SPEED_TEMPLATES[sel.value] || SPEED_TEMPLATES['custom'];
        this.updateHighlight();
    }

    updateHighlight() {
        var editor = document.getElementById('codeEditor');
        var codeEl = document.getElementById('codeHighlightCode');
        if (!editor || !codeEl) return;
        codeEl.innerHTML = this.highlightPython(editor.value);
    }

    highlightPython(code) {
        var escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        escaped = escaped.replace(/("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="py-string">$1</span>');
        escaped = escaped.replace(/(#.*$)/gm, '<span class="py-comment">$1</span>');
        escaped = escaped.replace(/\b(def|class|return|if|elif|else|for|while|import|from|as|try|except|finally|with|yield|lambda|pass|break|continue|raise|in|not|and|or|is|None|True|False|global|nonlocal|assert|del)\b/g, '<span class="py-keyword">$1</span>');
        escaped = escaped.replace(/\b(print|len|range|sum|max|min|round|int|float|str|list|dict|tuple|set|type|isinstance|enumerate|zip|map|filter|sorted|abs|open|super|getattr|setattr|hasattr)\b/g, '<span class="py-builtin">$1</span>');
        escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="py-number">$1</span>');
        escaped = escaped.replace(/\b(self)\b/g, '<span class="py-self">$1</span>');
        escaped = escaped.replace(/^(@\w+)/gm, '<span class="py-decorator">$1</span>');
        return escaped;
    }

    toggleCodeExpand() {
        var wrapper = document.getElementById('codeEditorWrapper');
        var overlay = document.getElementById('codeFullscreenOverlay');
        var btn = document.getElementById('expandCodeBtn');
        if (!wrapper) return;
        var isFs = wrapper.classList.toggle('fullscreen');
        if (overlay) overlay.classList.toggle('active', isFs);
        if (btn) btn.textContent = isFs ? '⛶ 缩小' : '⛶ 放大';
    }

    // ========== 确认代码 ==========
    confirmCode() {
        var editor = document.getElementById('codeEditor');
        var code = editor ? editor.value.trim() : '';
        if (!code) { alert('请先编写算法代码'); return; }
        this.codeConfirmed = true;
        var confirmBtn = document.getElementById('confirmCodeBtn');
        var submitBtn = document.getElementById('submitCustomAlgo');
        if (confirmBtn) { confirmBtn.textContent = '✅ 已确认'; confirmBtn.style.background = '#888'; confirmBtn.disabled = true; }
        if (submitBtn) { submitBtn.disabled = false; }
        var statusEl = document.getElementById('customAlgoStatus');
        if (statusEl) statusEl.textContent = '代码已确认，可以点击运行';
    }

    resetConfirm() {
        this.codeConfirmed = false;
        var confirmBtn = document.getElementById('confirmCodeBtn');
        var submitBtn = document.getElementById('submitCustomAlgo');
        if (confirmBtn) { confirmBtn.textContent = '✅ 确认代码'; confirmBtn.style.background = '#27ae60'; confirmBtn.disabled = false; }
        if (submitBtn) { submitBtn.disabled = true; }
        var statusEl = document.getElementById('customAlgoStatus');
        if (statusEl) statusEl.textContent = '';
    }

    parseParamsFromCode(code, algoKey) {
        // 从编辑器代码中解析 __init__ 参数
        var params = {};
        var initMatch = code.match(/def __init__\s*\(self[^)]*\)/);
        if (!initMatch) return params;
        var initLine = initMatch[0];
        // 匹配 key=value 对
        var paramRegex = /(\w+)\s*=\s*([0-9.]+)/g;
        var m;
        while ((m = paramRegex.exec(initLine)) !== null) {
            if (m[1] !== 'self') params[m[1]] = parseFloat(m[2]);
        }
        return params;
    }

    // ========== 自定义算法提交 ==========
    async submitCustomAlgorithm() {
        var editor = document.getElementById('codeEditor');
        var code = editor ? editor.value.trim() : '';
        if (!code) { alert('请先编写自定义算法代码'); return; }
        if (!this.codeConfirmed) { alert('请先点击"确认代码"按钮'); return; }
        if (this.isRunning) { alert('仿真正在运行中，请等待完成'); return; }

        // 模板算法：解析参数，调用 /run 接口
        var tplSel = document.getElementById('templateSelect');
        var tplVal = tplSel ? tplSel.value : 'custom';
        var TPL_TO_ALGO = { 'idm_tpl': 'idm', 'acc_tpl': 'acc', 'cacc_tpl': 'cacc', 'pid_tpl': 'pid' };

        if (TPL_TO_ALGO[tplVal]) {
            var algoKey = TPL_TO_ALGO[tplVal];
            var params = this.parseParamsFromCode(code, algoKey);
            document.getElementById('algorithmSelect').value = algoKey;
            this.updateAlgorithmDesc();
            this.updateAlgorithmDisplay();
            this.startSimulation(params);
            return;
        }

        // 自定义模板 -> 服务器后台任务执行用户代码
        var statusEl = document.getElementById('customAlgoStatus');
        var submitBtn = document.getElementById('submitCustomAlgo');
        if (statusEl) statusEl.textContent = '正在提交...';
        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '运行中...'; }

        var flowLevel = parseInt(document.getElementById('flowLevel').value);
        var pr = parseInt(document.getElementById('prSelect').value);

        try {
            var resp = await fetch(API_BASE + '/run-custom', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, flow_level: flowLevel, pr: pr })
            });
            var data = await resp.json();
            if (resp.ok && data.success) {
                if (statusEl) statusEl.textContent = '✅ ' + data.message;
                this.setStatus('自定义算法运行中（服务器后台任务）...');
                this.isRunning = true;
                this.pollStatus();
            } else {
                if (statusEl) statusEl.textContent = '❌ ' + (data.message || data.detail || '未知错误');
            }
        } catch (err) {
            if (statusEl) statusEl.textContent = '❌ 后端服务未响应';
        }
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = '▶ 运行自定义算法'; }
    }

    // ========== 核心：启动仿真 ==========
    async startSimulation(params) {
        if (this.isRunning) return;
        var algo = document.getElementById('algorithmSelect').value;
        var flowLevel = parseInt(document.getElementById('flowLevel').value);
        var pr = parseInt(document.getElementById('prSelect').value);
        var algoName = ALGO_NAMES[algo];

        this.isRunning = true;
        this.setStatus('正在启动 ' + algoName + ' 车速控制仿真...');
        var btn = document.getElementById('startSimulation');
        btn.textContent = '仿真中...'; btn.disabled = true;
        this.showSimulationRunning(algoName, flowLevel, pr);

        var body = { algorithm: algo, flow_level: flowLevel, pr: pr, use_gui: true };
        if (params && Object.keys(params).length > 0) body.params = params;

        try {
            var resp = await fetch(API_BASE + '/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            var data = await resp.json();
            if (resp.ok && data.success) {
                this.setStatus(algoName + ' 仿真中（服务器后台运行中）...');
                this.pollStatus();
            } else {
                this.setStatus('启动失败: ' + (data.message || data.detail || 'HTTP ' + resp.status));
                this.resetButton(); this.clearRunningStatus();
            }
        } catch (err) {
            this.setStatus('后端服务未响应，请确认服务器已启动');
            this.resetButton(); this.clearRunningStatus();
        }
    }

    showSimulationRunning(algoName, flowLevel, pr) {
        var summary = document.getElementById('resultSummary');
        if (summary) {
            summary.innerHTML = '<div style="text-align:center;padding:30px 20px;">' +
                '<div style="font-size:48px;margin-bottom:12px;">⏳</div>' +
                '<div style="font-size:16px;font-weight:500;color:#2c3e50;">' + algoName + ' 车速控制仿真运行中</div>' +
                '<div style="font-size:13px;color:#999;margin-top:8px;">流量等级: ' + flowLabel(flowLevel) + ' | 渗透率: ' + pr + '% | 网页会自动刷新运行状态</div>' +
                '<div style="margin-top:15px;color:#2C5AA0;font-size:13px;">SUMO仿真运行中，CAV车辆速度实时控制...</div></div>';
        }
    }

    clearRunningStatus() {
        var summary = document.getElementById('resultSummary');
        if (summary) summary.innerHTML = '<p style="color:#999;text-align:center;padding:20px;">暂无结果，请先运行仿真</p>';
    }

    pollStatus() {
        var self = this;
        if (this.pollTimer) clearInterval(this.pollTimer);
        this.pollTimer = setInterval(async function() {
            try {
                var resp = await fetch(API_BASE + '/status');
                var s = await resp.json();
                if (s.running) {
                    self.setStatus('仿真运行中（服务器后台任务）...');
                } else {
                    clearInterval(self.pollTimer); self.pollTimer = null;
                    if (s.success) {
                        self.setStatus(s.message || '仿真完成');
                        self.updateTimestamp();
                        if (s.results) self.displayResults(s.results, s.config_name);
                        else if (s.config_name) self.loadAndDisplayResults(s.config_name);
                    } else {
                        self.setStatus('仿真失败: ' + (s.message || '未知错误'));
                        self.clearRunningStatus();
                    }
                    self.resetButton();
                }
            } catch (e) { console.warn('轮询失败:', e); }
        }, 3000);
    }

    async loadAndDisplayResults(configName) {
        try {
            var resp = await fetch(API_BASE + '/results/' + configName);
            if (resp.ok) { var results = await resp.json(); this.displayResults(results, configName); }
        } catch (e) { console.warn('加载结果失败:', e); }
    }

    displayResults(results, configName) {
        var summary = document.getElementById('resultSummary');
        if (summary) {
            summary.innerHTML =
                '<div style="text-align:left;width:100%;padding:20px;">' +
                '<h4 style="color:#2C5AA0;margin-bottom:15px;font-size:16px;">✅ 仿真结果 - ' + (results.algorithm || '') + '</h4>' +
                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">' +
                    '<div style="background:#f0f7ff;padding:12px;border-radius:6px;border-left:3px solid #2C5AA0;">' +
                        '<div style="font-size:12px;color:#666;">平均延误</div>' +
                        '<div style="font-size:20px;font-weight:bold;color:#2c3e50;">' + (results.average_delay != null ? results.average_delay + 's' : '--') + '</div></div>' +
                    '<div style="background:#f0fff0;padding:12px;border-radius:6px;border-left:3px solid #27ae60;">' +
                        '<div style="font-size:12px;color:#666;">平均速度</div>' +
                        '<div style="font-size:20px;font-weight:bold;color:#2c3e50;">' + (results.avg_speed != null ? results.avg_speed + ' km/h' : '--') + '</div></div>' +
                    '<div style="background:#fff8f0;padding:12px;border-radius:6px;border-left:3px solid #f39c12;">' +
                        '<div style="font-size:12px;color:#666;">速度标准差</div>' +
                        '<div style="font-size:20px;font-weight:bold;color:#2c3e50;">' + (results.speed_std != null ? results.speed_std + ' km/h' : '--') + '</div></div>' +
                    '<div style="background:#fff0f0;padding:12px;border-radius:6px;border-left:3px solid #e74c3c;">' +
                        '<div style="font-size:12px;color:#666;">吞吐量</div>' +
                        '<div style="font-size:20px;font-weight:bold;color:#2c3e50;">' + (results.throughput != null ? results.throughput + ' 辆' : '--') + '</div></div>' +
                '</div>' +
                '<div style="margin-top:12px;font-size:12px;color:#888;">' +
                    '流量等级: ' + flowLabel(results.flow_level || '--') + ' | 渗透率: ' + (results.pr || '--') + '% | 运行时间: ' + (results.runtime || '--') + 's | 配置: ' + (configName || '--') +
                '</div></div>';
        }
        if (configName) this.loadOutputFiles(configName);
    }

    async loadOutputFiles(configName) {
        try {
            var resp = await fetch(API_BASE + '/output/' + configName);
            if (!resp.ok) return;
            var data = await resp.json();
            var imgFiles = data.files.filter(function(f) { return f.name.match(/\.(png|jpg|jpeg)$/i); });
            var dataFiles = data.files.filter(function(f) { return f.name.match(/\.(xlsx|csv|json)$/i); });
            var container = document.getElementById('resultImages');
            if (!container) return;
            var html = '';
            imgFiles.forEach(function(f) {
                html += '<div class="result-image-item"><img src="' + API_BASE + '/output-file/' + configName + '/' + f.name + '" alt="' + f.name + '" class="result-img"><p class="result-img-caption">' + f.name + '</p></div>';
            });
            if (dataFiles.length > 0) {
                html += '<div style="padding:10px;"><p style="font-weight:600;margin-bottom:8px;">📁 输出文件：</p>';
                dataFiles.forEach(function(f) {
                    html += '<a href="' + API_BASE + '/output-file/' + configName + '/' + f.name + '" download style="display:block;padding:6px 0;color:#2C5AA0;text-decoration:none;">📄 ' + f.name + ' (' + (f.size/1024).toFixed(1) + 'KB)</a>';
                });
                html += '</div>';
            }
            container.innerHTML = html || '<p style="color:#999;text-align:center;padding:20px;">暂无输出文件</p>';
        } catch (e) { console.warn('加载输出文件失败:', e); }
    }

    resetButton() {
        this.isRunning = false;
        var btn = document.getElementById('startSimulation');
        if (btn) { btn.textContent = '开始仿真'; btn.disabled = false; }
    }

    resetParams() {
        if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
        this.isRunning = false;
        document.getElementById('algorithmSelect').value = 'idm';
        document.getElementById('flowLevel').value = '4';
        document.getElementById('prSelect').value = '40';
        this.updateAlgorithmDesc(); this.updateAlgorithmDisplay();
        this.clearRunningStatus();
        var ri = document.getElementById('resultImages');
        if (ri) ri.innerHTML = '<p style="color:#999;text-align:center;padding:40px 20px;">运行仿真后将在此显示输出图表和数据文件</p>';
        document.querySelectorAll('.config-file-btn').forEach(function(b) { b.classList.remove('step-done'); });
        this.setStatus('就绪');
        document.getElementById('updateTime').textContent = '--:--:--';
        this.resetButton();
        fetch(API_BASE + '/reset', { method: 'POST' }).catch(function() {});
    }

    async exportResults() {
        var results = null;
        try { var resp = await fetch(API_BASE + '/status'); var s = await resp.json(); if (s.results) results = s.results; } catch (e) {}
        var algo = document.getElementById('algorithmSelect').value;
        var algoName = ALGO_NAMES[algo];
        var flowLevel = document.getElementById('flowLevel').value;
        var pr = document.getElementById('prSelect').value;
        var csv = '\uFEFF车速控制仿真结果\n生成时间,' + new Date().toLocaleString('zh-CN') + '\n算法,' + algoName + '\n流量等级,' + flowLabel(flowLevel) + '\nCAV渗透率,' + pr + '%\n\n';
        if (results) {
            csv += '指标名称,数值\n平均延误(s),' + (results.average_delay || '--') + '\n平均速度(km/h),' + (results.avg_speed || '--') + '\n速度标准差(km/h),' + (results.speed_std || '--') + '\n吞吐量(辆),' + (results.throughput || '--') + '\n运行时间(s),' + (results.runtime || '--') + '\n';
        } else { csv += '（暂无仿真结果）\n'; }
        var blob = new Blob([csv], { type: 'text/csv;charset=utf-8-sig' });
        var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = '车速控制结果_' + algoName + '_flow' + flowLevel + '_pr' + pr + '_' + Date.now() + '.csv';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
    }

    exportReport() {
        var algo = document.getElementById('algorithmSelect').value;
        var algoName = ALGO_NAMES[algo];
        var flowLevel = document.getElementById('flowLevel').value;
        var pr = document.getElementById('prSelect').value;
        var currentTime = new Date().toLocaleString('zh-CN');
        var html = '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>车速控制实验报告</title>' +
            '<style>body{font-family:"Microsoft YaHei",Arial,sans-serif;line-height:1.8;margin:40px;}h1{text-align:center;color:#2C5AA0;}h2{color:#2C5AA0;border-bottom:2px solid #2C5AA0;padding-bottom:5px;margin-top:30px;}table{width:100%;border-collapse:collapse;margin:15px 0;}th,td{border:1px solid #ddd;padding:10px;text-align:left;}th{background:#2C5AA0;color:white;}.info-box{background:#E8F4F8;padding:15px;border-left:4px solid #2C5AA0;margin:15px 0;}</style></head><body>' +
            '<h1>车速控制实验报告</h1><p style="text-align:center;color:#666;">实验时间：' + currentTime + '</p>' +
            '<h2>一、实验配置</h2><table><tr><th>配置项</th><th>值</th></tr><tr><td>控制算法</td><td>' + algoName + '</td></tr><tr><td>流量等级</td><td>' + flowLabel(flowLevel) + '</td></tr><tr><td>CAV渗透率</td><td>' + pr + '%</td></tr><tr><td>仿真平台</td><td>SUMO + TraCI</td></tr><tr><td>路网</td><td>SiouxFalls</td></tr></table>' +
            '<h2>二、算法说明</h2><div class="info-box">' + (ALGO_DESCRIPTIONS[algo] || '') + '</div>' +
            '<h2>三、实验结果</h2><p>（请在仿真完成后填写实际结果数据）</p>' +
            '<h2>四、实验心得</h2><p style="min-height:100px;border:1px dashed #ccc;padding:10px;"></p>' +
            '<div style="margin-top:50px;text-align:right;"><p>实验人员：___________　学号：___________</p><p>指导教师：___________　日期：' + currentTime.split(' ')[0] + '</p></div></body></html>';
        var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = '车速控制实验报告_' + algoName + '_' + Date.now() + '.doc';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
    }
}

document.addEventListener('DOMContentLoaded', function() { new VehicleSpeedControl(); });

(function() {
    function checkServer() {
        var el = document.getElementById('serverStatus');
        if (!el) return;
        fetch('/', { method: 'GET' })
            .then(function(r) { if (r.ok || r.status === 404 || r.status === 405) { el.textContent = '服务器: 已连接 ✓'; el.style.color = '#28a745'; } else { throw new Error(); } })
            .catch(function() { el.textContent = '服务器: 未连接 ✗'; el.style.color = '#dc3545'; });
    }
    document.addEventListener('DOMContentLoaded', function() { checkServer(); setInterval(checkServer, 30000); });
})();


