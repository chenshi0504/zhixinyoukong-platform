/**
 * 聊天框 & 日志增强组件 - 全局共享脚本
 * 在各功能页面中引入即可自动注入底部聊天框和日志增强功能。
 *
 * 用法：在 HTML 末尾加入
 *   <link rel="stylesheet" href="../../components/chat-log-widget.css">
 *   <script src="../../components/chat-log-widget.js"></script>
 */

(function () {
    'use strict';

    // ========== 工具函数 ==========

    /** 获取当前时间字符串 HH:MM */
    function timeStr() {
        var d = new Date();
        return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    }

    /** 通用确认弹窗（返回 Promise<boolean>） */
    function showConfirm(msg, icon) {
        return new Promise(function (resolve) {
            var overlay = document.createElement('div');
            overlay.className = 'confirm-overlay';
            overlay.innerHTML =
                '<div class="confirm-dialog">' +
                    '<div class="confirm-dialog-icon">' + (icon || '⚠️') + '</div>' +
                    '<div class="confirm-dialog-msg">' + msg + '</div>' +
                    '<div class="confirm-dialog-btns">' +
                        '<button class="confirm-btn-cancel">取消</button>' +
                        '<button class="confirm-btn-ok">确定</button>' +
                    '</div>' +
                '</div>';
            document.body.appendChild(overlay);

            function close(result) {
                overlay.style.animation = 'confirmFadeIn 0.15s ease reverse';
                setTimeout(function () {
                    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                }, 150);
                resolve(result);
            }

            overlay.querySelector('.confirm-btn-ok').addEventListener('click', function () { close(true); });
            overlay.querySelector('.confirm-btn-cancel').addEventListener('click', function () { close(false); });
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) close(false);
            });
        });
    }

    // ========== 日志区域增强 ==========

    function enhanceLogSections() {
        // 找到所有 .log-section 中的清空按钮，替换为带确认的版本
        var clearBtns = document.querySelectorAll('#clearLogBtn, .btn-clear-log');
        clearBtns.forEach(function (btn) {
            var newBtn = btn.cloneNode(true);
            btn.parentNode.replaceChild(newBtn, btn);
            newBtn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                showConfirm('确定要清空所有日志吗？', '🗑️').then(function (ok) {
                    if (!ok) return;
                    var container = document.getElementById('logContainer');
                    if (container) {
                        container.innerHTML = '<div class="log-empty">等待操作...</div>';
                    }
                });
            });
        });
    }

    // ========== 底部聊天框 ==========

    var chatMessages = []; // { role: 'system'|'user'|'bot', text: string, time: string }

    function createChatWidget() {
        var widget = document.createElement('div');
        widget.className = 'chat-widget';
        widget.id = 'chatWidget';
        widget.innerHTML =
            '<div class="chat-header" id="chatHeader">' +
                '<span class="chat-header-title">💬 实验助手</span>' +
                '<div class="chat-header-actions">' +
                    '<button class="chat-header-btn" id="chatClearBtn" title="清空聊天">🗑️</button>' +
                    '<button class="chat-header-btn" id="chatToggleBtn" title="收起/展开">▼</button>' +
                '</div>' +
            '</div>' +
            '<div class="chat-messages" id="chatMessages">' +
                '<div class="chat-empty">暂无消息，输入内容开始对话</div>' +
            '</div>' +
            '<div class="chat-input-area">' +
                '<input class="chat-input" id="chatInput" type="text" placeholder="输入消息..." maxlength="500" autocomplete="off">' +
                '<button class="chat-send-btn" id="chatSendBtn" title="发送">➤</button>' +
            '</div>';
        document.body.appendChild(widget);

        // 绑定事件
        var header = document.getElementById('chatHeader');
        var toggleBtn = document.getElementById('chatToggleBtn');
        var clearBtn = document.getElementById('chatClearBtn');
        var input = document.getElementById('chatInput');
        var sendBtn = document.getElementById('chatSendBtn');
        var msgArea = document.getElementById('chatMessages');

        // 展开/收起
        function toggleChat(e) {
            // 不要在点击按钮时触发
            if (e && (e.target.id === 'chatClearBtn' || e.target.closest('#chatClearBtn'))) return;
            widget.classList.toggle('chat-collapsed');
            toggleBtn.textContent = widget.classList.contains('chat-collapsed') ? '▲' : '▼';
        }
        header.addEventListener('click', toggleChat);

        // 清空聊天
        clearBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            showConfirm('确定要清空所有聊天记录吗？', '🗑️').then(function (ok) {
                if (!ok) return;
                chatMessages = [];
                renderMessages();
            });
        });

        // 发送消息
        function sendMessage() {
            var text = input.value.trim();
            if (!text) return;
            addMessage('user', text);
            input.value = '';
            // 模拟自动回复
            setTimeout(function () {
                var reply = getAutoReply(text);
                addMessage('bot', reply);
            }, 400 + Math.random() * 400);
        }
        sendBtn.addEventListener('click', sendMessage);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // 初始系统消息
        addMessage('system', '欢迎使用实验助手，有问题可以随时提问。');
    }

    function addMessage(role, text) {
        chatMessages.push({ role: role, text: text, time: timeStr() });
        renderMessages();
    }

    function renderMessages() {
        var area = document.getElementById('chatMessages');
        if (!area) return;
        if (chatMessages.length === 0) {
            area.innerHTML = '<div class="chat-empty">暂无消息，输入内容开始对话</div>';
            return;
        }
        var html = '';
        chatMessages.forEach(function (m) {
            var cls = 'chat-msg msg-' + m.role;
            html += '<div class="' + cls + '">' +
                '<div class="chat-msg-bubble">' + escapeHtml(m.text) + '</div>' +
                '<div class="chat-msg-time">' + m.time + '</div>' +
            '</div>';
        });
        area.innerHTML = html;
        // 滚动到底部
        area.scrollTop = area.scrollHeight;
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /** 简单的自动回复（本地，无需后端） */
    function getAutoReply(text) {
        var t = text.toLowerCase();
        if (t.indexOf('你好') !== -1 || t.indexOf('hello') !== -1 || t.indexOf('hi') !== -1) {
            return '你好！我是实验助手，有什么可以帮你的吗？';
        }
        if (t.indexOf('帮助') !== -1 || t.indexOf('help') !== -1) {
            return '你可以在左侧面板配置参数，然后点击操作按钮运行实验。如有具体问题请描述一下。';
        }
        if (t.indexOf('sumo') !== -1) {
            return 'SUMO是一款开源的微观交通仿真工具，本平台通过TraCI接口与其交互。';
        }
        if (t.indexOf('mqtt') !== -1) {
            return 'MQTT是轻量级消息协议，本实验用它实现仿真数据与实车的双向通信。';
        }
        if (t.indexOf('carla') !== -1) {
            return 'CARLA是开源自动驾驶仿真器，支持城市场景、天气和传感器模拟。';
        }
        if (t.indexOf('报告') !== -1 || t.indexOf('导出') !== -1) {
            return '实验完成后，可以在结果区域点击"导出实验报告"按钮生成报告。';
        }
        if (t.indexOf('错误') !== -1 || t.indexOf('失败') !== -1 || t.indexOf('error') !== -1) {
            return '如果遇到错误，请检查：1) 后端服务是否正常运行；2) 参数配置是否正确；3) 查看日志获取详细信息。';
        }
        if (t.indexOf('参数') !== -1) {
            return '请在左侧配置面板中调整实验参数，不同实验模块有不同的可配置项。';
        }
        var replies = [
            '收到，请问还有其他问题吗？',
            '好的，如果需要更多帮助可以继续提问。',
            '了解，建议查看左侧的算法讲解部分获取更多信息。',
            '明白了，你可以尝试运行实验看看效果。'
        ];
        return replies[Math.floor(Math.random() * replies.length)];
    }

    // ========== 暴露全局API ==========

    window.ChatLogWidget = {
        addMessage: addMessage,
        showConfirm: showConfirm,
        /** 向日志容器追加一条日志 */
        addLog: function (msg, level) {
            var container = document.getElementById('logContainer');
            if (!container) return;
            var empty = container.querySelector('.log-empty');
            if (empty) empty.remove();
            var div = document.createElement('div');
            div.className = 'log-line log-' + (level || 'info');
            div.textContent = '[' + timeStr() + '] ' + msg;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }
    };

    // ========== 初始化 ==========

    function init() {
        enhanceLogSections();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
