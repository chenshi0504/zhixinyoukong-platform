// 上层-交通信号优化功能 JavaScript
// 调用真实后端API，运行SUMO仿真

const API_BASE = '/api/signal-optimization';

// 算法描述映射
const ALGO_DESCRIPTIONS = {
    '2': '<strong>TuRBO</strong>：信任域贝叶斯优化，通过局部高斯过程建模在信任域内高效搜索最优信号配时参数，快速收敛。无需预训练。',
    '6': '<strong>BO</strong>：标准贝叶斯优化，全局高斯过程建模，样本效率高，适合参数空间较大的优化问题。无需预训练。',
    '4': '<strong>DQN</strong>：深度Q网络强化学习，通过预训练模型在线推理最优配时策略。<span style="color:#e74c3c">需要预训练模型</span>。',
    '5': '<strong>PPO</strong>：近端策略优化强化学习，策略梯度方法，稳定性好。<span style="color:#e74c3c">需要预训练模型</span>。',
    '7': '<strong>GA</strong>：遗传算法，传统元启发式方法，通过种群进化搜索最优解。无需预训练。',
    '8': '<strong>PSO</strong>：粒子群优化，群体智能搜索，粒子协作寻优。无需预训练。',
};

const SIG_TO_KEY = { '2': 'turbo', '6': 'bo', '4': 'dqn', '5': 'ppo', '7': 'ga', '8': 'pso' };
const SIG_TO_NAME = { '2': 'TuRBO', '6': 'BO', '4': 'DQN', '5': 'PPO', '7': 'GA', '8': 'PSO' };

// 流量等级显示映射 (内部值 -> 显示值)
const FLOW_DISPLAY = { '2': '1 (低流量)', '4': '2 (中流量)', '6': '3 (高流量)' };
function flowLabel(v) { return FLOW_DISPLAY[String(v)] || String(v); }

// 算法模板
const SIGNAL_TEMPLATES = {
    webster: '# Webster公式信号配时优化\n# 基于经典Webster公式计算最优周期和绿信比\n\nimport numpy as np\n\ndef optimize_signal(flow_data, saturation_flow=1800):\n    """\n    Webster公式配时优化\n    flow_data: dict, 各相位流量 {phase_id: flow_rate}\n    saturation_flow: 饱和流率(pcu/h)\n    """\n    # 计算各相位流量比\n    y_values = []\n    for phase_id, flow in flow_data.items():\n        y = flow / saturation_flow\n        y_values.append(y)\n    \n    Y = sum(y_values)  # 总流量比\n    L = len(y_values) * 4  # 总损失时间(每相位4s)\n    \n    # Webster最优周期\n    C0 = (1.5 * L + 5) / (1 - Y)\n    C0 = max(40, min(C0, 180))  # 限制在40-180s\n    \n    # 各相位有效绿灯时间\n    green_times = []\n    for y in y_values:\n        g = (y / Y) * (C0 - L)\n        g = max(10, round(g))  # 最小绿灯10s\n        green_times.append(g)\n    \n    return {\n        "cycle": round(C0),\n        "green_times": green_times,\n        "Y": round(Y, 3)\n    }\n\n# 示例调用\nflow_data = {0: 600, 1: 450, 2: 500, 3: 380}\nresult = optimize_signal(flow_data)\nprint(f"最优周期: {result[\'cycle\']}s")\nprint(f"绿灯时长: {result[\'green_times\']}")',
    ga_simple: '# 简易遗传算法信号配时优化\n# 使用遗传算法搜索最优绿灯时长分配\n\nimport numpy as np\nimport random\n\ndef ga_optimize(n_phases=4, pop_size=30, generations=50):\n    """\n    遗传算法优化信号配时\n    n_phases: 相位数\n    pop_size: 种群大小\n    generations: 迭代代数\n    """\n    cycle = 120  # 固定周期\n    min_green = 10\n    \n    # 初始化种群\n    population = []\n    for _ in range(pop_size):\n        greens = np.random.randint(min_green, 50, n_phases)\n        greens = (greens / greens.sum() * (cycle - n_phases * 4)).astype(int)\n        greens = np.maximum(greens, min_green)\n        population.append(greens)\n    \n    def fitness(greens):\n        # 模拟延误计算(简化)\n        delay = sum([(cycle - g)**2 / (2 * g) for g in greens])\n        return -delay  # 最小化延误\n    \n    for gen in range(generations):\n        scores = [fitness(ind) for ind in population]\n        # 选择\n        sorted_idx = np.argsort(scores)[::-1]\n        population = [population[i] for i in sorted_idx[:pop_size//2]]\n        # 交叉 + 变异\n        children = []\n        while len(children) < pop_size // 2:\n            p1, p2 = random.sample(population, 2)\n            child = (p1 + p2) // 2\n            if random.random() < 0.2:  # 变异率\n                idx = random.randint(0, n_phases-1)\n                child[idx] += random.randint(-5, 5)\n            child = np.maximum(child, min_green)\n            children.append(child)\n        population.extend(children)\n    \n    best = max(population, key=fitness)\n    return {"green_times": best.tolist(), "fitness": fitness(best)}\n\nresult = ga_optimize()\nprint(f"最优绿灯: {result[\'green_times\']}")',
    greedy: '# 贪心信号配时优化\n# 按流量比例分配绿灯时间\n\ndef greedy_optimize(flows, cycle=120, min_green=10):\n    """\n    贪心策略：按流量比例分配绿灯\n    flows: list, 各相位流量\n    cycle: 信号周期(s)\n    min_green: 最小绿灯时间(s)\n    """\n    n = len(flows)\n    lost_time = n * 4  # 每相位损失4s\n    available = cycle - lost_time\n    \n    total_flow = sum(flows)\n    if total_flow == 0:\n        return [available // n] * n\n    \n    # 按流量比例分配\n    greens = []\n    for f in flows:\n        g = max(min_green, round(f / total_flow * available))\n        greens.append(g)\n    \n    # 调整使总和等于可用时间\n    diff = available - sum(greens)\n    if diff != 0:\n        max_idx = greens.index(max(greens))\n        greens[max_idx] += diff\n    \n    return greens\n\n# 示例\nflows = [600, 450, 500, 380]\nresult = greedy_optimize(flows)\nprint(f"各相位绿灯: {result}")\nprint(f"总有效绿灯: {sum(result)}s")',
    custom: '# 自定义信号优化算法\n# 请在此编写您的算法\n\ndef my_signal_optimizer(intersection_data):\n    """\n    自定义信号优化函数\n    \n    参数:\n        intersection_data: dict\n            - flows: 各相位流量列表\n            - cycle: 信号周期\n            - n_phases: 相位数\n    \n    返回:\n        green_times: 各相位绿灯时长列表\n    """\n    flows = intersection_data.get("flows", [500, 400, 450, 350])\n    cycle = intersection_data.get("cycle", 120)\n    n_phases = len(flows)\n    \n    # TODO: 在此实现您的优化算法\n    green_times = [cycle // n_phases] * n_phases\n    \n    return green_times\n'
};

class SignalOptimization {
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
        const algoSelect = document.getElementById('algorithmSelect');
        if (algoSelect) {
            algoSelect.addEventListener('change', () => {
                this.updateAlgorithmDesc();
                this.updateAlgorithmDisplay();
            });
        }

        document.getElementById('startSimulation').addEventListener('click', () => this.startSimulation());
        document.getElementById('resetParams').addEventListener('click', () => this.resetParams());

        const exportBtn = document.getElementById('exportResultsBtn');
        if (exportBtn) exportBtn.addEventListener('click', () => this.exportResults());

        const exportReportBtn = document.getElementById('exportReportBtn');
        if (exportReportBtn) exportReportBtn.addEventListener('click', () => this.exportReport());

        const backBtn = document.getElementById('backBtn');
        if (backBtn) backBtn.addEventListener('click', () => window.history.back());

        // 配置文件按钮
        document.querySelectorAll('.config-file-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleConfigClick(e.currentTarget));
        });

        // 自主算法设计
        const submitCustomBtn = document.getElementById('submitCustomAlgo');
        if (submitCustomBtn) submitCustomBtn.addEventListener('click', () => this.submitCustomAlgorithm());

        const confirmCodeBtn = document.getElementById('confirmCodeBtn');
        if (confirmCodeBtn) confirmCodeBtn.addEventListener('click', () => this.confirmCode());

        // 模板选择
        const templateSelect = document.getElementById('templateSelect');
        if (templateSelect) templateSelect.addEventListener('change', () => { this.handleTemplateChange(); this.resetConfirm(); });

        // 恢复模板
        const resetTemplateBtn = document.getElementById('resetTemplateBtn');
        if (resetTemplateBtn) resetTemplateBtn.addEventListener('click', () => { this.handleResetTemplate(); this.resetConfirm(); });

        // 放大/缩小代码编辑器
        const expandBtn = document.getElementById('expandCodeBtn');
        if (expandBtn) expandBtn.addEventListener('click', () => this.toggleCodeExpand());

        // 全屏遮罩点击关闭
        const overlay = document.getElementById('codeFullscreenOverlay');
        if (overlay) overlay.addEventListener('click', () => this.toggleCodeExpand());
    }

    updateAlgorithmDesc() {
        const sig = document.getElementById('algorithmSelect').value;
        const descEl = document.getElementById('algorithmDesc');
        if (descEl) descEl.innerHTML = '<p>' + (ALGO_DESCRIPTIONS[sig] || '') + '</p>';
    }

    updateAlgorithmDisplay() {
        const sig = document.getElementById('algorithmSelect').value;
        const el = document.getElementById('currentAlgorithm');
        if (el) el.textContent = SIG_TO_NAME[sig] || '未知';
    }

    setStatus(text) {
        const el = document.getElementById('currentStatus');
        if (el) el.textContent = '状态: ' + text;
    }

    updateTimestamp() {
        const el = document.getElementById('updateTime');
        if (el) el.textContent = new Date().toLocaleString('zh-CN');
    }

    // 配置文件按钮点击 - 蓝色→白色 (step-done)
    handleConfigClick(btn) {
        btn.classList.toggle('step-done');
    }

    // ========== 代码编辑器 ==========
    initCodeEditor() {
        const editor = document.getElementById('codeEditor');
        if (!editor) return;
        this.codeConfirmed = false;
        // 加载默认模板
        this.handleTemplateChange();
        // 输入时同步高亮
        editor.addEventListener('input', () => { this.updateHighlight(); this.resetConfirm(); });
        editor.addEventListener('scroll', () => this.syncScroll());
        // Tab键支持
        editor.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                e.preventDefault();
                var start = editor.selectionStart;
                var end = editor.selectionEnd;
                editor.value = editor.value.substring(0, start) + '    ' + editor.value.substring(end);
                editor.selectionStart = editor.selectionEnd = start + 4;
                this.updateHighlight();
            }
        });
    }

    handleTemplateChange() {
        var sel = document.getElementById('templateSelect');
        var editor = document.getElementById('codeEditor');
        if (!sel || !editor) return;
        var tpl = SIGNAL_TEMPLATES[sel.value] || SIGNAL_TEMPLATES['custom'];
        editor.value = tpl;
        this.updateHighlight();
    }

    handleResetTemplate() {
        this.handleTemplateChange();
    }

    updateHighlight() {
        var editor = document.getElementById('codeEditor');
        var codeEl = document.getElementById('codeHighlightCode');
        if (!editor || !codeEl) return;
        codeEl.innerHTML = this.highlightPython(editor.value);
    }

    syncScroll() {
        var editor = document.getElementById('codeEditor');
        var highlight = document.getElementById('codeHighlight');
        if (editor && highlight) {
            highlight.scrollTop = editor.scrollTop;
            highlight.scrollLeft = editor.scrollLeft;
        }
    }

    highlightPython(code) {
        // 简易Python语法高亮
        var escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        // 字符串（三引号、单双引号）
        escaped = escaped.replace(/("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="py-string">$1</span>');
        // 注释
        escaped = escaped.replace(/(#.*$)/gm, '<span class="py-comment">$1</span>');
        // 关键字
        var kw = '\\b(def|class|return|if|elif|else|for|while|import|from|as|try|except|finally|with|yield|lambda|pass|break|continue|raise|in|not|and|or|is|None|True|False|global|nonlocal|assert|del)\\b';
        escaped = escaped.replace(new RegExp(kw, 'g'), '<span class="py-keyword">$1</span>');
        // 内置函数
        var bi = '\\b(print|len|range|sum|max|min|round|int|float|str|list|dict|tuple|set|type|isinstance|enumerate|zip|map|filter|sorted|abs|open|super|getattr|setattr|hasattr)\\b';
        escaped = escaped.replace(new RegExp(bi, 'g'), '<span class="py-builtin">$1</span>');
        // 数字
        escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="py-number">$1</span>');
        // self
        escaped = escaped.replace(/\b(self)\b/g, '<span class="py-self">$1</span>');
        // 装饰器
        escaped = escaped.replace(/^(@\w+)/gm, '<span class="py-decorator">$1</span>');
        return escaped;
    }

    toggleCodeExpand() {
        var wrapper = document.getElementById('codeEditorWrapper');
        var overlay = document.getElementById('codeFullscreenOverlay');
        var btn = document.getElementById('expandCodeBtn');
        if (!wrapper) return;
        var isFullscreen = wrapper.classList.toggle('fullscreen');
        if (overlay) overlay.classList.toggle('active', isFullscreen);
        if (btn) btn.textContent = isFullscreen ? '⛶ 缩小' : '⛶ 放大';
    }

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

    // 自主算法设计提交 - 调用后端在服务器后台任务运行
    async submitCustomAlgorithm() {
        var editor = document.getElementById('codeEditor');
        var code = editor ? editor.value.trim() : '';
        if (!code) {
            alert('请先编写自定义算法代码');
            return;
        }
        if (!this.codeConfirmed) {
            alert('请先点击"确认代码"按钮');
            return;
        }
        if (this.isRunning) {
            alert('仿真正在运行中，请等待完成');
            return;
        }

        var statusEl = document.getElementById('customAlgoStatus');
        var submitBtn = document.getElementById('submitCustomAlgo');
        if (statusEl) statusEl.textContent = '正在提交...';
        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '运行中...'; }

        var flowLevel = parseInt(document.getElementById('flowLevel').value);

        try {
            var resp = await fetch(API_BASE + '/run-custom', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, flow_level: flowLevel })
            });
            var data = await resp.json();
            if (data.success) {
                if (statusEl) statusEl.textContent = '✅ ' + data.message;
                this.setStatus('自定义算法运行中（服务器后台任务）...');
                this.isRunning = true;
                this.pollStatus();
            } else {
                if (statusEl) statusEl.textContent = '❌ ' + data.message;
            }
        } catch (err) {
            if (statusEl) statusEl.textContent = '❌ 后端服务未响应';
        }

        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = '▶ 运行自定义算法'; }
    }

    // ========== 核心：启动仿真 ==========
    async startSimulation() {
        if (this.isRunning) return;

        const sig = document.getElementById('algorithmSelect').value;
        const algoKey = SIG_TO_KEY[sig];
        const flowLevel = parseInt(document.getElementById('flowLevel').value);
        const algoName = SIG_TO_NAME[sig];

        this.isRunning = true;
        this.setStatus('正在启动 ' + algoName + ' 仿真...');

        const btn = document.getElementById('startSimulation');
        btn.textContent = '仿真中...';
        btn.disabled = true;

        // 显示运行中状态到结果摘要区
        this.showSimulationRunning(algoName, flowLevel);

        try {
            const resp = await fetch(API_BASE + '/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ algorithm: algoKey, flow_level: flowLevel, use_gui: false })
            });
            const data = await resp.json();

            if (data.success) {
                this.setStatus(algoName + ' 仿真中（服务器后台运行中）...');
                this.pollStatus();
            } else {
                this.setStatus('启动失败: ' + data.message);
                this.resetButton();
                this.clearRunningStatus();
            }
        } catch (err) {
            console.error('启动仿真失败:', err);
            this.setStatus('后端服务未响应，请确认服务器已启动');
            this.resetButton();
            this.clearRunningStatus();
        }
    }

    // 显示仿真运行中状态（更新 #resultSummary）
    showSimulationRunning(algoName, flowLevel) {
        const summary = document.getElementById('resultSummary');
        if (summary) {
            summary.innerHTML =
                '<div style="text-align:center; padding:30px 20px;">' +
                '<div style="font-size:48px; margin-bottom:12px;">⏳</div>' +
                '<div style="font-size:16px; font-weight:500; color:#2c3e50;">' + algoName + ' 信号优化仿真运行中</div>' +
                '<div style="font-size:13px; color:#999; margin-top:8px;">流量等级: ' + flowLabel(flowLevel) + ' | 网页会自动刷新运行状态</div>' +
                '<div style="margin-top:15px; color:#2C5AA0; font-size:13px;">SUMO仿真引擎正在运行...</div>' +
                '</div>';
        }
    }

    // 清除运行中状态
    clearRunningStatus() {
        const summary = document.getElementById('resultSummary');
        if (summary) {
            summary.innerHTML = '<p style="color:#999; text-align:center; padding:20px;">暂无结果，请先运行仿真</p>';
        }
    }

    // 轮询仿真状态
    pollStatus() {
        if (this.pollTimer) clearInterval(this.pollTimer);

        this.pollTimer = setInterval(async () => {
            try {
                const resp = await fetch(API_BASE + '/status');
                const s = await resp.json();

                if (s.running) {
                    this.setStatus('仿真运行中（服务器后台任务）...');
                } else {
                    clearInterval(this.pollTimer);
                    this.pollTimer = null;

                    if (s.success) {
                        this.setStatus(s.message || '仿真完成');
                        this.updateTimestamp();
                        if (s.results) {
                            this.displayResults(s.results, s.config_name);
                        } else if (s.config_name) {
                            await this.loadAndDisplayResults(s.config_name);
                        }
                    } else {
                        this.setStatus('仿真失败: ' + (s.message || '未知错误'));
                        this.clearRunningStatus();
                    }
                    this.resetButton();
                }
            } catch (e) {
                console.warn('轮询状态失败:', e);
            }
        }, 3000);
    }

    // 加载并展示结果
    async loadAndDisplayResults(configName) {
        try {
            const resp = await fetch(API_BASE + '/results/' + configName);
            if (resp.ok) {
                const results = await resp.json();
                this.displayResults(results, configName);
            }
        } catch (e) {
            console.warn('加载结果失败:', e);
        }
    }

    // 展示仿真结果（更新 #resultSummary）
    displayResults(results, configName) {
        const summary = document.getElementById('resultSummary');
        if (summary) {
            summary.innerHTML =
                '<div style="text-align:left; width:100%; padding:20px;">' +
                '<h4 style="color:#2C5AA0; margin-bottom:15px; font-size:16px;">✅ 仿真结果 - ' + (results.algorithm || '') + '</h4>' +
                '<div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">' +
                    '<div style="background:#f0f7ff; padding:12px; border-radius:6px; border-left:3px solid #2C5AA0;">' +
                        '<div style="font-size:12px; color:#666;">平均延误</div>' +
                        '<div style="font-size:20px; font-weight:bold; color:#2c3e50;">' + (results.average_delay != null ? results.average_delay.toFixed(1) + 's' : '--') + '</div>' +
                    '</div>' +
                    '<div style="background:#f0fff0; padding:12px; border-radius:6px; border-left:3px solid #27ae60;">' +
                        '<div style="font-size:12px; color:#666;">通过车辆数</div>' +
                        '<div style="font-size:20px; font-weight:bold; color:#2c3e50;">' + (results.throughput || '--') + '</div>' +
                    '</div>' +
                    '<div style="background:#fff8f0; padding:12px; border-radius:6px; border-left:3px solid #f39c12;">' +
                        '<div style="font-size:12px; color:#666;">总行程时间</div>' +
                        '<div style="font-size:20px; font-weight:bold; color:#2c3e50;">' + (results.total_time != null ? results.total_time.toFixed(0) + 's' : '--') + '</div>' +
                    '</div>' +
                    '<div style="background:#fff0f0; padding:12px; border-radius:6px; border-left:3px solid #e74c3c;">' +
                        '<div style="font-size:12px; color:#666;">总燃油消耗</div>' +
                        '<div style="font-size:20px; font-weight:bold; color:#2c3e50;">' + (results.total_fuel != null ? results.total_fuel.toFixed(1) + 'L' : '--') + '</div>' +
                    '</div>' +
                '</div>' +
                '<div style="margin-top:12px; font-size:12px; color:#888;">' +
                    '流量等级: ' + flowLabel(results.flow_level || '--') + ' | 运行时间: ' + (results.runtime || '--') + 's | 配置: ' + (configName || '--') +
                '</div>' +
                '</div>';
        }

        // 加载结果图片
        if (configName) {
            this.loadOutputFiles(configName);
        }
    }

    // 加载输出文件列表（直接更新 #resultImages，始终可见）
    async loadOutputFiles(configName) {
        try {
            const resp = await fetch(API_BASE + '/output/' + configName);
            if (!resp.ok) return;
            const data = await resp.json();

            const imgFiles = data.files.filter(function(f) {
                return f.name.endsWith('.png') || f.name.endsWith('.jpg') || f.name.endsWith('.jpeg');
            });
            const dataFiles = data.files.filter(function(f) {
                return f.name.endsWith('.xlsx') || f.name.endsWith('.csv') || f.name.endsWith('.json');
            });

            const container = document.getElementById('resultImages');
            if (!container) return;

            var html = '';

            imgFiles.forEach(function(f) {
                html +=
                    '<div class="result-image-item">' +
                    '<img src="' + API_BASE + '/output-file/' + configName + '/' + f.name + '" alt="' + f.name + '" class="result-img">' +
                    '<p class="result-img-caption">' + f.name + '</p>' +
                    '</div>';
            });

            if (dataFiles.length > 0) {
                html += '<div style="padding:10px;">';
                html += '<p style="font-weight:600; margin-bottom:8px;">📁 输出文件：</p>';
                dataFiles.forEach(function(f) {
                    var sizeKB = (f.size / 1024).toFixed(1);
                    html += '<a href="' + API_BASE + '/output-file/' + configName + '/' + f.name + '" download ' +
                        'style="display:block; padding:6px 0; color:#2C5AA0; text-decoration:none;">' +
                        '📄 ' + f.name + ' (' + sizeKB + 'KB)</a>';
                });
                html += '</div>';
            }

            container.innerHTML = html || '<p style="color:#999; text-align:center; padding:20px;">暂无输出文件</p>';
        } catch (e) {
            console.warn('加载输出文件失败:', e);
        }
    }

    // 重置按钮状态
    resetButton() {
        this.isRunning = false;
        const btn = document.getElementById('startSimulation');
        if (btn) {
            btn.textContent = '开始仿真';
            btn.disabled = false;
        }
    }

    // 重置参数
    resetParams() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this.isRunning = false;

        document.getElementById('algorithmSelect').value = '2';
        document.getElementById('flowLevel').value = '4';
        this.updateAlgorithmDesc();
        this.updateAlgorithmDisplay();

        // 重置结果摘要
        this.clearRunningStatus();

        // 重置结果图片
        const resultImages = document.getElementById('resultImages');
        if (resultImages) {
            resultImages.innerHTML = '<p style="color:#999; text-align:center; padding:40px 20px;">运行仿真后将在此显示输出图表和数据文件</p>';
        }

        // 重置配置文件按钮
        document.querySelectorAll('.config-file-btn').forEach(function(b) {
            b.classList.remove('step-done');
        });

        this.setStatus('就绪');
        document.getElementById('updateTime').textContent = '--:--:--';
        this.resetButton();

        fetch(API_BASE + '/reset', { method: 'POST' }).catch(function() {});
    }

    // 导出结果CSV
    async exportResults() {
        var results = null;
        try {
            const resp = await fetch(API_BASE + '/status');
            const s = await resp.json();
            if (s.results) results = s.results;
        } catch (e) {}

        const sig = document.getElementById('algorithmSelect').value;
        const algoName = SIG_TO_NAME[sig];
        const flowLevel = document.getElementById('flowLevel').value;
        const timestamp = new Date().toLocaleString('zh-CN');

        var csv = '\uFEFF';
        csv += '交通信号优化仿真结果\n';
        csv += '生成时间,' + timestamp + '\n';
        csv += '算法,' + algoName + '\n';
        csv += '流量等级,' + flowLabel(flowLevel) + '\n\n';

        if (results) {
            csv += '指标名称,数值\n';
            csv += '平均延误(s),' + (results.average_delay || '--') + '\n';
            csv += '通过车辆数,' + (results.throughput || '--') + '\n';
            csv += '总行程时间(s),' + (results.total_time || '--') + '\n';
            csv += '总燃油消耗(L),' + (results.total_fuel || '--') + '\n';
            csv += '运行时间(s),' + (results.runtime || '--') + '\n';
        } else {
            csv += '（暂无仿真结果，请先运行仿真）\n';
        }

        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8-sig' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '信号优化结果_' + algoName + '_flow' + flowLevel + '_' + Date.now() + '.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // 导出实验报告
    exportReport() {
        const sig = document.getElementById('algorithmSelect').value;
        const algoName = SIG_TO_NAME[sig];
        const flowLevel = document.getElementById('flowLevel').value;
        const currentTime = new Date().toLocaleString('zh-CN');

        const html = '<!DOCTYPE html>' +
'<html lang="zh-CN"><head><meta charset="UTF-8"><title>交通信号优化实验报告</title>' +
'<style>' +
'body{font-family:"Microsoft YaHei",Arial,sans-serif;line-height:1.8;margin:40px;}' +
'h1{text-align:center;color:#2C5AA0;}' +
'h2{color:#2C5AA0;border-bottom:2px solid #2C5AA0;padding-bottom:5px;margin-top:30px;}' +
'table{width:100%;border-collapse:collapse;margin:15px 0;}' +
'th,td{border:1px solid #ddd;padding:10px;text-align:left;}' +
'th{background:#2C5AA0;color:white;}' +
'.info-box{background:#E8F4F8;padding:15px;border-left:4px solid #2C5AA0;margin:15px 0;}' +
'</style></head><body>' +
'<h1>交通信号优化实验报告</h1>' +
'<p style="text-align:center;color:#666;">实验时间：' + currentTime + '</p>' +
'<h2>一、实验配置</h2>' +
'<table><tr><th>配置项</th><th>值</th></tr>' +
'<tr><td>优化算法</td><td>' + algoName + '</td></tr>' +
'<tr><td>流量等级</td><td>' + flowLabel(flowLevel) + '</td></tr>' +
'<tr><td>仿真引擎</td><td>SUMO</td></tr>' +
'<tr><td>路网</td><td>SiouxFalls</td></tr></table>' +
'<h2>二、算法说明</h2>' +
'<div class="info-box">' + (ALGO_DESCRIPTIONS[sig] || '') + '</div>' +
'<h2>三、实验结果</h2>' +
'<p>（请在仿真完成后填写实际结果数据）</p>' +
'<h2>四、实验心得</h2>' +
'<p style="min-height:100px;border:1px dashed #ccc;padding:10px;"></p>' +
'<div style="margin-top:50px;text-align:right;">' +
'<p>实验人员：___________　学号：___________</p>' +
'<p>指导教师：___________　日期：' + currentTime.split(' ')[0] + '</p>' +
'</div></body></html>';

        const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '信号优化实验报告_' + algoName + '_' + Date.now() + '.doc';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    new SignalOptimization();
});

// 服务器状态检测
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


