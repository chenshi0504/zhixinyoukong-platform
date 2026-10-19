/**
 * 局域网访问守卫（lan-guard）
 *
 * 本机（local）访问不做任何改动；局域网（lan）访问时：
 *   1. 在页面顶部显示"仅限本机"提示横幅；
 *   2. 禁用页面内全部交互控件；
 *   3. 在捕获阶段拦截点击与表单提交，保证动态生成的控件同样无法使用。
 *
 * 主要用于"虚实融合"相关实验页（CARLA / VIC-Sim / 车规级小车 / SUMO 算法测试），
 * 避免学生在自己的电脑上误触发教师机的仿真与小车控制。
 * 后端 access_mode 仍会对本机专属接口返回 403，这里是第二道防线。
 */
(function () {
    'use strict';

    var BANNER_ID = 'zxkLanGuardBanner';
    var BANNER_TEXT = '局域网访问：该实验仅限运行平台的本机操作。页面可查看，但所有功能不可用。';
    var INTERACTIVE_SELECTOR = 'button, input, select, textarea, [contenteditable="true"], [role="button"], [onclick]';

    var locked = false;

    function buildBanner() {
        var banner = document.createElement('div');
        banner.id = BANNER_ID;
        banner.setAttribute('role', 'alert');
        banner.style.cssText = [
            'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:2147483647',
            'box-sizing:border-box', 'padding:10px 16px',
            'background:#2C5AA0', 'color:#ffffff',
            'font:500 14px/1.5 "Microsoft YaHei",Arial,sans-serif',
            'text-align:center', 'box-shadow:0 2px 10px rgba(18,38,72,0.28)'
        ].join(';');
        banner.textContent = BANNER_TEXT;
        return banner;
    }

    function disableControls() {
        var nodes = document.querySelectorAll(INTERACTIVE_SELECTOR);
        for (var i = 0; i < nodes.length; i += 1) {
            var el = nodes[i];
            if (el.id === BANNER_ID) continue;
            try {
                el.disabled = true;
            } catch (error) {
                // 非表单元素赋值 disabled 无效，忽略
            }
            el.setAttribute('aria-disabled', 'true');
            el.style.pointerEvents = 'none';
            el.style.cursor = 'not-allowed';
        }
    }

    function isBannerTarget(target) {
        if (!target || target.nodeType !== 1) return false;
        if (target.id === BANNER_ID) return true;
        if (typeof target.closest === 'function' && target.closest('#' + BANNER_ID)) return true;
        return false;
    }

    function blockEvent(event) {
        if (!locked) return;
        if (isBannerTarget(event.target)) return;
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) {
            event.stopImmediatePropagation();
        }
    }

    function blockKeydown(event) {
        if (!locked) return;
        // 只拦截回车与空格这类会触发"激活"的按键，其余按键（滚动、刷新、调试）放行。
        if (event.key === 'Enter' || event.key === ' ') {
            blockEvent(event);
        }
    }

    function lockPage() {
        if (locked) return;
        locked = true;

        if (document.body) {
            var banner = buildBanner();
            document.body.appendChild(banner);
            var bannerHeight = banner.offsetHeight || 44;
            document.body.style.paddingTop = bannerHeight + 6 + 'px';
        }

        disableControls();
        document.addEventListener('click', blockEvent, true);
        document.addEventListener('submit', blockEvent, true);
        document.addEventListener('keydown', blockKeydown, true);
    }

    function init() {
        fetch('/api/v1/access-context', { cache: 'no-store' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (context) {
                if (context && context.access_mode === 'lan') {
                    lockPage();
                }
            })
            .catch(function (error) {
                // 无法确认访问模式时不锁定页面，避免影响本机使用；
                // 后端仍会对本机专属接口返回 403。
                console.warn('[lan-guard] 访问模式检测失败，保持页面可用:', error);
            });
    }

    // 供页面在运行的进程被判定为本机时手动解锁，或特殊场景复用。
    window.zxkLanGuardLock = lockPage;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
