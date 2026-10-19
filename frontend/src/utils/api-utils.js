/**
 * 统一 API 调用工具与通知组件
 * 所有页面可通过 <script src="/src/utils/api-utils.js"></script> 引入
 */

/* ========== 通知 Toast ========== */
(function () {
    // 注入一次性 CSS
    if (!document.getElementById('zxk-toast-style')) {
        var style = document.createElement('style');
        style.id = 'zxk-toast-style';
        style.textContent = [
            '.zxk-toast{position:fixed;top:24px;right:24px;min-width:260px;max-width:420px;padding:14px 22px;border-radius:10px;',
            'color:#fff;font-size:14px;line-height:1.5;z-index:99999;box-shadow:0 6px 20px rgba(0,0,0,.18);',
            'display:flex;align-items:center;gap:10px;opacity:0;transform:translateY(-12px);',
            'transition:opacity .3s,transform .3s}',
            '.zxk-toast.show{opacity:1;transform:translateY(0)}',
            '.zxk-toast-success{background:#2C5AA0}',
            '.zxk-toast-error{background:#dc3545}',
            '.zxk-toast-warning{background:#e6a817}',
            '.zxk-toast-info{background:#17a2b8}',
            '.zxk-toast .zxk-toast-icon{font-size:18px;flex-shrink:0}',
            '.zxk-toast .zxk-toast-msg{flex:1}',
            /* 同步指示器 */
            '.zxk-sync-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:20px;',
            'font-size:12px;background:#f0f4f8;color:#5a7faa;border:1px solid #d0d8e4;margin-left:8px;vertical-align:middle}',
            '.zxk-sync-badge.syncing{color:#2C5AA0;background:#e8eef6}',
            '.zxk-sync-badge.synced{color:#28a745;background:#e8f5e9}',
            '.zxk-sync-badge.error{color:#dc3545;background:#fde8ea}',
            '@keyframes zxk-spin{to{transform:rotate(360deg)}}',
            '.zxk-sync-spinner{display:inline-block;width:12px;height:12px;border:2px solid #2C5AA0;',
            'border-top-color:transparent;border-radius:50%;animation:zxk-spin .8s linear infinite}',
        ].join('\n');
        document.head.appendChild(style);
    }

    var ICONS = { success: '\u2705', error: '\u274C', warning: '\u26A0\uFE0F', info: '\u2139\uFE0F' };

    /**
     * 显示全局 toast 通知
     * @param {string} message
     * @param {'success'|'error'|'warning'|'info'} type
     * @param {number} duration  毫秒, 默认 3000
     */
    window.zxkToast = function (message, type, duration) {
        type = type || 'info';
        duration = duration || 3000;
        var old = document.querySelector('.zxk-toast');
        if (old) old.remove();

        var el = document.createElement('div');
        el.className = 'zxk-toast zxk-toast-' + type;
        el.innerHTML = '<span class="zxk-toast-icon">' + (ICONS[type] || '') + '</span>'
            + '<span class="zxk-toast-msg">' + message + '</span>';
        document.body.appendChild(el);
        // trigger reflow then show
        void el.offsetWidth;
        el.classList.add('show');
        setTimeout(function () {
            el.classList.remove('show');
            setTimeout(function () { el.remove(); }, 300);
        }, duration);
    };

    /* ========== 统一 fetch 封装 ========== */

    /**
     * 调用后端 API 并统一处理错误
     * @param {string} url        完整 URL 或相对路径 (会拼接 API_BASE)
     * @param {object} [options]  fetch options
     * @returns {Promise<any>}    parsed JSON body
     * @throws  带 .code / .message 的 Error
     */
    window.zxkFetch = async function (url, options) {
        options = options || {};

        // 自动注入 Authorization
        var token = localStorage.getItem('token') || sessionStorage.getItem('token');
        if (token) {
            options.headers = options.headers || {};
            if (!options.headers['Authorization'] && !options.headers['authorization']) {
                options.headers['Authorization'] = 'Bearer ' + token;
            }
        }

        var resp;
        try {
            resp = await fetch(url, options);
        } catch (networkErr) {
            zxkToast('网络连接失败，请检查网络后重试', 'error');
            var ne = new Error('网络连接失败');
            ne.code = 'NETWORK_ERROR';
            throw ne;
        }

        if (resp.ok) {
            var ct = resp.headers.get('content-type') || '';
            if (ct.indexOf('application/json') !== -1) {
                return resp.json();
            }
            return resp;
        }

        // 错误处理 — 兼容新旧两种格式
        var body = null;
        try { body = await resp.json(); } catch (e) { /* ignore */ }

        var errMsg = '请求失败 (' + resp.status + ')';
        var errCode = 'HTTP_' + resp.status;

        if (body) {
            // 新格式: { success: false, error: { code, message } }
            if (body.error && body.error.message) {
                errMsg = body.error.message;
                errCode = body.error.code || errCode;
            }
            // 旧格式: { detail: { code, message } } 或 { detail: "string" }
            else if (body.detail) {
                if (typeof body.detail === 'string') {
                    errMsg = body.detail;
                } else if (body.detail.message) {
                    errMsg = body.detail.message;
                    errCode = body.detail.code || errCode;
                }
            }
        }

        // 401 自动跳转登录
        if (resp.status === 401) {
            zxkToast('登录已过期，请重新登录', 'warning');
            setTimeout(function () {
                window.location.href = '/src/pages/登录界面/login.html';
            }, 1500);
        } else {
            zxkToast(errMsg, 'error');
        }

        var err = new Error(errMsg);
        err.code = errCode;
        err.status = resp.status;
        throw err;
    };

    /* ========== 同步状态徽章 ========== */

    /**
     * 创建或更新同步状态徽章
     * @param {string}  containerId  宿主元素 id
     * @param {'syncing'|'synced'|'error'|'idle'} state
     * @param {string}  [text]
     */
    window.zxkSyncBadge = function (containerId, state, text) {
        var container = document.getElementById(containerId);
        if (!container) return;
        var badge = container.querySelector('.zxk-sync-badge');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'zxk-sync-badge';
            container.appendChild(badge);
        }
        badge.className = 'zxk-sync-badge ' + (state || 'idle');
        if (state === 'syncing') {
            badge.innerHTML = '<span class="zxk-sync-spinner"></span>' + (text || '同步中...');
        } else if (state === 'synced') {
            badge.innerHTML = '\u2705 ' + (text || '已同步');
        } else if (state === 'error') {
            badge.innerHTML = '\u274C ' + (text || '同步失败');
        } else {
            badge.innerHTML = text || '';
        }
    };
})();
