/**
 * 智信优控 — 底部状态栏组件
 *
 * 自包含模块：注入 HTML + CSS + 轮询逻辑。
 * 在页面底部显示：后端健康状态、仿真器安装/运行状态、通信状态。
 *
 * 用法：在 HTML 底部加 <script src="/src/components/status-bar.js"></script>
 */
(function () {
  'use strict';

  // ---- 配置 ----
  var POLL_INTERVAL = 5000; // ms
  var HEALTH_URL = '/api/v1/health';
  var SIMULATORS_URL = '/api/v1/simulators/status';

  // ---- 颜色常量 ----
  var COLOR_OK = '#67c23a';
  var COLOR_IDLE = '#909399';
  var COLOR_ERR = '#f56c6c';
  var COLOR_WARN = '#e6a23c';

  // ---- 注入 CSS ----
  var css = [
    '.zxk-status-bar{',
    '  position:fixed;bottom:0;left:0;right:0;height:36px;z-index:9999;',
    '  background:linear-gradient(135deg,#1e3d72 0%,#2C5AA0 100%);',
    '  color:#fff;font-size:12px;font-family:"Microsoft YaHei",Arial,sans-serif;',
    '  display:flex;align-items:center;padding:0 16px;gap:18px;',
    '  box-shadow:0 -1px 6px rgba(0,0,0,0.15);',
    '}',
    '.zxk-sb-item{display:flex;align-items:center;gap:4px;white-space:nowrap;}',
    '.zxk-sb-dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0;}',
    '.zxk-sb-sep{width:1px;height:18px;background:rgba(255,255,255,0.25);flex-shrink:0;}',
    '.zxk-sb-label{opacity:0.85;}',
    '.zxk-sb-val{font-weight:600;}',
  ].join('\n');

  var style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  // ---- 注入 HTML ----
  var bar = document.createElement('div');
  bar.className = 'zxk-status-bar';
  bar.innerHTML = [
    '<span class="zxk-sb-item"><span class="zxk-sb-label">后端</span><span class="zxk-sb-dot" id="zxk-sb-backend"></span><span class="zxk-sb-val" id="zxk-sb-backend-text">检测中</span></span>',
    '<span class="zxk-sb-sep"></span>',
    '<span class="zxk-sb-item"><span class="zxk-sb-label">SUMO</span><span class="zxk-sb-dot" id="zxk-sb-sumo"></span><span class="zxk-sb-val" id="zxk-sb-sumo-text">--</span></span>',
    '<span class="zxk-sb-item"><span class="zxk-sb-label">DTALite</span><span class="zxk-sb-dot" id="zxk-sb-dtalite"></span><span class="zxk-sb-val" id="zxk-sb-dtalite-text">--</span></span>',
    '<span class="zxk-sb-item"><span class="zxk-sb-label">CARLA</span><span class="zxk-sb-dot" id="zxk-sb-carla"></span><span class="zxk-sb-val" id="zxk-sb-carla-text">--</span></span>',
    '<span class="zxk-sb-sep"></span>',
    '<span class="zxk-sb-item"><span class="zxk-sb-label">通信</span><span class="zxk-sb-dot" id="zxk-sb-comm"></span><span class="zxk-sb-val" id="zxk-sb-comm-text">检测中</span></span>',
    '<span class="zxk-sb-sep"></span>',
    '<span class="zxk-sb-item"><span class="zxk-sb-label">模式</span><span class="zxk-sb-val" id="zxk-sb-mode">--</span></span>',
  ].join('');
  document.body.appendChild(bar);

  // 页面底部留空，避免遮挡
  document.body.style.paddingBottom = '40px';

  // ---- 辅助函数 ----
  function setDot(id, color) {
    var el = document.getElementById(id);
    if (el) el.style.background = color;
  }
  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  // ---- 轮询后端健康 ----
  var commOk = false;

  function pollHealth() {
    fetch(HEALTH_URL, { method: 'GET' })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (data && data.status === 'healthy') {
          setDot('zxk-sb-backend', COLOR_OK);
          setText('zxk-sb-backend-text', '正常');
          commOk = true;
        } else {
          setDot('zxk-sb-backend', COLOR_WARN);
          setText('zxk-sb-backend-text', '异常');
          commOk = false;
        }
        if (data && data.run_mode_label) {
          setText('zxk-sb-mode', data.run_mode_label);
        }
      })
      .catch(function () {
        setDot('zxk-sb-backend', COLOR_ERR);
        setText('zxk-sb-backend-text', '离线');
        commOk = false;
      })
      .finally(function () {
        setDot('zxk-sb-comm', commOk ? COLOR_OK : COLOR_ERR);
        setText('zxk-sb-comm-text', commOk ? '已连接' : '断开');
      });
  }

  // ---- 轮询仿真器状态 ----
  function simStatusText(sim) {
    if (!sim.installed) return '未安装';
    if (sim.running) return '运行中';
    return '已安装';
  }
  function simStatusColor(sim) {
    if (!sim.installed) return COLOR_IDLE;
    if (sim.running) return COLOR_OK;
    return COLOR_WARN;
  }

  function pollSimulators() {
    fetch(SIMULATORS_URL, { method: 'GET' })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data || !data.simulators) return;
        data.simulators.forEach(function (sim) {
          var key = sim.name.toLowerCase();
          var dotId = 'zxk-sb-' + key;
          var textId = 'zxk-sb-' + key + '-text';
          setDot(dotId, simStatusColor(sim));
          setText(textId, simStatusText(sim));
        });
      })
      .catch(function () {
        // 后端不可达时保持上次状态
      });
  }

  // ---- 启动轮询 ----
  pollHealth();
  pollSimulators();
  setInterval(pollHealth, POLL_INTERVAL);
  setInterval(pollSimulators, POLL_INTERVAL);
})();
