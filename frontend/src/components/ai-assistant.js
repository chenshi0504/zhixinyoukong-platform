/**
 * AI实验助手组件
 * 提供智能对话、实验指导、代码理解等功能
 */

class AIAssistant {
    constructor() {
        this.viewMode = 'minimized'; // minimized, normal, maximized
        this.currentModel = 'deepseek';
        this.currentModelName = 'DeepSeek V4 Pro';
        this.chatHistory = [];
        this.container = null;
        this.init();
    }

    init() {
        this.createUI();
        this.bindEvents();
        this.loadConfig();
        this.restoreState();
        this.setupLogoutListener();
    }

    setupLogoutListener() {
        // 监听storage事件（跨标签页）
        window.addEventListener('storage', (e) => {
            if (e.key === 'token' && e.newValue === null) {
                this.clearHistoryAndMinimize();
            }
        });

        // 监听自定义退出登录事件（同一页面）
        window.addEventListener('beforeunload', () => {
            // 检查token是否存在，如果不存在说明已退出登录
            if (!localStorage.getItem('token')) {
                this.clearHistoryAndMinimize();
            }
        });

        // 定期检查token状态
        this.tokenCheckInterval = setInterval(() => {
            if (!localStorage.getItem('token') && this.chatHistory.length > 0) {
                this.clearHistoryAndMinimize();
                clearInterval(this.tokenCheckInterval);
            }
        }, 1000);
    }

    createUI() {
        const html = `
            <!-- AI助手浮动按钮 -->
            <div id="aiAssistantBtn" class="ai-assistant-btn" title="AI实验助手">
                <div class="ai-avatar">🤖</div>
                <div class="ai-pulse"></div>
            </div>

            <!-- AI助手面板 -->
            <div id="aiAssistantPanel" class="ai-assistant-panel">
                <div class="ai-header">
                    <div class="ai-header-left">
                        <div class="ai-avatar-small">🤖</div>
                        <div class="ai-title">
                            <div class="ai-name">AI实验助手</div>
                            <div class="ai-status" id="aiStatus">在线</div>
                        </div>
                    </div>
                    <div class="ai-header-right">
                        <div id="aiModelBadge" class="ai-model-badge" title="当前AI模型">DeepSeek V4 Pro</div>
                        <button class="ai-control-btn" id="aiClearBtn" title="清除对话">🗑</button>
                        <button class="ai-control-btn" id="aiMaximizeBtn" title="放大">⛶</button>
                        <button class="ai-control-btn" id="aiNormalizeBtn" title="缩小" style="display:none;">⊡</button>
                        <button class="ai-close-btn" id="aiCloseBtn" title="最小化">−</button>
                    </div>
                </div>

                <div class="ai-chat-container" id="aiChatContainer">
                    <div class="ai-welcome">
                        <div class="ai-welcome-icon">👋</div>
                        <div class="ai-welcome-text">你好！我是智信优控AI实验助手</div>
                        <div class="ai-welcome-desc">我可以帮你：</div>
                        <div class="ai-welcome-features">
                            <div class="ai-feature">📚 解答实验理论问题</div>
                            <div class="ai-feature">🧭 解释算法原理与实验指标</div>
                            <div class="ai-feature">🎯 指导实验操作步骤</div>
                            <div class="ai-feature">📊 分析实验结果</div>
                        </div>
                        <div class="ai-quick-questions">
                            <div class="ai-quick-title">快速提问：</div>
                            <button class="ai-quick-btn" data-question="什么是车路协同？">什么是车路协同？</button>
                            <button class="ai-quick-btn" data-question="如何进行交通流预测？">如何进行交通流预测？</button>
                            <button class="ai-quick-btn" data-question="SUMO仿真的基本步骤是什么？">SUMO仿真步骤</button>
                        </div>
                    </div>
                </div>

                <div class="ai-input-container">
                    <textarea
                        id="aiInput"
                        class="ai-input"
                        placeholder="输入你的问题；需要代码时请明确说明"
                        rows="1"
                    ></textarea>
                    <button id="aiSendBtn" class="ai-send-btn" title="发送">
                        <span class="ai-send-icon">➤</span>
                    </button>
                </div>

                <div class="ai-footer">
                    <span class="ai-footer-text">由 DeepSeek V4 Pro 提供支持</span>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', html);
        this.container = document.getElementById('aiAssistantPanel');
    }

    bindEvents() {
        const btn = document.getElementById('aiAssistantBtn');
        const closeBtn = document.getElementById('aiCloseBtn');
        const clearBtn = document.getElementById('aiClearBtn');
        const maximizeBtn = document.getElementById('aiMaximizeBtn');
        const normalizeBtn = document.getElementById('aiNormalizeBtn');
        const sendBtn = document.getElementById('aiSendBtn');
        const input = document.getElementById('aiInput');

        btn.addEventListener('click', () => this.openNormal());
        closeBtn.addEventListener('click', () => this.minimize());
        clearBtn.addEventListener('click', () => {
            if (confirm('确定要清除所有对话记录吗？')) {
                this.clearHistory();
            }
        });
        maximizeBtn.addEventListener('click', () => this.maximize());
        normalizeBtn.addEventListener('click', () => this.normalize());
        sendBtn.addEventListener('click', () => this.sendMessage());

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        });

        // 快速提问按钮
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('ai-quick-btn')) {
                const question = e.target.dataset.question;
                input.value = question;
                this.sendMessage();
            }
        });
    }

    async loadConfig() {
        try {
            const token = localStorage.getItem('token');
            const resp = await fetch('/api/v1/ai-assistant/config', {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (resp.ok) {
                const data = await resp.json();
                const modelBadge = document.getElementById('aiModelBadge');

                const deepseekModel = Array.isArray(data.available_models)
                    ? data.available_models.find(model => model.id === 'deepseek')
                    : null;
                const modelName = deepseekModel?.name || 'DeepSeek V4 Pro';
                this.currentModelName = modelName;
                this.currentModel = 'deepseek';

                if (modelBadge) {
                    modelBadge.textContent = deepseekModel?.available === false ? `${modelName}（未配置）` : modelName;
                    modelBadge.classList.toggle('not-configured', deepseekModel?.available === false);
                }

                const footerText = document.querySelector('.ai-footer-text');
                if (footerText) footerText.textContent = `由 ${modelName} 提供支持`;
            }
        } catch (e) {
            console.warn('加载AI配置失败:', e);
        }
    }

    toggle() {
        if (this.viewMode === 'minimized') {
            this.openNormal();
        } else {
            this.minimize();
        }
    }

    openNormal() {
        this.viewMode = 'normal';
        this.container.classList.remove('maximized');
        this.container.classList.add('open');
        document.getElementById('aiAssistantBtn').classList.add('hidden');
        document.getElementById('aiMaximizeBtn').style.display = 'flex';
        document.getElementById('aiNormalizeBtn').style.display = 'none';
        document.getElementById('aiInput').focus();
        this.saveState();
    }

    maximize() {
        this.viewMode = 'maximized';
        this.container.classList.add('maximized');
        document.getElementById('aiMaximizeBtn').style.display = 'none';
        document.getElementById('aiNormalizeBtn').style.display = 'flex';
        this.saveState();
    }

    normalize() {
        this.viewMode = 'normal';
        this.container.classList.remove('maximized');
        document.getElementById('aiMaximizeBtn').style.display = 'flex';
        document.getElementById('aiNormalizeBtn').style.display = 'none';
        this.saveState();
    }

    minimize() {
        this.viewMode = 'minimized';
        this.container.classList.remove('open', 'maximized');
        document.getElementById('aiAssistantBtn').classList.remove('hidden');
        document.getElementById('aiMaximizeBtn').style.display = 'flex';
        document.getElementById('aiNormalizeBtn').style.display = 'none';
        this.saveState();
    }

    open() {
        this.openNormal();
    }

    close() {
        this.minimize();
    }

    async sendMessage() {
        const input = document.getElementById('aiInput');
        const message = input.value.trim();

        if (!message) return;

        // 清空输入框
        input.value = '';
        input.style.height = 'auto';

        // 添加用户消息
        this.addMessage('user', message);

        // 添加助手消息占位
        const assistantMsgId = this.addMessage('assistant', '', true);

        // 获取当前实验模块上下文
        const context = this.getCurrentContext();

        try {
            const token = localStorage.getItem('token');
            const response = await fetch('/api/v1/ai-assistant/chat/stream', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: message,
                    model: 'deepseek',
                    context: context,
                    history: this.chatHistory.slice(-10)
                })
            });

            if (!response.ok) {
                throw new Error('AI服务请求失败');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let assistantMessage = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data.trim() === '[DONE]') continue;

                        try {
                            const json = JSON.parse(data);
                            if (json.error) {
                                assistantMessage = `❌ ${json.error}`;
                                break;
                            }
                            if (json.choices && json.choices[0].delta.content) {
                                assistantMessage += json.choices[0].delta.content;
                                this.updateMessage(assistantMsgId, assistantMessage);
                            }
                        } catch (e) {
                            // 忽略解析错误
                        }
                    }
                }
            }

            // 保存到历史
            this.chatHistory.push(
                { role: 'user', content: message },
                { role: 'assistant', content: assistantMessage }
            );

            // 移除加载状态
            this.updateMessage(assistantMsgId, assistantMessage, false);

            // 保存聊天历史
            this.saveChatHistory();

        } catch (error) {
            console.error('AI对话失败:', error);
            this.updateMessage(assistantMsgId, `❌ 对话失败: ${error.message}`, false);
        }
    }

    addMessage(role, content, loading = false) {
        const container = document.getElementById('aiChatContainer');

        // 移除欢迎界面
        const welcome = container.querySelector('.ai-welcome');
        if (welcome) {
            welcome.remove();
        }

        const msgId = `msg-${Date.now()}-${Math.random()}`;
        const msgClass = role === 'user' ? 'ai-message-user' : 'ai-message-assistant';
        const avatar = role === 'user' ? '👤' : '🤖';

        const html = `
            <div class="ai-message ${msgClass}" id="${msgId}">
                <div class="ai-message-avatar">${avatar}</div>
                <div class="ai-message-content">
                    ${loading ? '<div class="ai-loading"><span></span><span></span><span></span></div>' : this.formatMessage(content)}
                </div>
            </div>
        `;

        container.insertAdjacentHTML('beforeend', html);
        container.scrollTop = container.scrollHeight;

        return msgId;
    }

    updateMessage(msgId, content, loading = true) {
        const msg = document.getElementById(msgId);
        if (!msg) return;

        const contentDiv = msg.querySelector('.ai-message-content');
        if (loading) {
            contentDiv.innerHTML = this.formatMessage(content) + '<div class="ai-loading"><span></span><span></span><span></span></div>';
        } else {
            contentDiv.innerHTML = this.formatMessage(content);
        }

        const container = document.getElementById('aiChatContainer');
        container.scrollTop = container.scrollHeight;
    }

    formatMessage(content) {
        if (!content) return '';

        // 简单的markdown渲染
        let html = content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');

        // 代码块
        html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre><code class="language-${lang || 'text'}">${this.escapeHtml(code.trim())}</code></pre>`;
        });

        return html;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getCurrentContext() {
        // 从URL或页面标题推断当前实验模块
        const path = window.location.pathname;
        if (path.includes('data_collection')) return 'data-collection';
        if (path.includes('data_fusion')) return 'data-fusion';
        if (path.includes('traffic_reconstruction')) return 'traffic-reconstruction';
        if (path.includes('traffic_flow_prediction')) return 'traffic-prediction';
        if (path.includes('signal_optimization')) return 'signal-optimization';
        if (path.includes('path_guidance')) return 'path-guidance';
        if (path.includes('vehicle_speed_control')) return 'speed-control';
        if (path.includes('three_level_control')) return 'cooperative-control';
        return null;
    }

    saveState() {
        try {
            localStorage.setItem('aiAssistantViewMode', this.viewMode);
        } catch (e) {
            console.warn('无法保存AI助手状态:', e);
        }
    }

    saveChatHistory() {
        try {
            // 只保存最近20条消息，避免localStorage溢出
            const recentHistory = this.chatHistory.slice(-20);
            localStorage.setItem('aiAssistantHistory', JSON.stringify(recentHistory));
        } catch (e) {
            console.warn('无法保存聊天历史:', e);
        }
    }

    restoreState() {
        try {
            // 恢复视图模式
            const savedViewMode = localStorage.getItem('aiAssistantViewMode');
            if (savedViewMode === 'normal') {
                this.openNormal();
            } else if (savedViewMode === 'maximized') {
                this.openNormal();
                setTimeout(() => this.maximize(), 100);
            }

            // 恢复聊天历史
            const savedHistory = localStorage.getItem('aiAssistantHistory');
            if (savedHistory) {
                this.chatHistory = JSON.parse(savedHistory);
                this.restoreChatUI();
            }
        } catch (e) {
            console.warn('无法恢复AI助手状态:', e);
        }
    }

    restoreChatUI() {
        const container = document.getElementById('aiChatContainer');

        // 移除欢迎界面
        const welcome = container.querySelector('.ai-welcome');
        if (welcome) {
            welcome.remove();
        }

        // 重新渲染所有消息
        this.chatHistory.forEach(msg => {
            const msgId = `msg-${Date.now()}-${Math.random()}`;
            const msgClass = msg.role === 'user' ? 'ai-message-user' : 'ai-message-assistant';
            const avatar = msg.role === 'user' ? '👤' : '🤖';

            const html = `
                <div class="ai-message ${msgClass}" id="${msgId}">
                    <div class="ai-message-avatar">${avatar}</div>
                    <div class="ai-message-content">
                        ${this.formatMessage(msg.content)}
                    </div>
                </div>
            `;

            container.insertAdjacentHTML('beforeend', html);
        });

        container.scrollTop = container.scrollHeight;
    }

    clearHistory() {
        // 清除聊天历史
        this.chatHistory = [];
        localStorage.removeItem('aiAssistantHistory');

        // 重置UI
        const container = document.getElementById('aiChatContainer');
        container.innerHTML = `
            <div class="ai-welcome">
                <div class="ai-welcome-icon">👋</div>
                <div class="ai-welcome-text">你好！我是智信优控AI实验助手</div>
                <div class="ai-welcome-desc">我可以帮你：</div>
                <div class="ai-welcome-features">
                    <div class="ai-feature">📚 解答实验理论问题</div>
                    <div class="ai-feature">🧭 解释算法原理与实验指标</div>
                    <div class="ai-feature">🎯 指导实验操作步骤</div>
                    <div class="ai-feature">📊 分析实验结果</div>
                </div>
                <div class="ai-quick-questions">
                    <div class="ai-quick-title">快速提问：</div>
                    <button class="ai-quick-btn" data-question="什么是车路协同？">什么是车路协同？</button>
                    <button class="ai-quick-btn" data-question="如何进行交通流预测？">如何进行交通流预测？</button>
                    <button class="ai-quick-btn" data-question="SUMO仿真的基本步骤是什么？">SUMO仿真步骤</button>
                </div>
            </div>
        `;
    }

    clearHistoryAndMinimize() {
        // 清除历史并最小化（用于退出登录）
        this.clearHistory();
        localStorage.removeItem('aiAssistantViewMode');
        this.minimize();
    }
}

// 自动初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.aiAssistant = new AIAssistant();
    });
} else {
    window.aiAssistant = new AIAssistant();
}
