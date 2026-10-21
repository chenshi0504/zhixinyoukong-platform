(function () {
  'use strict';

  if (window.ZXKInteractionFeedback) return;

  var busyKeys = {};
  var originalFetch = window.fetch;

  function ensureStyles() {
    if (document.getElementById('zxk-interaction-feedback-style')) return;
    var style = document.createElement('style');
    style.id = 'zxk-interaction-feedback-style';
    style.textContent = [
      '.zxk-feedback-toast{position:fixed;top:78px;right:22px;z-index:12000;max-width:360px;',
      'padding:10px 14px;border-radius:8px;color:#fff;font-size:14px;line-height:1.5;',
      'box-shadow:0 10px 28px rgba(0,0,0,.18);opacity:0;transform:translateY(-8px);',
      'transition:opacity .2s ease,transform .2s ease;font-family:"Microsoft YaHei",Arial,sans-serif;}',
      '.zxk-feedback-toast.show{opacity:1;transform:translateY(0);}',
      '.zxk-feedback-toast.info{background:#409eff;}',
      '.zxk-feedback-toast.success{background:#67c23a;}',
      '.zxk-feedback-toast.warning{background:#e6a23c;}',
      '.zxk-feedback-toast.error{background:#f56c6c;}',
      'button.zxk-busy,.btn.zxk-busy{opacity:.72;cursor:wait!important;}',
      'button.zxk-busy *,.btn.zxk-busy *{pointer-events:none;}'
    ].join('');
    document.head.appendChild(style);
  }

  function notify(message, type, timeout) {
    ensureStyles();
    var old = document.querySelector('.zxk-feedback-toast');
    if (old && old.parentNode) old.parentNode.removeChild(old);
    var toast = document.createElement('div');
    toast.className = 'zxk-feedback-toast ' + (type || 'info');
    toast.textContent = message || '操作已触发';
    document.body.appendChild(toast);
    requestAnimationFrame(function () { toast.classList.add('show'); });
    setTimeout(function () {
      toast.classList.remove('show');
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 220);
    }, timeout || 1800);
  }

  function setBusy(button, busy, text) {
    if (!button) return;
    if (busy) {
      if (!button.dataset.zxkOriginalText) button.dataset.zxkOriginalText = button.textContent.trim();
      button.disabled = true;
      button.classList.add('zxk-busy');
      if (text) button.textContent = text;
    } else {
      button.disabled = false;
      button.classList.remove('zxk-busy');
      if (button.dataset.zxkOriginalText) button.textContent = button.dataset.zxkOriginalText;
    }
  }

  function actionFromText(text) {
    var clean = (text || '').replace(/\s+/g, ' ').replace(/[↻🔄📊▶✅☁️📤📄]/g, '').trim();
    if (!clean) return null;
    if (/刷新|加载|查询|查看/.test(clean)) return { pending: '正在' + clean + '...', success: clean + '完成' };
    if (/保存/.test(clean)) return { pending: '正在保存...', success: '保存成功' };
    if (/提交/.test(clean)) return { pending: '正在提交...', success: '提交成功' };
    if (/上传/.test(clean)) return { pending: '正在上传...', success: '上传成功' };
    if (/下载/.test(clean)) return { pending: '正在准备下载...', success: '下载已开始' };
    if (/导出/.test(clean)) return { pending: '正在导出...', success: '导出完成' };
    if (/运行|仿真|启动/.test(clean)) return { pending: '正在运行，请勿重复操作', success: '任务已启动' };
    if (/停止/.test(clean)) return { pending: '正在停止...', success: '已停止' };
    if (/删除/.test(clean)) return { pending: '正在删除...', success: '删除成功' };
    if (/发送|下发/.test(clean)) return { pending: '正在发送...', success: '发送成功' };
    return null;
  }

  function getActionKey(el, text) {
    return el.id || el.getAttribute('href') || el.getAttribute('onclick') || text;
  }

  function markActionStarted(el, action) {
    var text = (el.textContent || '').replace(/\s+/g, ' ').trim();
    var key = getActionKey(el, text);
    var now = Date.now();
    if (busyKeys[key] && now - busyKeys[key] < 1200) {
      notify('操作正在处理中，请勿重复点击', 'warning', 1600);
      return false;
    }
    busyKeys[key] = now;
    if (/运行|仿真|启动|上传|提交|保存|删除/.test(text)) {
      setBusy(el, true, action.pending);
      setTimeout(function () {
        setBusy(el, false);
        delete busyKeys[key];
      }, 1800);
    } else {
      setTimeout(function () { delete busyKeys[key]; }, 1200);
    }
    notify(action.pending, 'info', 1300);
    return true;
  }

  function isMutationRequest(input, init) {
    var method = (init && init.method) || (input && input.method) || 'GET';
    return !/^(GET|HEAD|OPTIONS)$/i.test(method);
  }

  function requestUrl(input) {
    if (typeof input === 'string') return input;
    if (input && input.url) return input.url;
    return '';
  }

  function shouldReportRequest(url) {
    return /\/api\//.test(url) && !/\/health|\/status|\/simulators\/status/.test(url);
  }

  function bindFetchFeedback() {
    if (!originalFetch || originalFetch.__zxkFeedbackWrapped) return;
    var wrapped = function (input, init) {
      var url = requestUrl(input);
      var report = shouldReportRequest(url) && isMutationRequest(input, init);
      return originalFetch.apply(window, arguments).then(function (response) {
        if (report) {
          notify(response.ok ? '服务器已处理本次操作' : '服务器处理失败：' + response.status, response.ok ? 'success' : 'error', 1800);
        }
        return response;
      }).catch(function (error) {
        if (report) notify('请求失败：' + (error && error.message ? error.message : '网络或服务器不可用'), 'error', 2200);
        throw error;
      });
    };
    wrapped.__zxkFeedbackWrapped = true;
    window.fetch = wrapped;
  }

  function bindDefaultButtonFeedback() {
    document.addEventListener('click', function (event) {
      var el = event.target.closest('button,.btn,[role="button"]');
      if (!el || el.disabled || el.dataset.feedbackBound === 'manual') return;
      var text = (el.textContent || '').replace(/\s+/g, ' ').trim();
      if (!text) return;
      var action = actionFromText(text);
      if (!action) return;
      if (!markActionStarted(el, action)) {
        event.preventDefault();
        event.stopPropagation();
      }
    }, true);
  }

  window.ZXKInteractionFeedback = {
    notify: notify,
    setBusy: setBusy,
    actionFromText: actionFromText,
  };

  bindFetchFeedback();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindDefaultButtonFeedback);
  } else {
    bindDefaultButtonFeedback();
  }
})();
