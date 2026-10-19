// 中层-路径诱导功能 JavaScript
// 调用真实后端API，运行SUMO路径诱导算法（SSP / A*）

const API_BASE = '/api/path-guidance';

// 算法描述映射
const ALGO_DESCRIPTIONS = {
    'dijkstra': '<strong>Dijkstra</strong>：经典最短路径算法，基于实时effort值（旅行时间+拥堵延迟+信号延迟）动态重路由CAV车辆，贪心策略保证最优解。',
    'ssp': '<strong>SSP</strong>：逐次最短路径算法（Successive Shortest Path），基于实时路网effort值逐步求解最优路径分配方案，周期性为CAV车辆重新规划路径。',
    'astar': '<strong>A*</strong>：启发式搜索算法，通过估价函数f(n)=g(n)+h(n)加速寻路，仅考虑路段长度的静态最短路径规划。',
};

const ALGO_NAMES = {
    'dijkstra': 'Dijkstra',
    'ssp': 'SSP',
    'astar': 'A*',
};

// 流量模式显示映射；后端以当前 flow=4 作为普通模式基准
const FLOW_MODE_DISPLAY = {
    'normal': '普通模式（当前流量）',
    'high': '高流量模式（当前流量 × 1.7）',
};
const FLOW_DISPLAY = { '2': '旧流量等级 1', '4': '旧流量等级 2', '6': '旧流量等级 3' };
function flowMode() {
    var el = document.getElementById('flowLevel');
    var value = el ? String(el.value) : 'normal';
    return value === 'high' ? 'high' : 'normal';
}
function flowLabel(v) {
    var key = String(v);
    return FLOW_MODE_DISPLAY[key] || FLOW_DISPLAY[key] || key;
}

// 算法模板
const PATH_TEMPLATES = {
    dijkstra_tpl: '# Dijkstra 动态最短路径算法\n# 基于实时effort值的动态重路由\n\nimport traci\nimport heapq\nfrom collections import defaultdict\n\nclass DijkstraRouter:\n    """\n    Dijkstra动态路由器\n    基于实时effort值（旅行时间+拥堵+信号延迟）\n    每50秒为CAV车辆重新规划最优路径\n    """\n    def __init__(self, update_interval=50):\n        self.update_interval = update_interval\n        self.edge_weights = {}\n\n    def update_effort(self):\n        """更新全网effort值"""\n        for edge in traci.edge.getIDList():\n            if edge.startswith(\':\'):\n                continue\n            # effort = 自由流时间 + BPR拥堵延迟\n            lanes = traci.edge.getLaneNumber(edge)\n            length = traci.lane.getLength(f"{edge}_0")\n            speed = traci.edge.getLastStepMeanSpeed(edge)\n            if speed < 0.1:\n                speed = 0.1\n            free_flow = length / speed\n            # BPR延迟\n            vehicles = traci.edge.getLastStepVehicleNumber(edge)\n            capacity = lanes * 0.5  # 每秒通行能力\n            ratio = vehicles / capacity if capacity > 0 else 0\n            bpr_delay = free_flow * 0.15 * (ratio ** 4)\n            # 排队惩罚\n            halting = traci.edge.getLastStepHaltingNumber(edge)\n            queue_penalty = halting * 2.0\n            self.edge_weights[edge] = free_flow + bpr_delay + queue_penalty\n            traci.edge.setEffort(edge, self.edge_weights[edge])\n\n    def reroute_cavs(self):\n        """为所有CAV重新规划路径"""\n        count = 0\n        for veh in traci.vehicle.getIDList():\n            if traci.vehicle.getTypeID(veh) == \'CAV\':\n                traci.vehicle.rerouteEffort(veh)\n                count += 1\n        return count\n\n    def update(self, sim_step):\n        """每个决策周期执行"""\n        if sim_step < 600:  # 预热期\n            return\n        if sim_step % self.update_interval != 0:\n            return\n        self.update_effort()\n        changed = self.reroute_cavs()\n        print(f"[{sim_step}s] Rerouted {changed} CAVs")',
    ssp_tpl: '# SSP 逐次最短路径算法\n# 基于实时路网状态的动态路径分配\n\nimport traci\nimport heapq\nfrom collections import defaultdict\n\nclass SSPRouter:\n    """\n    逐次最短路径路由器\n    每个决策周期基于当前effort值\n    为CAV车辆计算最优路径\n    """\n    def __init__(self, flow_level=4, update_interval=60,\n                 output_dir=None):\n        self.flow_level = flow_level\n        self.update_interval = update_interval\n        self.output_dir = output_dir\n        self.edge_weights = {}\n\n    def update_weights(self):\n        """更新全网effort值"""\n        for edge in traci.edge.getIDList():\n            if edge.startswith(\':\'):\n                continue\n            travel_time = traci.edge.getTraveltime(edge)\n            halting = traci.edge.getLastStepHaltingNumber(edge)\n            # effort = 旅行时间 + 排队惩罚\n            self.edge_weights[edge] = travel_time + halting * 2.0\n\n    def find_shortest_path(self, start, end):\n        """Dijkstra求最短路径"""\n        dist = defaultdict(lambda: float(\'inf\'))\n        prev = {}\n        dist[start] = 0\n        pq = [(0, start)]\n        visited = set()\n\n        while pq:\n            d, u = heapq.heappop(pq)\n            if u in visited:\n                continue\n            visited.add(u)\n            if u == end:\n                break\n            # 获取邻接边\n            for lane_link in traci.lane.getLinks(f"{u}_0"):\n                next_edge = lane_link[0].rsplit(\'_\', 1)[0]\n                if next_edge.startswith(\':\'):\n                    continue\n                w = self.edge_weights.get(next_edge, 100)\n                if d + w < dist[next_edge]:\n                    dist[next_edge] = d + w\n                    prev[next_edge] = u\n                    heapq.heappush(pq, (dist[next_edge], next_edge))\n\n        # 回溯路径\n        path = []\n        node = end\n        while node in prev:\n            path.append(node)\n            node = prev[node]\n        path.append(start)\n        path.reverse()\n        return path, dist[end]\n\n    def update(self, sim_step):\n        """每个决策周期执行路径更新"""\n        if sim_step % self.update_interval != 0:\n            return\n        self.update_weights()\n        # 为所有CAV重新规划路径\n        for veh in traci.vehicle.getIDList():\n            if traci.vehicle.getTypeID(veh) == \'CAV\':\n                route = traci.vehicle.getRoute(veh)\n                current = traci.vehicle.getRoadID(veh)\n                dest = route[-1]\n                new_path, cost = self.find_shortest_path(\n                    current, dest\n                )\n                if len(new_path) > 1:\n                    traci.vehicle.setRoute(veh, new_path)',
    astar_tpl: '# A* 启发式搜索路径诱导\n# 基于路段长度的静态最短路径\n\nimport traci\nimport heapq\nimport math\n\nclass AstarRouter:\n    """\n    A*路径诱导路由器\n    使用启发式函数加速搜索\n    仅考虑路段长度（静态最短路径）\n    """\n    def __init__(self, net_file=None):\n        self.coords = {}  # 节点坐标缓存\n        self.net_file = net_file\n\n    def _get_edge_coords(self, edge_id):\n        """获取边的中心坐标"""\n        if edge_id not in self.coords:\n            try:\n                lane = f"{edge_id}_0"\n                shape = traci.lane.getShape(lane)\n                if shape:\n                    mid = len(shape) // 2\n                    self.coords[edge_id] = shape[mid]\n                else:\n                    self.coords[edge_id] = (0, 0)\n            except:\n                self.coords[edge_id] = (0, 0)\n        return self.coords[edge_id]\n\n    def heuristic(self, a, b):\n        """欧几里得距离启发函数"""\n        ax, ay = self._get_edge_coords(a)\n        bx, by = self._get_edge_coords(b)\n        return math.sqrt((ax-bx)**2 + (ay-by)**2)\n\n    def find_path(self, start, end):\n        """A*搜索最短路径"""\n        from collections import defaultdict\n        dist = defaultdict(lambda: float(\'inf\'))\n        prev = {}\n        dist[start] = 0\n        h = self.heuristic(start, end)\n        pq = [(h, 0, start)]\n        visited = set()\n\n        while pq:\n            f, g, u = heapq.heappop(pq)\n            if u in visited:\n                continue\n            visited.add(u)\n            if u == end:\n                break\n            for link in traci.lane.getLinks(f"{u}_0"):\n                next_edge = link[0].rsplit(\'_\', 1)[0]\n                if next_edge.startswith(\':\'):\n                    continue\n                length = traci.lane.getLength(f"{next_edge}_0")\n                new_g = g + length\n                if new_g < dist[next_edge]:\n                    dist[next_edge] = new_g\n                    prev[next_edge] = u\n                    h = self.heuristic(next_edge, end)\n                    heapq.heappush(pq, (new_g + h, new_g, next_edge))\n\n        path = []\n        node = end\n        while node in prev:\n            path.append(node)\n            node = prev[node]\n        path.append(start)\n        path.reverse()\n        return path, dist[end]\n\n    def update(self, sim_step):\n        """每60秒为CAV重新规划路径"""\n        if sim_step % 60 != 0 or sim_step < 600:\n            return\n        for veh in traci.vehicle.getIDList():\n            if traci.vehicle.getTypeID(veh) == \'CAV\':\n                route = traci.vehicle.getRoute(veh)\n                current = traci.vehicle.getRoadID(veh)\n                dest = route[-1]\n                new_path, _ = self.find_path(current, dest)\n                if len(new_path) > 1:\n                    traci.vehicle.setRoute(veh, new_path)',
    greedy_path: '# 贪心路径选择算法\n# 每步选择effort最小的邻居边\n\nimport traci\n\ndef greedy_reroute(veh_id):\n    """\n    贪心路径选择\n    每步选择当前节点effort最小的邻居\n    """\n    current = traci.vehicle.getRoadID(veh_id)\n    route = list(traci.vehicle.getRoute(veh_id))\n    dest = route[-1]\n\n    path = [current]\n    visited = {current}\n    max_steps = 50\n\n    for _ in range(max_steps):\n        if current == dest:\n            break\n        # 获取邻接边\n        neighbors = []\n        try:\n            links = traci.lane.getLinks(f"{current}_0")\n            for link in links:\n                next_edge = link[0].rsplit(\'_\', 1)[0]\n                if not next_edge.startswith(\':\') and next_edge not in visited:\n                    effort = traci.edge.getTraveltime(next_edge)\n                    neighbors.append((next_edge, effort))\n        except:\n            break\n\n        if not neighbors:\n            break\n\n        # 贪心选择effort最小的邻居\n        next_edge, _ = min(neighbors, key=lambda x: x[1])\n        path.append(next_edge)\n        visited.add(next_edge)\n        current = next_edge\n\n    return path\n\n# 在仿真循环中调用:\n# for veh in traci.vehicle.getIDList():\n#     if traci.vehicle.getTypeID(veh) == \'CAV\':\n#         new_path = greedy_reroute(veh)\n#         traci.vehicle.setRoute(veh, new_path)',
    custom: '# 自定义路径诱导算法\n# 请在此编写您的算法\n# 算法将在SUMO仿真环境中运行\n\nimport traci\n\ndef my_route_algorithm(sim_step):\n    """\n    自定义路径诱导函数\n    在仿真主循环中每步调用\n\n    参数:\n        sim_step: 当前仿真时间步\n\n    可用的TraCI接口:\n        traci.edge.getTraveltime(edge)  # 获取旅行时间\n        traci.edge.getLastStepHaltingNumber(edge)  # 排队数\n        traci.vehicle.getRoute(veh)  # 获取路径\n        traci.vehicle.setRoute(veh, route)  # 设置路径\n        traci.vehicle.getTypeID(veh)  # 获取车辆类型\n    """\n    # 每60秒执行一次\n    if sim_step % 60 != 0:\n        return\n\n    # TODO: 在此实现您的路径诱导算法\n    for veh in traci.vehicle.getIDList():\n        if traci.vehicle.getTypeID(veh) == \'CAV\':\n            # 获取当前路径\n            route = traci.vehicle.getRoute(veh)\n            # 计算新路径...\n            pass\n'
};

class PathGuidance {
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
        if (algoSelect) {
            algoSelect.addEventListener('change', function() {
                self.updateAlgorithmDesc();
                self.updateAlgorithmDisplay();
            });
        }

        document.getElementById('startSimulation').addEventListener('click', function() { self.startSimulation(); });
        document.getElementById('resetParams').addEventListener('click', function() { self.resetParams(); });

        var exportBtn = document.getElementById('exportResultsBtn');
        if (exportBtn) exportBtn.addEventListener('click', function() { self.exportResults(); });

        var exportReportBtn = document.getElementById('exportReportBtn');
        if (exportReportBtn) exportReportBtn.addEventListener('click', function() { self.exportReport(); });

        var backBtn = document.getElementById('backBtn');
        if (backBtn) backBtn.addEventListener('click', function() { window.history.back(); });

        // 配置文件按钮
        document.querySelectorAll('.config-file-btn').forEach(function(btn) {
            btn.addEventListener('click', function(e) { self.handleConfigClick(e.currentTarget); });
        });

        // 自主算法设计
        var submitCustomBtn = document.getElementById('submitCustomAlgo');
        if (submitCustomBtn) submitCustomBtn.addEventListener('click', function() { self.submitCustomAlgorithm(); });

        var confirmCodeBtn = document.getElementById('confirmCodeBtn');
        if (confirmCodeBtn) confirmCodeBtn.addEventListener('click', function() { self.confirmCode(); });

        var templateSelect = document.getElementById('templateSelect');
        if (templateSelect) templateSelect.addEventListener('change', function() { self.handleTemplateChange(); self.resetConfirm(); });

        var resetTemplateBtn = document.getElementById('resetTemplateBtn');
        if (resetTemplateBtn) resetTemplateBtn.addEventListener('click', function() { self.handleResetTemplate(); self.resetConfirm(); });

        var expandBtn = document.getElementById('expandCodeBtn');
        if (expandBtn) expandBtn.addEventListener('click', function() { self.toggleCodeExpand(); });

        var overlay = document.getElementById('codeFullscreenOverlay');
        if (overlay) overlay.addEventListener('click', function() { self.toggleCodeExpand(); });
    }

    updateAlgorithmDesc() {
        var algo = document.getElementById('algorithmSelect').value;
        var descEl = document.getElementById('algorithmDesc');
        if (descEl) descEl.innerHTML = '<p>' + (ALGO_DESCRIPTIONS[algo] || '') + '</p>';
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

    handleConfigClick(btn) {
        btn.classList.toggle('step-done');
    }

    // ========== 代码编辑器 ==========
    initCodeEditor() {
        var self = this;
        var editor = document.getElementById('codeEditor');
        if (!editor) return;
        this.codeConfirmed = false;
        this.handleTemplateChange();
        editor.addEventListener('input', function() { self.updateHighlight(); self.resetConfirm(); });
        editor.addEventListener('scroll', function() { self.syncScroll(); });
        editor.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                e.preventDefault();
                var start = editor.selectionStart;
                var end = editor.selectionEnd;
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
        var tpl = PATH_TEMPLATES[sel.value] || PATH_TEMPLATES['custom'];
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
        var escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        escaped = escaped.replace(/("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="py-string">$1</span>');
        escaped = escaped.replace(/(#.*$)/gm, '<span class="py-comment">$1</span>');
        var kw = '\\b(def|class|return|if|elif|else|for|while|import|from|as|try|except|finally|with|yield|lambda|pass|break|continue|raise|in|not|and|or|is|None|True|False|global|nonlocal|assert|del)\\b';
        escaped = escaped.replace(new RegExp(kw, 'g'), '<span class="py-keyword">$1</span>');
        var bi = '\\b(print|len|range|sum|max|min|round|int|float|str|list|dict|tuple|set|type|isinstance|enumerate|zip|map|filter|sorted|abs|open|super|getattr|setattr|hasattr)\\b';
        escaped = escaped.replace(new RegExp(bi, 'g'), '<span class="py-builtin">$1</span>');
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

    // 自主算法设计提交
    async submitCustomAlgorithm() {
        var editor = document.getElementById('codeEditor');
        var code = editor ? editor.value.trim() : '';
        if (!code) { alert('请先编写自定义算法代码'); return; }
        if (!this.codeConfirmed) { alert('请先点击"确认代码"按钮'); return; }
        if (this.isRunning) { alert('仿真正在运行中，请等待完成'); return; }

        // 模板算法直接调用 /run 接口运行真实仿真（带SUMO-GUI）
        var tplSel = document.getElementById('templateSelect');
        var tplVal = tplSel ? tplSel.value : 'custom';
        var TPL_TO_ALGO = { 'dijkstra_tpl': 'dijkstra', 'ssp_tpl': 'ssp', 'astar_tpl': 'astar', 'greedy_path': 'dijkstra' };

        if (TPL_TO_ALGO[tplVal]) {
            document.getElementById('algorithmSelect').value = TPL_TO_ALGO[tplVal];
            this.updateAlgorithmDesc();
            this.updateAlgorithmDisplay();
            this.startSimulation();
            return;
        }

        // 自定义/贪心模板 -> 服务器后台任务执行用户代码
        var statusEl = document.getElementById('customAlgoStatus');
        var submitBtn = document.getElementById('submitCustomAlgo');
        if (statusEl) statusEl.textContent = '正在提交...';
        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '运行中...'; }

        var selectedFlowMode = flowMode();
        var flowLevel = 4;
        var pr = parseInt(document.getElementById('prSelect').value);

        try {
            var resp = await fetch(API_BASE + '/run-custom', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code, flow_level: flowLevel, flow_mode: selectedFlowMode, pr: pr })
            });
            var data = await resp.json();
            if (resp.ok && data.success) {
                if (statusEl) statusEl.textContent = ' ' + data.message;
                this.setStatus('自定义算法运行中（服务器后台任务）...');
                this.isRunning = true;
                this.pollStatus();
            } else {
                if (statusEl) statusEl.textContent = ' ' + (data.message || data.detail || '未知错误');
            }
        } catch (err) {
            if (statusEl) statusEl.textContent = ' 后端服务未响应';
        }

        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = ' 运行自定义算法'; }
    }

    // ========== 核心：启动仿真 ==========
    async startSimulation() {
        if (this.isRunning) return;

        var algo = document.getElementById('algorithmSelect').value;
        var selectedFlowMode = flowMode();
        var flowLevel = 4;
        var pr = parseInt(document.getElementById('prSelect').value);
        var algoName = ALGO_NAMES[algo];

        this.isRunning = true;
        this.setStatus('正在启动 ' + algoName + ' 路径诱导仿真...');

        var btn = document.getElementById('startSimulation');
        btn.textContent = '仿真中...';
        btn.disabled = true;

        this.showSimulationRunning(algoName, selectedFlowMode, pr);

        try {
            var resp = await fetch(API_BASE + '/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ algorithm: algo, flow_level: flowLevel, flow_mode: selectedFlowMode, pr: pr, use_gui: true })
            });
            var data = await resp.json();

            if (resp.ok && data.success) {
                this.setStatus(algoName + ' 仿真中（服务器后台运行中）...');
                this.pollStatus();
            } else {
                var errMsg = data.message || data.detail || ('HTTP ' + resp.status);
                this.setStatus('启动失败: ' + errMsg);
                this.resetButton();
                this.clearRunningStatus();
            }
        } catch (err) {
            this.setStatus('后端服务未响应，请确认服务器已启动');
            this.resetButton();
            this.clearRunningStatus();
        }
    }

    showSimulationRunning(algoName, selectedFlowMode, pr) {
        var summary = document.getElementById('resultSummary');
        if (summary) {
            summary.innerHTML =
                '<div style="text-align:center; padding:30px 20px;">' +
                '<div style="font-size:48px; margin-bottom:12px;">⏳</div>' +
                '<div style="font-size:16px; font-weight:500; color:#2c3e50;">' + algoName + ' 路径诱导仿真运行中</div>' +
                '<div style="font-size:13px; color:#999; margin-top:8px;">流量模式: ' + flowLabel(selectedFlowMode) + ' | 渗透率: ' + pr + '% | 网页会自动刷新运行状态</div>' +
                '<div style="margin-top:15px; color:#2C5AA0; font-size:13px;">SUMO仿真运行中，CAV车辆路径周期性优化...</div>' +
                '</div>';
        }
    }

    clearRunningStatus() {
        var summary = document.getElementById('resultSummary');
        if (summary) {
            summary.innerHTML = '<p style="color:#999; text-align:center; padding:20px;">暂无结果，请先运行仿真</p>';
        }
    }

    // 轮询仿真状态
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
                    clearInterval(self.pollTimer);
                    self.pollTimer = null;

                    if (s.success) {
                        self.setStatus(s.message || '仿真完成');
                        self.updateTimestamp();
                        if (s.results) {
                            self.displayResults(s.results, s.config_name);
                        } else if (s.config_name) {
                            await self.loadAndDisplayResults(s.config_name);
                        }
                    } else {
                        self.setStatus('仿真失败: ' + (s.message || '未知错误'));
                        self.clearRunningStatus();
                    }
                    self.resetButton();
                }
            } catch (e) {
                console.warn('轮询状态失败:', e);
            }
        }, 3000);
    }

    async loadAndDisplayResults(configName) {
        try {
            var resp = await fetch(API_BASE + '/results/' + configName);
            if (resp.ok) {
                var results = await resp.json();
                this.displayResults(results, configName);
            }
        } catch (e) {
            console.warn('加载结果失败:', e);
        }
    }

    displayResults(results, configName) {
        var summary = document.getElementById('resultSummary');
        if (summary) {
            summary.innerHTML =
                '<div style="text-align:left; width:100%; padding:20px;">' +
                '<h4 style="color:#2C5AA0; margin-bottom:15px; font-size:16px;">✅ 仿真结果 - ' + (results.algorithm || '') + '</h4>' +
                '<div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">' +
                    '<div style="background:#f0f7ff; padding:12px; border-radius:6px; border-left:3px solid #2C5AA0;">' +
                        '<div style="font-size:12px; color:#666;">平均延误</div>' +
                        '<div style="font-size:20px; font-weight:bold; color:#2c3e50;">' + (results.average_delay != null ? results.average_delay + 's' : '--') + '</div>' +
                    '</div>' +
                    '<div style="background:#f0fff0; padding:12px; border-radius:6px; border-left:3px solid #27ae60;">' +
                        '<div style="font-size:12px; color:#666;">吞吐量</div>' +
                        '<div style="font-size:20px; font-weight:bold; color:#2c3e50;">' + (results.throughput != null ? results.throughput + ' 辆' : '--') + '</div>' +
                    '</div>' +
                    '<div style="background:#fff8f0; padding:12px; border-radius:6px; border-left:3px solid #f39c12;">' +
                        '<div style="font-size:12px; color:#666;">总行程时间</div>' +
                        '<div style="font-size:20px; font-weight:bold; color:#2c3e50;">' + (results.total_time != null ? results.total_time + 's' : '--') + '</div>' +
                    '</div>' +
                    '<div style="background:#fff0f0; padding:12px; border-radius:6px; border-left:3px solid #e74c3c;">' +
                        '<div style="font-size:12px; color:#666;">总燃油消耗</div>' +
                        '<div style="font-size:20px; font-weight:bold; color:#2c3e50;">' + (results.total_fuel != null ? results.total_fuel + 'L' : '--') + '</div>' +
                    '</div>' +
                '</div>' +
                '<div style="margin-top:12px; font-size:12px; color:#888;">' +
                    '流量模式: ' + flowLabel(results.flow_mode || results.flow_level || '--') + ' | 渗透率: ' + (results.pr || '--') + '% | CAV数: ' + (results.cav_count || '--') + ' | 运行时间: ' + (results.runtime || '--') + 's | 配置: ' + (configName || '--') +
                '</div>' +
                '</div>';
        }

        if (configName) {
            this.loadOutputFiles(configName);
        }
    }

    async loadOutputFiles(configName) {
        try {
            var resp = await fetch(API_BASE + '/output/' + configName);
            if (!resp.ok) return;
            var data = await resp.json();

            var imgFiles = data.files.filter(function(f) {
                return f.name.endsWith('.png') || f.name.endsWith('.jpg') || f.name.endsWith('.jpeg');
            });
            var dataFiles = data.files.filter(function(f) {
                return f.name.endsWith('.xlsx') || f.name.endsWith('.csv') || f.name.endsWith('.json');
            });

            var container = document.getElementById('resultImages');
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

    resetButton() {
        this.isRunning = false;
        var btn = document.getElementById('startSimulation');
        if (btn) { btn.textContent = '开始仿真'; btn.disabled = false; }
    }

    resetParams() {
        if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
        this.isRunning = false;

        document.getElementById('algorithmSelect').value = 'dijkstra';
        document.getElementById('flowLevel').value = 'normal';
        document.getElementById('prSelect').value = '40';
        this.updateAlgorithmDesc();
        this.updateAlgorithmDisplay();

        this.clearRunningStatus();

        var resultImages = document.getElementById('resultImages');
        if (resultImages) {
            resultImages.innerHTML = '<p style="color:#999; text-align:center; padding:40px 20px;">运行仿真后将在此显示输出图表和数据文件</p>';
        }

        document.querySelectorAll('.config-file-btn').forEach(function(b) { b.classList.remove('step-done'); });

        this.setStatus('就绪');
        document.getElementById('updateTime').textContent = '--:--:--';
        this.resetButton();

        fetch(API_BASE + '/reset', { method: 'POST' }).catch(function() {});
    }

    // 导出结果CSV
    async exportResults() {
        var results = null;
        try {
            var resp = await fetch(API_BASE + '/status');
            var s = await resp.json();
            if (s.results) results = s.results;
        } catch (e) {}

        var algo = document.getElementById('algorithmSelect').value;
        var algoName = ALGO_NAMES[algo];
        var selectedFlowMode = flowMode();
        var pr = document.getElementById('prSelect').value;
        var timestamp = new Date().toLocaleString('zh-CN');

        var csv = '\uFEFF';
        csv += '路径诱导仿真结果\n';
        csv += '生成时间,' + timestamp + '\n';
        csv += '算法,' + algoName + '\n';
        csv += '流量模式,' + flowLabel(selectedFlowMode) + '\n';
        csv += 'CAV渗透率,' + pr + '%\n\n';

        if (results) {
            csv += '指标名称,数值\n';
            csv += '平均延误(s),' + (results.average_delay || '--') + '\n';
            csv += '总行程时间(s),' + (results.total_time || '--') + '\n';
            csv += '总燃油消耗(L),' + (results.total_fuel || '--') + '\n';
            csv += '吞吐量(辆),' + (results.throughput || '--') + '\n';
            csv += '车辆总数,' + (results.vehicle_count || '--') + '\n';
            csv += 'CAV数量,' + (results.cav_count || '--') + '\n';
            csv += '运行时间(s),' + (results.runtime || '--') + '\n';
        } else {
            csv += '（暂无仿真结果，请先运行仿真）\n';
        }

        var blob = new Blob([csv], { type: 'text/csv;charset=utf-8-sig' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = '路径诱导结果_' + algoName + '_' + selectedFlowMode + '_pr' + pr + '_' + Date.now() + '.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // 导出实验报告
    exportReport() {
        var algo = document.getElementById('algorithmSelect').value;
        var algoName = ALGO_NAMES[algo];
        var selectedFlowMode = flowMode();
        var pr = document.getElementById('prSelect').value;
        var currentTime = new Date().toLocaleString('zh-CN');

        var html = '<!DOCTYPE html>' +
'<html lang="zh-CN"><head><meta charset="UTF-8"><title>路径诱导实验报告</title>' +
'<style>' +
'body{font-family:"Microsoft YaHei",Arial,sans-serif;line-height:1.8;margin:40px;}' +
'h1{text-align:center;color:#2C5AA0;}' +
'h2{color:#2C5AA0;border-bottom:2px solid #2C5AA0;padding-bottom:5px;margin-top:30px;}' +
'table{width:100%;border-collapse:collapse;margin:15px 0;}' +
'th,td{border:1px solid #ddd;padding:10px;text-align:left;}' +
'th{background:#2C5AA0;color:white;}' +
'.info-box{background:#E8F4F8;padding:15px;border-left:4px solid #2C5AA0;margin:15px 0;}' +
'</style></head><body>' +
'<h1>路径诱导实验报告</h1>' +
'<p style="text-align:center;color:#666;">实验时间：' + currentTime + '</p>' +
'<h2>一、实验配置</h2>' +
'<table><tr><th>配置项</th><th>值</th></tr>' +
'<tr><td>路径算法</td><td>' + algoName + '</td></tr>' +
'<tr><td>流量模式</td><td>' + flowLabel(selectedFlowMode) + '</td></tr>' +
'<tr><td>CAV渗透率</td><td>' + pr + '%</td></tr>' +
'<tr><td>仿真平台</td><td>SUMO + TraCI</td></tr>' +
'<tr><td>路网</td><td>SiouxFalls</td></tr></table>' +
'<h2>二、算法说明</h2>' +
'<div class="info-box">' + (ALGO_DESCRIPTIONS[algo] || '') + '</div>' +
'<h2>三、实验结果</h2>' +
'<p>（请在仿真完成后填写实际结果数据）</p>' +
'<h2>四、实验心得</h2>' +
'<p style="min-height:100px;border:1px dashed #ccc;padding:10px;"></p>' +
'<div style="margin-top:50px;text-align:right;">' +
'<p>实验人员：___________　学号：___________</p>' +
'<p>指导教师：___________　日期：' + currentTime.split(' ')[0] + '</p>' +
'</div></body></html>';

        var blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = '路径诱导实验报告_' + algoName + '_' + Date.now() + '.doc';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    new PathGuidance();
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
