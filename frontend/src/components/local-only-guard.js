/**
 * 本机专属功能守卫（local-only-guard）
 *
 * 用于「必须由运行平台的本机浏览器操作」的实验页（交通信号优化 / 路径诱导 /
 * 车速控制 / 三层级协同优化控制）。局域网访问时：
 *   1. 顶部显示提示横幅；
 *   2. 禁用并持续锁定指定的「运行类」按钮；
 *   3. 保留查看、导出、返回等纯本地功能可用。
 *
 * 之所以要「持续锁定」：这些页面自身的 resetButton() / confirmCode() 会把
 * 按钮重新置为可点击，只禁用一次会被立刻解锁。
 *
 * 真正的权限由后端 access_mode 强制（命中本机专属接口返回 403 LOCAL_ONLY），
 * 这里只是体验层的前置防线。
 *
 * 使用方式——在页面里先声明要锁定的按钮，再引入本脚本：
 *   <script>window.ZXK_LOCAL_ONLY = { buttons: ['startSimulation'] };</script>
 *   <script src="/src/components/local-only-guard.js"></script>
 */
(function () {
    'use strict';

    var config = window.ZXK_LOCAL_ONLY || {};
    var buttonIds = Array.isArray(config.buttons) ? config.buttons : [];
    var BANNER_ID = 'zxkLocalOnlyBanner';
    var LOCK_MESSAGE = config.message
        || '局域网访问：该实验需要启动教师机的仿真进程，仅限在运行平台的本机操作。页面可查看，运行类按钮已禁用。';

    var locked = false;
    var handled = {};

    function buildBanner() {
        var banner = document.createElement('div');
        banner.id = BANNER_ID;
        banner.setAttribute('role', 'alert');
        banner.style.cssText = [
            'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:2147483646',
            'box-sizing:border-box', 'padding:10px 16px',
            'background:#2C5AA0', 'color:#ffffff',
            'font:500 14px/1.5 "Microsoft YaHei",Arial,sans-serif',
            'text-align:center', 'box-shadow:0 2px 10px rgba(18,38,72,0.28)'
        ].join(';');
        banner.textContent = LOCK_MESSAGE;
        return banner;
    }

    function hardDisable(button) {
        var enforce = function () {
            if (!button.disabled) {
                button.disabled = true;
            }
            button.title = LOCK_MESSAGE;
        };
        enforce();
        try {
            // 页面代码把 disabled 改回 false 时立刻恢复禁用，避免前端防线被解锁
            new MutationObserver(enforce).observe(button, {
                attributes: true,
                attributeFilter: ['disabled']
            });
        } catch (error) {
            setInterval(enforce, 800);
        }
    }

    function lockButton(id) {
        if (handled[id]) return;
        var button = document.getElementById(id);
        if (!button) return;
        handled[id] = true;
        hardDisable(button);
    }

    function applyLock() {
        if (locked) return;
        locked = true;

        if (document.body && !document.getElementById(BANNER_ID)) {
            var banner = buildBanner();
            document.body.appendChild(banner);
            document.body.style.paddingTop = (banner.offsetHeight || 44) + 6 + 'px';
        }

        buttonIds.forEach(lockButton);

        // 部分按钮在页面初始化后才渲染，做一次短时补扫
        var tries = 0;
        var timer = setInterval(function () {
            buttonIds.forEach(lockButton);
            tries += 1;
            if (tries >= 10) clearInterval(timer);
        }, 500);
    }

    function init() {
        fetch('/api/v1/access-context', { cache: 'no-store' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (context) {
                if (context && context.can_control_local_services !== true) {
                    applyLock();
                }
            })
            .catch(function (error) {
                // 无法确认访问模式时不锁定，避免影响本机使用；后端仍会返回 403。
                console.warn('[local-only-guard] 访问模式检测失败，保持页面可用:', error);
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
