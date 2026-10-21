// 操作说明文档模块JavaScript交互功能

// 全局变量
let currentSection = 'platform-overview';
let searchResults = [];

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    generateQuickLinks();
    updateActiveSection();
});

// 事件监听器初始化
function initializeEventListeners() {
    // 导航链接点击事件
    document.querySelectorAll('.nav-link').forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            var category = this.dataset.category;
            switchSection(category);
            updateNavigation(this);
        });
    });

    // 搜索功能
    var searchInput = document.getElementById('searchInput');
    var searchBtn = document.getElementById('searchBtn');

    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') performSearch();
    });
    searchInput.addEventListener('input', function() {
        if (this.value.length > 2) performSearch();
        else if (this.value.length === 0) clearSearchHighlight();
    });

    // 工具栏按钮
    document.getElementById('backToTopBtn').addEventListener('click', scrollToTop);
    document.getElementById('printBtn').addEventListener('click', printPage);
    document.getElementById('backBtn').addEventListener('click', handleBack);

    // FAQ问题点击展开/收起
    document.querySelectorAll('.faq-question').forEach(function(question) {
        question.addEventListener('click', function() {
            var answer = this.nextElementSibling;
            var isVisible = answer.style.display === 'block';
            // 收起所有
            document.querySelectorAll('.faq-answer').forEach(function(ans) { ans.style.display = 'none'; });
            answer.style.display = isVisible ? 'none' : 'block';
        });
    });

    // 快速链接点击
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('quick-link')) {
            e.preventDefault();
            var targetId = e.target.getAttribute('href').substring(1);
            scrollToElement(targetId);
        }
    });

    // 滚动显示/隐藏返回顶部
    window.addEventListener('scroll', function() {
        var btn = document.getElementById('backToTopBtn');
        btn.style.display = window.pageYOffset > 300 ? 'flex' : 'none';
    });
}

// 切换文档分类
function switchSection(category) {
    currentSection = category;
    document.querySelectorAll('.doc-section').forEach(function(s) { s.classList.remove('active'); });

    // 映射 category -> section id
    var map = {
        'platform-overview': 'platform-overview',
        'resources': 'resources',
        'teacher': 'teacher-guide',
        'student': 'student-guide',
        'experiment-modules': 'experiment-modules',
        'faq': 'faq',
        'support': 'support'
    };
    var target = document.getElementById(map[category] || category);
    if (target) target.classList.add('active');

    generateQuickLinks();
    document.querySelector('.content-area').scrollTop = 0;
}

// 更新导航状态
function updateNavigation(activeLink) {
    document.querySelectorAll('.nav-link').forEach(function(l) { l.classList.remove('active'); });
    activeLink.classList.add('active');
}

// 生成快速链接
function generateQuickLinks() {
    var quickLinks = document.getElementById('quickLinks');
    quickLinks.innerHTML = '';
    var activeSection = document.querySelector('.doc-section.active');
    if (!activeSection) return;

    var headings = activeSection.querySelectorAll('h3[id], .faq-question');
    headings.forEach(function(heading) {
        var li = document.createElement('li');
        var a = document.createElement('a');
        a.textContent = heading.textContent;
        a.href = '#' + (heading.id || 'faq');
        a.className = 'quick-link';
        li.appendChild(a);
        quickLinks.appendChild(li);
    });
}

// 搜索
function performSearch() {
    var searchTerm = document.getElementById('searchInput').value.trim().toLowerCase();
    if (searchTerm.length < 2) { showNotification('请输入至少2个字符进行搜索', 'warning'); return; }

    clearSearchHighlight();
    searchResults = [];

    var allSections = document.querySelectorAll('.doc-section');
    var found = false;

    allSections.forEach(function(section) {
        if (section.textContent.toLowerCase().includes(searchTerm)) {
            found = true;
            highlightSearchTerm(section, searchTerm);
            searchResults.push({ section: section.id, title: section.querySelector('h2').textContent });
        }
    });

    if (found) {
        showNotification('找到 ' + searchResults.length + ' 个相关结果', 'success');
        var current = document.querySelector('.doc-section.active');
        if (!current.textContent.toLowerCase().includes(searchTerm) && searchResults.length > 0) {
            var catMap = { 'platform-overview': 'platform-overview', 'resources': 'resources', 'teacher-guide': 'teacher', 'student-guide': 'student', 'experiment-modules': 'experiment-modules', 'faq': 'faq', 'support': 'support' };
            var cat = catMap[searchResults[0].section] || searchResults[0].section;
            var navLink = document.querySelector('[data-category="' + cat + '"]');
            if (navLink) { switchSection(cat); updateNavigation(navLink); }
        }
    } else {
        showNotification('未找到相关内容', 'info');
    }
}

// 高亮搜索词
function highlightSearchTerm(container, searchTerm) {
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null, false);
    var textNodes = [];
    var node;
    while (node = walker.nextNode()) {
        if (node.nodeValue.toLowerCase().includes(searchTerm)) textNodes.push(node);
    }
    textNodes.forEach(function(tn) {
        var parent = tn.parentNode;
        var regex = new RegExp('(' + searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
        var html = tn.nodeValue.replace(regex, '<span class="highlight">$1</span>');
        var temp = document.createElement('div');
        temp.innerHTML = html;
        while (temp.firstChild) parent.insertBefore(temp.firstChild, tn);
        parent.removeChild(tn);
    });
}

// 清除高亮
function clearSearchHighlight() {
    document.querySelectorAll('.highlight').forEach(function(h) {
        var p = h.parentNode;
        p.replaceChild(document.createTextNode(h.textContent), h);
        p.normalize();
    });
}

// 滚动到元素
function scrollToElement(elementId) {
    var el = document.getElementById(elementId);
    if (el) {
        var area = document.querySelector('.content-area');
        area.scrollTo({ top: el.offsetTop - area.offsetTop - 20, behavior: 'smooth' });
        el.style.backgroundColor = '#fff3cd';
        setTimeout(function() { el.style.backgroundColor = ''; }, 2000);
    }
}

function scrollToTop() {
    document.querySelector('.content-area').scrollTo({ top: 0, behavior: 'smooth' });
}

function printPage() {
    var all = document.querySelectorAll('.doc-section');
    var orig = [];
    all.forEach(function(s, i) { orig[i] = s.className; s.classList.add('active'); });
    window.print();
    setTimeout(function() { all.forEach(function(s, i) { s.className = orig[i]; }); }, 1000);
}

// 返回按钮
function handleBack() {
    window.history.back();
}

// 根据URL hash初始化
function updateActiveSection() {
    var hash = window.location.hash.substring(1);
    var target = 'platform-overview';
    if (hash) {
        if (hash.includes('resource') || hash.includes('download')) target = 'resources';
        else if (hash.includes('teacher')) target = 'teacher';
        else if (hash.includes('student')) target = 'student';
        else if (hash.includes('experiment')) target = 'experiment-modules';
        else if (hash.includes('faq')) target = 'faq';
        else if (hash.includes('support')) target = 'support';
    }
    var link = document.querySelector('[data-category="' + target + '"]');
    if (link) { switchSection(target); updateNavigation(link); }
}

// 通知
function showNotification(message, type) {
    type = type || 'info';
    var n = document.createElement('div');
    n.style.cssText = 'position:fixed;top:80px;right:20px;padding:1rem 1.5rem;border-radius:6px;color:white;font-weight:500;z-index:2000;max-width:300px;box-shadow:0 4px 12px rgba(0,0,0,0.15);animation:slideInRight 0.3s ease;';
    var colors = { success: '#67c23a', error: '#f56c6c', warning: '#e6a23c', info: '#409EFF' };
    n.style.backgroundColor = colors[type] || colors.info;
    n.textContent = message;
    document.body.appendChild(n);
    setTimeout(function() {
        n.style.opacity = '0';
        n.style.transition = 'opacity 0.3s';
        setTimeout(function() { if (n.parentNode) n.parentNode.removeChild(n); }, 300);
    }, 3000);
}

// 键盘快捷键
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.key === 'f') { e.preventDefault(); document.getElementById('searchInput').focus(); }
    if (e.key === 'Escape') { document.getElementById('searchInput').value = ''; clearSearchHighlight(); }
});

// 动画样式
var style = document.createElement('style');
style.textContent = '@keyframes slideInRight{from{opacity:0;transform:translateX(100%)}to{opacity:1;transform:translateX(0)}}';
document.head.appendChild(style);
