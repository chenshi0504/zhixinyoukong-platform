// 实验报告管理模块JavaScript交互功能

// API配置
const API_BASE = '/api/v1';
function authHeaders() {
    return { 'Authorization': 'Bearer ' + (localStorage.getItem('token') || '') };
}
function authJsonHeaders() {
    return { 'Authorization': 'Bearer ' + (localStorage.getItem('token') || ''), 'Content-Type': 'application/json' };
}

// 全局变量
let reports = [];
let filteredReports = [];
let currentPage = 1;
let pageSize = 20;
let selectedReports = [];
let currentReviewReport = null;

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    try {
        console.log('开始初始化报告管理页面...');

        // 检查登录状态
        var token = localStorage.getItem('token');
        if (!token) { window.location.href = '../登录界面/login.html'; return; }

        // 初始化云端平台连接检测
        if (window.CloudStatusChecker) {
            window.CloudStatusChecker.createCloudStatusChecker({
                dotElement: document.getElementById('cloudStatusDot'),
                textElement: document.getElementById('cloudStatusText'),
                autoStart: true
            });
        }

        loadReports();
        initializeEventListeners();

        console.log('报告管理页面初始化完成');
    } catch (error) {
        console.error('初始化失败:', error);
        document.body.innerHTML = '<div style="padding: 20px; color: red; font-family: Arial;">页面初始化失败: ' + error.message + '</div>';
    }
});

// 从后端加载报告列表
async function loadReports() {
    try {
        var resp = await fetch(API_BASE + '/reports', { headers: authHeaders() });
        if (resp.status === 401) { localStorage.removeItem('token'); window.location.href = '../登录界面/login.html'; return; }
        if (!resp.ok) throw new Error('加载报告失败');
        var data = await resp.json();
        reports = data.map(function(r) {
            return {
                id: r.id,
                studentName: r.student_name || '未知',
                studentClass: r.student_class || '',
                experimentName: r.task_title || '未知任务',
                experimentType: r.experiment_type || '实验',
                submitTime: r.submitted_at || r.created_at || '',
                fileName: r.file_name || '',
                fileSize: r.file_size ? (r.file_size / 1024 / 1024).toFixed(1) + 'MB' : '未知',
                reviewStatus: r.status || 'pending',
                score: r.score
            };
        });
    } catch (e) {
        console.error('加载报告失败:', e);
        reports = [];
    }
    filteredReports = [...reports];
    updateStatistics();
    renderReportTable();
    renderPagination();
}

async function syncLatestCloudData() {
    try {
        var resp = await fetch(API_BASE + '/sync/pull', {
            method: 'POST',
            headers: authHeaders()
        });
        if (resp.status === 401) {
            localStorage.removeItem('token');
            window.location.href = '../登录界面/login.html';
            return null;
        }
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.warn('云端同步失败，回退为本地刷新:', e);
        return null;
    }
}

function setRefreshState(refreshing) {
    var btn = document.getElementById('refreshReportsBtn');
    if (!btn) return;
    btn.disabled = refreshing;
    btn.classList.toggle('spinning', refreshing);
}

async function refreshReportManagementData() {
    setRefreshState(true);
    try {
        var syncResult = await syncLatestCloudData();
        await loadReports();
        applyFilters();
        if (syncResult && syncResult.success) {
            showNotification('已刷新最新报告数据', 'success');
        } else if (syncResult && syncResult.errors && syncResult.errors.length > 0) {
            showNotification('报告列表已刷新，部分云端数据同步失败', 'warning');
        } else {
            showNotification('报告列表已刷新', 'success');
        }
    } catch (error) {
        console.error('刷新报告数据失败:', error);
        showNotification('刷新失败: ' + error.message, 'error');
    } finally {
        setRefreshState(false);
    }
}

// 事件监听器初始化
function initializeEventListeners() {
    try {
        console.log('初始化事件监听器...');
        
        // 主要按钮事件
        const batchReviewBtn = document.getElementById('batchReviewBtn');
        const exportReportsBtn = document.getElementById('exportReportsBtn');
        const templateMgmtBtn = document.getElementById('templateMgmtBtn');
        const refreshReportsBtn = document.getElementById('refreshReportsBtn');
        const backBtn = document.getElementById('backBtn');
        
        if (batchReviewBtn) batchReviewBtn.addEventListener('click', showBatchScoreModal);
        if (exportReportsBtn) exportReportsBtn.addEventListener('click', exportReports);
        if (templateMgmtBtn) templateMgmtBtn.addEventListener('click', showTemplateModal);
        if (refreshReportsBtn) refreshReportsBtn.addEventListener('click', refreshReportManagementData);
        if (backBtn) backBtn.addEventListener('click', handleBack);
        
        // 筛选器事件
        const experimentFilter = document.getElementById('experimentFilter');
        const statusFilter = document.getElementById('statusFilter');
        const classFilter = document.getElementById('classFilter');
        const searchInput = document.getElementById('searchInput');
        
        if (experimentFilter) experimentFilter.addEventListener('change', applyFilters);
        if (statusFilter) statusFilter.addEventListener('change', applyFilters);
        if (classFilter) classFilter.addEventListener('change', applyFilters);
        if (searchInput) searchInput.addEventListener('input', applyFilters);
        
        // 表格事件
        const selectAllCheckbox = document.getElementById('selectAllCheckbox');
        const batchDownloadBtn = document.getElementById('batchDownloadBtn');
        const batchScoreBtn = document.getElementById('batchScoreBtn');
        
        if (selectAllCheckbox) selectAllCheckbox.addEventListener('change', handleSelectAll);
        if (batchDownloadBtn) batchDownloadBtn.addEventListener('click', handleBatchDownload);
        if (batchScoreBtn) batchScoreBtn.addEventListener('click', showBatchScoreModal);
        
        // 分页事件
        const prevPageBtn = document.getElementById('prevPageBtn');
        const nextPageBtn = document.getElementById('nextPageBtn');
        const pageSizeSelect = document.getElementById('pageSizeSelect');
        
        if (prevPageBtn) prevPageBtn.addEventListener('click', () => changePage(currentPage - 1));
        if (nextPageBtn) nextPageBtn.addEventListener('click', () => changePage(currentPage + 1));
        if (pageSizeSelect) pageSizeSelect.addEventListener('change', handlePageSizeChange);
        
        // 模态框关闭事件
        setupModalEvents();
        
        console.log('事件监听器初始化完成');
    } catch (error) {
        console.error('事件监听器初始化失败:', error);
    }
}

// 模态框事件设置
function setupModalEvents() {
    // 批阅模态框
    document.getElementById('closeReviewModal').addEventListener('click', hideReviewModal);
    document.getElementById('cancelReviewBtn').addEventListener('click', hideReviewModal);
    document.getElementById('saveReviewBtn').addEventListener('click', saveReview);
    document.getElementById('submitReviewBtn').addEventListener('click', submitReview);
    
    // 批量评分模态框
    document.getElementById('closeBatchScoreModal').addEventListener('click', hideBatchScoreModal);
    document.getElementById('cancelBatchScoreBtn').addEventListener('click', hideBatchScoreModal);
    document.getElementById('confirmBatchScoreBtn').addEventListener('click', handleBatchScore);
    
    // 模板管理模态框
    document.getElementById('closeTemplateModal').addEventListener('click', hideTemplateModal);
    document.getElementById('closeTemplateBtn').addEventListener('click', hideTemplateModal);
    
    // 标签页切换
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            switchTab(this.dataset.tab);
        });
    });
    
    // 评分输入事件
    const scoreInputs = ['processScore', 'analysisScore', 'conclusionScore', 'formatScore', 'innovationScore'];
    scoreInputs.forEach(inputId => {
        document.getElementById(inputId).addEventListener('input', calculateTotalScore);
    });
    
    // 快速评语模板点击事件
    document.querySelectorAll('.template-tag').forEach(tag => {
        tag.addEventListener('click', function() {
            insertQuickFeedback(this.textContent);
        });
    });
    
    // 反馈文本框字数统计
    const overallFeedback = document.getElementById('overallFeedback');
    const improvementSuggestions = document.getElementById('improvementSuggestions');
    
    if (overallFeedback) {
        overallFeedback.addEventListener('input', function() {
            updateCharCount('overallFeedback', 'overallFeedbackCount', 500);
        });
    }
    
    if (improvementSuggestions) {
        improvementSuggestions.addEventListener('input', function() {
            updateCharCount('improvementSuggestions', 'improvementSuggestionsCount', 500);
        });
    }
}

// 插入快速评语
function insertQuickFeedback(text) {
    const overallFeedback = document.getElementById('overallFeedback');
    const currentText = overallFeedback.value;
    
    // 如果已有内容，添加分号和空格
    const separator = currentText.trim() ? '；' : '';
    overallFeedback.value = currentText + separator + text;
    
    // 更新字数统计
    updateCharCount('overallFeedback', 'overallFeedbackCount', 500);
    
    // 添加视觉反馈
    overallFeedback.style.backgroundColor = '#e7f3ff';
    setTimeout(() => {
        overallFeedback.style.backgroundColor = '';
    }, 300);
    
    // 显示提示
    showNotification('已插入评语模板', 'success');
}

// 更新字数统计
function updateCharCount(textareaId, countId, maxLength) {
    const textarea = document.getElementById(textareaId);
    const countElement = document.getElementById(countId);
    
    if (!textarea || !countElement) return;
    
    const currentLength = textarea.value.length;
    countElement.textContent = currentLength;
    
    // 根据字数添加警告样式
    const countContainer = countElement.parentElement;
    countContainer.classList.remove('warning', 'error');
    
    if (currentLength > maxLength * 0.9) {
        countContainer.classList.add('warning');
    }
    
    if (currentLength >= maxLength) {
        countContainer.classList.add('error');
        textarea.value = textarea.value.substring(0, maxLength);
        countElement.textContent = maxLength;
    }
}

// 显示批阅模态框
function showReviewModal(reportId) {
    const report = reports.find(r => r.id === reportId);
    if (!report) return;
    
    currentReviewReport = report;
    
    // 填充报告信息
    document.getElementById('reviewStudentName').textContent = report.studentName;
    document.getElementById('reviewExperimentName').textContent = report.experimentName;
    document.getElementById('reviewSubmitTime').textContent = report.submitTime;
    document.getElementById('reviewFileName').textContent = report.fileName;
    
    // 模拟报告预览
    document.getElementById('previewArea').innerHTML = `
        <div class="preview-placeholder">
            <div class="placeholder-icon">📄</div>
            <p>报告预览：${report.fileName}</p>
            <p class="placeholder-hint">文件大小：${report.fileSize}</p>
        </div>
    `;
    
    document.getElementById('reviewModal').classList.add('show');
}

// 隐藏批阅模态框
function hideReviewModal() {
    document.getElementById('reviewModal').classList.remove('show');
    currentReviewReport = null;
}

// 切换标签页
function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === tabName + 'Tab');
    });
}

// 计算总分 - 增强版本，带验证和视觉反馈
function calculateTotalScore() {
    const scoreInputs = [
        { id: 'processScore', max: 30, name: '实验过程' },
        { id: 'analysisScore', max: 25, name: '数据分析' },
        { id: 'conclusionScore', max: 20, name: '结论总结' },
        { id: 'formatScore', max: 15, name: '报告规范' },
        { id: 'innovationScore', max: 10, name: '创新性' }
    ];
    
    let total = 0;
    let hasError = false;
    
    scoreInputs.forEach(input => {
        const element = document.getElementById(input.id);
        const value = parseInt(element.value) || 0;
        
        // 验证分数范围
        if (value < 0) {
            element.value = 0;
            showInputError(element, `${input.name}分数不能为负数`);
            hasError = true;
        } else if (value > input.max) {
            element.value = input.max;
            showInputError(element, `${input.name}最高${input.max}分`);
            hasError = true;
        } else {
            clearInputError(element);
            total += value;
        }
        
        // 添加视觉反馈
        updateScoreVisual(element, value, input.max);
    });
    
    // 更新总分显示
    const totalElement = document.getElementById('totalScore');
    totalElement.textContent = total;
    
    // 根据总分添加颜色反馈和等级
    totalElement.className = '';
    const gradeElement = document.getElementById('scoreGrade');
    let grade = '';
    let tips = [];
    
    if (total >= 90) {
        totalElement.classList.add('score-excellent');
        grade = '优秀';
        tips = ['报告质量优秀，继续保持！', '可以作为优秀范例展示'];
    } else if (total >= 80) {
        totalElement.classList.add('score-good');
        grade = '良好';
        tips = ['报告质量良好', '部分细节可以进一步完善'];
    } else if (total >= 70) {
        totalElement.classList.add('score-pass');
        grade = '中等';
        tips = ['报告基本达标', '建议加强数据分析和结论总结'];
    } else if (total >= 60) {
        totalElement.classList.add('score-pass');
        grade = '及格';
        tips = ['报告勉强及格', '需要在多个方面进行改进'];
    } else {
        totalElement.classList.add('score-fail');
        grade = '不及格';
        tips = ['报告未达标准', '建议重新完成实验并提交报告'];
    }
    
    if (gradeElement) {
        gradeElement.textContent = grade;
    }
    
    // 更新评分建议
    updateScoringTips(tips);
    
    return total;
}

// 更新评分建议提示
function updateScoringTips(tips) {
    const tipsList = document.getElementById('scoringTipsList');
    if (!tipsList || tips.length === 0) return;
    
    // 保留前3条固定提示，添加动态提示
    const fixedTips = [
        '请根据评分标准客观评价学生报告',
        '建议提供具体的改进意见',
        '鼓励学生的创新思维和独立思考'
    ];
    
    const allTips = [...fixedTips, ...tips];
    
    tipsList.innerHTML = allTips.map(tip => `<li>${tip}</li>`).join('');
}

// 显示输入错误提示
function showInputError(element, message) {
    element.classList.add('input-error');
    
    // 移除旧的错误提示
    const oldError = element.parentElement.querySelector('.error-message');
    if (oldError) oldError.remove();
    
    // 添加新的错误提示
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = message;
    element.parentElement.appendChild(errorDiv);
    
    // 3秒后自动移除
    setTimeout(() => {
        errorDiv.remove();
        element.classList.remove('input-error');
    }, 3000);
}

// 清除输入错误
function clearInputError(element) {
    element.classList.remove('input-error');
    const errorMsg = element.parentElement.querySelector('.error-message');
    if (errorMsg) errorMsg.remove();
}

// 更新分数视觉反馈
function updateScoreVisual(element, value, max) {
    const percentage = (value / max) * 100;
    const parent = element.parentElement;
    
    // 移除旧的进度条
    let progressBar = parent.querySelector('.score-progress');
    if (!progressBar) {
        progressBar = document.createElement('div');
        progressBar.className = 'score-progress';
        parent.appendChild(progressBar);
    }
    
    // 更新进度条
    progressBar.style.width = percentage + '%';
    progressBar.className = 'score-progress';
    
    if (percentage >= 80) {
        progressBar.classList.add('progress-excellent');
    } else if (percentage >= 60) {
        progressBar.classList.add('progress-good');
    } else {
        progressBar.classList.add('progress-low');
    }
}

// 保存批阅 - 调用后端API
async function saveReview() {
    if (!currentReviewReport) return;
    
    var total = parseInt(document.getElementById('totalScore').textContent) || 0;
    var overallFeedback = document.getElementById('overallFeedback').value;
    
    if (total === 0) {
        showNotification('请先进行评分', 'warning');
        return;
    }
    if (!overallFeedback.trim()) {
        showNotification('请填写总体评价', 'warning');
        return;
    }
    
    try {
        var resp = await fetch(API_BASE + '/reports/' + currentReviewReport.id + '/grade', {
            method: 'PUT',
            headers: authJsonHeaders(),
            body: JSON.stringify({ score: total, feedback: overallFeedback })
        });
        if (!resp.ok) {
            var err = await resp.json().catch(function() { return null; });
            throw new Error((err && err.detail && err.detail.message) || '保存批阅失败');
        }
        showNotification('批阅已保存', 'success');
        loadReports();
    } catch (error) {
        showNotification(error.message || '保存批阅失败', 'error');
    }
}

// 提交批阅
async function submitReview() {
    if (!currentReviewReport) return;
    
    var total = parseInt(document.getElementById('totalScore').textContent) || 0;
    var overallFeedback = document.getElementById('overallFeedback').value;
    
    if (total === 0) {
        showNotification('请先进行评分', 'warning');
        return;
    }
    if (!overallFeedback.trim()) {
        showNotification('请填写总体评价', 'warning');
        return;
    }
    
    showConfirmDialog(
        '确定要提交批阅吗？提交后将无法修改。',
        async function() {
            try {
                var resp = await fetch(API_BASE + '/reports/' + currentReviewReport.id + '/grade', {
                    method: 'PUT',
                    headers: authJsonHeaders(),
                    body: JSON.stringify({ score: total, feedback: overallFeedback })
                });
                if (!resp.ok) throw new Error('提交批阅失败');
                hideReviewModal();
                showNotification('批阅已提交成功！', 'success');
                loadReports();
            } catch (error) {
                showNotification(error.message || '提交批阅失败', 'error');
            }
        },
        function() {
            showNotification('已取消提交', 'info');
        }
    );
}

// 显示批量评分模态框
function showBatchScoreModal() {
    if (selectedReports.length === 0) {
        showNotification('请先选择要批量评分的报告', 'warning');
        return;
    }
    
    document.getElementById('batchScoreCount').textContent = selectedReports.length;
    document.getElementById('batchScoreModal').classList.add('show');
}

// 隐藏批量评分模态框
function hideBatchScoreModal() {
    document.getElementById('batchScoreModal').classList.remove('show');
}

// 处理批量评分
async function handleBatchScore() {
    const process = parseInt(document.getElementById('batchProcessScore').value) || 0;
    const analysis = parseInt(document.getElementById('batchAnalysisScore').value) || 0;
    const conclusion = parseInt(document.getElementById('batchConclusionScore').value) || 0;
    const format = parseInt(document.getElementById('batchFormatScore').value) || 0;
    const innovation = parseInt(document.getElementById('batchInnovationScore').value) || 0;
    const totalScore = process + analysis + conclusion + format + innovation;
    const feedback = document.getElementById('batchFeedback').value;
    
    var failed = 0;
    for (var i = 0; i < selectedReports.length; i++) {
        try {
            var resp = await fetch(API_BASE + '/reports/' + selectedReports[i] + '/grade', {
                method: 'PUT',
                headers: authJsonHeaders(),
                body: JSON.stringify({ score: totalScore, feedback: feedback })
            });
            if (!resp.ok) failed++;
        } catch (e) { failed++; }
    }
    
    selectedReports = [];
    updateSelectedReports();
    hideBatchScoreModal();
    
    if (failed > 0) {
        showNotification('批量评分完成，' + failed + '份失败', 'warning');
    } else {
        showNotification('批量评分完成', 'success');
    }
    loadReports();
}

// 处理全选
function handleSelectAll() {
    const isChecked = document.getElementById('selectAllCheckbox').checked;
    const checkboxes = document.querySelectorAll('#reportTableBody input[type="checkbox"]');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
    });
    
    updateSelectedReports();
}

// 更新选中的报告
function updateSelectedReports() {
    const checkboxes = document.querySelectorAll('#reportTableBody input[type="checkbox"]:checked');
    selectedReports = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    document.getElementById('selectedCount').textContent = selectedReports.length;
    document.getElementById('batchDownloadBtn').disabled = selectedReports.length === 0;
    document.getElementById('batchScoreBtn').disabled = selectedReports.length === 0;
}

// 批量下载
function handleBatchDownload() {
    if (selectedReports.length === 0) return;
    
    showNotification(`正在下载 ${selectedReports.length} 份报告...`, 'info');
    
    setTimeout(() => {
        showNotification('下载完成', 'success');
    }, 2000);
}

// 应用筛选条件
function applyFilters() {
    const experimentFilter = document.getElementById('experimentFilter').value;
    const statusFilter = document.getElementById('statusFilter').value;
    const classFilter = document.getElementById('classFilter').value;
    const searchText = document.getElementById('searchInput').value.toLowerCase().trim();
    
    filteredReports = reports.filter(report => {
        const experimentMatch = experimentFilter === 'all' || report.experimentType === experimentFilter;
        const statusMatch = statusFilter === 'all' || report.reviewStatus === statusFilter;
        const classMatch = classFilter === 'all' || report.studentClass === classFilter;
        const searchMatch = !searchText || 
            report.studentName.toLowerCase().includes(searchText) ||
            report.experimentName.toLowerCase().includes(searchText);
        
        return experimentMatch && statusMatch && classMatch && searchMatch;
    });
    
    currentPage = 1;
    renderReportTable();
    renderPagination();
}

// 渲染报告表格
function renderReportTable() {
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = startIndex + pageSize;
    const pageReports = filteredReports.slice(startIndex, endIndex);
    
    const tableHTML = pageReports.map(report => {
        const statusText = getStatusText(report.reviewStatus);
        const statusClass = report.reviewStatus.replace('_', '-');
        
        return `
            <tr>
                <td><input type="checkbox" value="${report.id}" onchange="updateSelectedReports()"></td>
                <td>${report.studentName}</td>
                <td>${report.studentClass}</td>
                <td>${report.experimentName}</td>
                <td>${report.experimentType}</td>
                <td>${report.submitTime}</td>
                <td>
                    <div>${report.fileName}</div>
                    <small style="color: #999;">${report.fileSize}</small>
                </td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>${report.score !== null ? report.score + '/100' : '-'}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-sm btn-info" onclick="showReviewModal(${report.id})">批阅</button>
                        <button class="btn btn-sm btn-secondary" onclick="downloadReport(${report.id})">下载</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
    
    document.getElementById('reportTableBody').innerHTML = tableHTML || 
        '<tr><td colspan="10" style="text-align: center; color: #999; padding: 2rem;">暂无报告数据</td></tr>';
    
    selectedReports = [];
    updateSelectedReports();
}

// 渲染分页
function renderPagination() {
    const totalPages = Math.ceil(filteredReports.length / pageSize);
    
    document.getElementById('prevPageBtn').disabled = currentPage <= 1;
    document.getElementById('nextPageBtn').disabled = currentPage >= totalPages;
    
    let pageNumbersHTML = '';
    for (let i = 1; i <= totalPages; i++) {
        pageNumbersHTML += `
            <button class="page-number ${i === currentPage ? 'active' : ''}" onclick="changePage(${i})">
                ${i}
            </button>
        `;
    }
    
    document.getElementById('pageNumbers').innerHTML = pageNumbersHTML;
}

// 切换页面
function changePage(page) {
    const totalPages = Math.ceil(filteredReports.length / pageSize);
    if (page < 1 || page > totalPages) return;
    
    currentPage = page;
    renderReportTable();
    renderPagination();
}

// 处理每页条数变化
function handlePageSizeChange() {
    pageSize = parseInt(document.getElementById('pageSizeSelect').value);
    currentPage = 1;
    renderReportTable();
    renderPagination();
}

// 更新统计数据
function updateStatistics() {
    const total = reports.length;
    const pending = reports.filter(r => r.reviewStatus === 'pending').length;
    const reviewed = reports.filter(r => r.reviewStatus === 'reviewed').length;
    const reviewedReports = reports.filter(r => r.score !== null);
    const avgScore = reviewedReports.length > 0 ? 
        (reviewedReports.reduce((sum, r) => sum + r.score, 0) / reviewedReports.length).toFixed(1) : 0;
    const progress = total > 0 ? Math.round(reviewed / total * 100) : 0;
    
    document.getElementById('totalReports').textContent = total;
    document.getElementById('pendingReports').textContent = pending;
    document.getElementById('reviewedReports').textContent = reviewed;
    document.getElementById('averageScore').textContent = avgScore;
    document.getElementById('reviewProgress').textContent = progress + '%';
}

// 获取状态文本
function getStatusText(status) {
    const statusMap = {
        'pending': '待批阅',
        'reviewing': '批阅中',
        'reviewed': '已批阅',
        'revision_required': '需修改'
    };
    return statusMap[status] || status;
}

// 下载报告
function downloadReport(reportId) {
    var report = reports.find(function(r) { return r.id === reportId; });
    if (!report) return;
    
    showNotification('正在下载 ' + report.fileName + '...', 'info');
    
    // 通过后端API下载
    var token = localStorage.getItem('token') || '';
    var link = document.createElement('a');
    link.href = API_BASE + '/reports/' + reportId + '/download';
    link.download = report.fileName;
    // 使用fetch带token下载
    fetch(API_BASE + '/reports/' + reportId + '/download', { headers: authHeaders() })
        .then(function(resp) {
            if (!resp.ok) throw new Error('下载失败');
            return resp.blob();
        })
        .then(function(blob) {
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = report.fileName || 'report';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showNotification('下载完成', 'success');
        })
        .catch(function(e) {
            console.error('下载失败:', e);
            showNotification('下载失败: ' + e.message, 'error');
        });
}

// 导出报告
function exportReports() {
    // 显示导出选项模态框
    showExportModal();
}

// 显示导出选项模态框
function showExportModal() {
    // 创建导出选项模态框
    const exportModal = document.createElement('div');
    exportModal.className = 'modal';
    exportModal.id = 'exportModal';
    exportModal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>导出学生报告</h3>
                <button class="close-btn" onclick="hideExportModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="export-options">
                    <h4>选择导出内容</h4>
                    <div class="export-option">
                        <input type="radio" id="exportSelected" name="exportType" value="selected" ${selectedReports.length > 0 ? 'checked' : ''}>
                        <label for="exportSelected">导出选中的报告 (${selectedReports.length}份)</label>
                    </div>
                    <div class="export-option">
                        <input type="radio" id="exportFiltered" name="exportType" value="filtered" ${selectedReports.length === 0 ? 'checked' : ''}>
                        <label for="exportFiltered">导出当前筛选结果 (${filteredReports.length}份)</label>
                    </div>
                    <div class="export-option">
                        <input type="radio" id="exportAll" name="exportType" value="all">
                        <label for="exportAll">导出全部报告 (${reports.length}份)</label>
                    </div>
                </div>
                
                <div class="export-format">
                    <h4>选择导出格式</h4>
                    <div class="format-options">
                        <div class="format-option">
                            <input type="checkbox" id="exportFiles" checked>
                            <label for="exportFiles">导出报告文件 (PDF/Word)</label>
                        </div>
                        <div class="format-option">
                            <input type="checkbox" id="exportStatistics" checked>
                            <label for="exportStatistics">导出统计表格 (CSV/Excel)</label>
                        </div>
                        <div class="format-option">
                            <input type="checkbox" id="exportSummary">
                            <label for="exportSummary">导出批阅汇总 (PDF)</label>
                        </div>
                    </div>
                </div>
                
                <div class="export-settings">
                    <h4>导出设置</h4>
                    <div class="setting-item">
                        <input type="checkbox" id="includeScores" checked>
                        <label for="includeScores">包含评分信息</label>
                    </div>
                    <div class="setting-item">
                        <input type="checkbox" id="includeFeedback" checked>
                        <label for="includeFeedback">包含批阅反馈</label>
                    </div>
                    <div class="setting-item">
                        <input type="checkbox" id="createZip" checked>
                        <label for="createZip">打包为ZIP文件</label>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" onclick="hideExportModal()">取消</button>
                <button type="button" class="btn btn-primary" onclick="startExport()">开始导出</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(exportModal);
    exportModal.classList.add('show');
}

// 隐藏导出模态框
function hideExportModal() {
    const exportModal = document.getElementById('exportModal');
    if (exportModal) {
        exportModal.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(exportModal);
        }, 300);
    }
}

// 开始导出
function startExport() {
    const exportType = document.querySelector('input[name="exportType"]:checked').value;
    const exportFiles = document.getElementById('exportFiles').checked;
    const exportStatistics = document.getElementById('exportStatistics').checked;
    const exportSummary = document.getElementById('exportSummary').checked;
    const includeScores = document.getElementById('includeScores').checked;
    const includeFeedback = document.getElementById('includeFeedback').checked;
    const createZip = document.getElementById('createZip').checked;
    
    // 确定要导出的报告
    let reportsToExport = [];
    switch (exportType) {
        case 'selected':
            reportsToExport = reports.filter(r => selectedReports.includes(r.id));
            break;
        case 'filtered':
            reportsToExport = filteredReports;
            break;
        case 'all':
            reportsToExport = reports;
            break;
    }
    
    if (reportsToExport.length === 0) {
        showNotification('没有可导出的报告', 'warning');
        return;
    }
    
    hideExportModal();
    
    // 显示导出进度
    showExportProgress(reportsToExport, {
        exportFiles,
        exportStatistics,
        exportSummary,
        includeScores,
        includeFeedback,
        createZip
    });
}

// 显示导出进度
function showExportProgress(reportsToExport, options) {
    // 创建进度模态框
    const progressModal = document.createElement('div');
    progressModal.className = 'modal';
    progressModal.id = 'exportProgressModal';
    progressModal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>导出进度</h3>
            </div>
            <div class="modal-body">
                <div class="progress-info">
                    <p>正在导出 ${reportsToExport.length} 份报告...</p>
                    <div class="progress-bar">
                        <div class="progress-fill" id="progressFill" style="width: 0%"></div>
                    </div>
                    <div class="progress-text">
                        <span id="progressText">准备中...</span>
                        <span id="progressPercent">0%</span>
                    </div>
                </div>
                <div class="export-log" id="exportLog">
                    <div class="log-item">开始导出任务...</div>
                </div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" id="cancelExportBtn" onclick="cancelExport()">取消</button>
                <button type="button" class="btn btn-primary" id="completeExportBtn" onclick="hideExportProgress()" style="display: none;">完成</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(progressModal);
    progressModal.classList.add('show');
    
    // 开始实际导出过程
    performExport(reportsToExport, options);
}

// 执行导出
async function performExport(reportsToExport, options) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const progressPercent = document.getElementById('progressPercent');
    const exportLog = document.getElementById('exportLog');
    
    let currentStep = 0;
    const totalSteps = reportsToExport.length + (options.exportStatistics ? 1 : 0) + (options.exportSummary ? 1 : 0);
    
    function updateProgress(step, text) {
        const percent = Math.round((step / totalSteps) * 100);
        progressFill.style.width = percent + '%';
        progressText.textContent = text;
        progressPercent.textContent = percent + '%';
        
        const logItem = document.createElement('div');
        logItem.className = 'log-item';
        logItem.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
        exportLog.appendChild(logItem);
        exportLog.scrollTop = exportLog.scrollHeight;
    }
    
    try {
        // 创建文件列表
        const filesToDownload = [];
        
        // 导出报告文件
        if (options.exportFiles) {
            updateProgress(currentStep++, '准备报告文件...');
            
            for (let i = 0; i < reportsToExport.length; i++) {
                const report = reportsToExport[i];
                updateProgress(currentStep++, `处理 ${report.studentName} 的报告...`);
                
                // 生成报告文件
                const reportContent = generateReportContent(report, options);
                const blob = new Blob([reportContent], { type: 'text/html;charset=utf-8' });
                
                filesToDownload.push({
                    name: `${report.studentName}_${report.experimentName}_报告.html`,
                    blob: blob,
                    type: 'report'
                });
                
                // 模拟处理时间
                await new Promise(resolve => setTimeout(resolve, 200));
            }
        }
        
        // 导出统计表格
        if (options.exportStatistics) {
            updateProgress(currentStep++, '生成统计表格...');
            
            const csvContent = generateStatisticsCSV(reportsToExport, options);
            const csvBlob = new Blob([csvContent], { 
                type: 'text/csv;charset=utf-8-sig' 
            });
            
            filesToDownload.push({
                name: `实验报告统计_${new Date().toISOString().split('T')[0]}.csv`,
                blob: csvBlob,
                type: 'statistics'
            });
            
            await new Promise(resolve => setTimeout(resolve, 300));
        }
        
        // 导出批阅汇总
        if (options.exportSummary) {
            updateProgress(currentStep++, '生成批阅汇总...');
            
            const summaryContent = generateSummaryReport(reportsToExport, options);
            const summaryBlob = new Blob([summaryContent], { type: 'text/html;charset=utf-8' });
            
            filesToDownload.push({
                name: `批阅汇总_${new Date().toISOString().split('T')[0]}.html`,
                blob: summaryBlob,
                type: 'summary'
            });
            
            await new Promise(resolve => setTimeout(resolve, 400));
        }
        
        // 下载文件
        if (options.createZip && filesToDownload.length > 1) {
            updateProgress(totalSteps, '打包文件...');
            await downloadAsZip(filesToDownload);
        } else {
            updateProgress(totalSteps, '下载文件...');
            filesToDownload.forEach(file => downloadFile(file.blob, file.name));
        }
        
        updateProgress(totalSteps, '导出完成！');
        
        // 显示完成按钮
        document.getElementById('cancelExportBtn').style.display = 'none';
        document.getElementById('completeExportBtn').style.display = 'inline-block';
        
        showNotification(`成功导出 ${reportsToExport.length} 份报告！`, 'success');
        
    } catch (error) {
        console.error('导出失败:', error);
        updateProgress(currentStep, '导出失败: ' + error.message);
        showNotification('导出失败，请重试', 'error');
    }
}

// 生成报告内容
function generateReportContent(report, options) {
    // 生成HTML格式的报告内容，更适合在浏览器中显示和打印
    let htmlContent = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>实验报告 - ${report.studentName}</title>
    <style>
        body { font-family: 'Microsoft YaHei', Arial, sans-serif; line-height: 1.6; margin: 40px; }
        .header { text-align: center; border-bottom: 2px solid #333; padding-bottom: 20px; margin-bottom: 30px; }
        .info-table { width: 100%; border-collapse: collapse; margin-bottom: 30px; }
        .info-table td { padding: 8px; border: 1px solid #ddd; }
        .info-table .label { background-color: #f5f5f5; font-weight: bold; width: 120px; }
        .section { margin-bottom: 30px; }
        .section h3 { color: #2C5AA0; border-left: 4px solid #2C5AA0; padding-left: 10px; }
        .score-section { background-color: #f9f9f9; padding: 15px; border-radius: 5px; }
        .feedback-section { background-color: #fff3cd; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107; }
        .content-section { background-color: #f8f9fa; padding: 20px; border-radius: 5px; min-height: 200px; }
        .footer { text-align: center; color: #666; font-size: 12px; margin-top: 40px; border-top: 1px solid #ddd; padding-top: 20px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>车路协同仿真教学平台</h1>
        <h2>实验报告</h2>
    </div>
    
    <table class="info-table">
        <tr>
            <td class="label">学生姓名</td>
            <td>${report.studentName}</td>
            <td class="label">班级</td>
            <td>${report.studentClass}</td>
        </tr>
        <tr>
            <td class="label">实验名称</td>
            <td colspan="3">${report.experimentName}</td>
        </tr>
        <tr>
            <td class="label">实验类型</td>
            <td>${report.experimentType}</td>
            <td class="label">提交时间</td>
            <td>${report.submitTime}</td>
        </tr>
        <tr>
            <td class="label">文件名称</td>
            <td>${report.fileName}</td>
            <td class="label">文件大小</td>
            <td>${report.fileSize}</td>
        </tr>
    </table>`;

    if (options.includeScores && report.score !== null) {
        htmlContent += `
    <div class="section">
        <h3>评分信息</h3>
        <div class="score-section">
            <p><strong>总分：</strong>${report.score}/100</p>
            <p><strong>批阅状态：</strong>${getStatusText(report.reviewStatus)}</p>
        </div>
    </div>`;
    }
    
    if (options.includeFeedback && report.feedback) {
        htmlContent += `
    <div class="section">
        <h3>批阅反馈</h3>
        <div class="feedback-section">
            <p>${report.feedback.replace(/\n/g, '<br>')}</p>
        </div>
    </div>`;
    }
    
    htmlContent += `
    <div class="section">
        <h3>报告正文</h3>
        <div class="content-section">
            <p><strong>原始文件：</strong>${report.fileName}</p>
            <p><strong>说明：</strong>这是演示版本的报告导出功能。在实际系统中，这里会显示学生上传的完整报告内容，包括：</p>
            <ul>
                <li>实验目的和要求</li>
                <li>实验原理和方法</li>
                <li>实验过程和步骤</li>
                <li>实验数据和结果</li>
                <li>数据分析和讨论</li>
                <li>实验结论和心得</li>
            </ul>
            <p>系统支持PDF、Word、图片等多种格式的报告文件，并能够在此处完整展示报告内容。</p>
        </div>
    </div>
    
    <div class="footer">
        <p>导出时间：${new Date().toLocaleString()}</p>
        <p>车路协同仿真教学平台 - 实验报告管理系统</p>
    </div>
</body>
</html>`;
    
    return htmlContent;
}

// 生成统计CSV
function generateStatisticsCSV(reportsToExport, options) {
    let headers = ['学生姓名', '班级', '实验名称', '实验类型', '提交时间', '文件名称', '文件大小', '批阅状态'];
    
    if (options.includeScores) {
        headers.push('成绩');
    }
    
    if (options.includeFeedback) {
        headers.push('批阅反馈');
    }
    
    // 添加BOM以支持中文字符
    let csvContent = '\uFEFF' + headers.join(',') + '\n';
    
    reportsToExport.forEach(report => {
        let row = [
            report.studentName || '',
            report.studentClass || '',
            report.experimentName || '',
            report.experimentType || '',
            report.submitTime || '',
            report.fileName || '',
            report.fileSize || '',
            getStatusText(report.reviewStatus) || ''
        ];
        
        if (options.includeScores) {
            row.push(report.score !== null ? report.score.toString() : '');
        }
        
        if (options.includeFeedback) {
            // 处理反馈中的换行符和引号
            const feedback = (report.feedback || '').replace(/"/g, '""').replace(/\n/g, ' ');
            row.push(feedback);
        }
        
        // 正确处理CSV字段，包含逗号或引号的字段需要用引号包围
        csvContent += row.map(field => {
            const fieldStr = String(field);
            if (fieldStr.includes(',') || fieldStr.includes('"') || fieldStr.includes('\n')) {
                return `"${fieldStr.replace(/"/g, '""')}"`;
            }
            return fieldStr;
        }).join(',') + '\n';
    });
    
    return csvContent;
}

// 生成汇总报告
function generateSummaryReport(reportsToExport, options) {
    // 统计信息
    const reviewedReports = reportsToExport.filter(r => r.reviewStatus === 'reviewed');
    const pendingReports = reportsToExport.filter(r => r.reviewStatus === 'pending');
    const reviewingReports = reportsToExport.filter(r => r.reviewStatus === 'reviewing');
    const avgScore = reviewedReports.length > 0 ? 
        (reviewedReports.reduce((sum, r) => sum + (r.score || 0), 0) / reviewedReports.length).toFixed(1) : 0;
    
    // 按实验类型统计
    const typeStats = {};
    reportsToExport.forEach(report => {
        if (!typeStats[report.experimentType]) {
            typeStats[report.experimentType] = { count: 0, totalScore: 0, reviewedCount: 0 };
        }
        typeStats[report.experimentType].count++;
        if (report.score !== null) {
            typeStats[report.experimentType].totalScore += report.score;
            typeStats[report.experimentType].reviewedCount++;
        }
    });
    
    // 按班级统计
    const classStats = {};
    reportsToExport.forEach(report => {
        if (!classStats[report.studentClass]) {
            classStats[report.studentClass] = { count: 0, totalScore: 0, reviewedCount: 0 };
        }
        classStats[report.studentClass].count++;
        if (report.score !== null) {
            classStats[report.studentClass].totalScore += report.score;
            classStats[report.studentClass].reviewedCount++;
        }
    });
    
    let htmlContent = `
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>实验报告批阅汇总</title>
    <style>
        body { font-family: 'Microsoft YaHei', Arial, sans-serif; line-height: 1.6; margin: 40px; }
        .header { text-align: center; border-bottom: 2px solid #2C5AA0; padding-bottom: 20px; margin-bottom: 30px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #2C5AA0; }
        .stat-number { font-size: 2em; font-weight: bold; color: #2C5AA0; }
        .stat-label { color: #666; font-size: 0.9em; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 30px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #2C5AA0; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .status-badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8em; }
        .status-reviewed { background-color: #d4edda; color: #155724; }
        .status-pending { background-color: #fff3cd; color: #856404; }
        .status-reviewing { background-color: #cce5ff; color: #004085; }
        .footer { text-align: center; color: #666; font-size: 12px; margin-top: 40px; border-top: 1px solid #ddd; padding-top: 20px; }
        .section { margin-bottom: 40px; }
        .section h3 { color: #2C5AA0; border-left: 4px solid #2C5AA0; padding-left: 10px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>车路协同仿真教学平台</h1>
        <h2>实验报告批阅汇总</h2>
        <p>生成时间: ${new Date().toLocaleString()}</p>
    </div>
    
    <div class="section">
        <h3>总体统计</h3>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">${reportsToExport.length}</div>
                <div class="stat-label">报告总数</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${reviewedReports.length}</div>
                <div class="stat-label">已批阅</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${pendingReports.length}</div>
                <div class="stat-label">待批阅</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">${avgScore}</div>
                <div class="stat-label">平均分</div>
            </div>
        </div>
    </div>
    
    <div class="section">
        <h3>实验类型统计</h3>
        <table>
            <thead>
                <tr>
                    <th>实验类型</th>
                    <th>报告数量</th>
                    <th>已批阅</th>
                    <th>平均分</th>
                </tr>
            </thead>
            <tbody>`;
    
    Object.entries(typeStats).forEach(([type, stats]) => {
        const avgTypeScore = stats.reviewedCount > 0 ? (stats.totalScore / stats.reviewedCount).toFixed(1) : '-';
        htmlContent += `
                <tr>
                    <td>${type}</td>
                    <td>${stats.count}</td>
                    <td>${stats.reviewedCount}</td>
                    <td>${avgTypeScore}</td>
                </tr>`;
    });
    
    htmlContent += `
            </tbody>
        </table>
    </div>
    
    <div class="section">
        <h3>班级统计</h3>
        <table>
            <thead>
                <tr>
                    <th>班级</th>
                    <th>报告数量</th>
                    <th>已批阅</th>
                    <th>平均分</th>
                </tr>
            </thead>
            <tbody>`;
    
    Object.entries(classStats).forEach(([className, stats]) => {
        const avgClassScore = stats.reviewedCount > 0 ? (stats.totalScore / stats.reviewedCount).toFixed(1) : '-';
        htmlContent += `
                <tr>
                    <td>${className}</td>
                    <td>${stats.count}</td>
                    <td>${stats.reviewedCount}</td>
                    <td>${avgClassScore}</td>
                </tr>`;
    });
    
    htmlContent += `
            </tbody>
        </table>
    </div>
    
    <div class="section">
        <h3>详细报告列表</h3>
        <table>
            <thead>
                <tr>
                    <th>序号</th>
                    <th>学生姓名</th>
                    <th>班级</th>
                    <th>实验名称</th>
                    <th>提交时间</th>
                    <th>批阅状态</th>
                    <th>成绩</th>
                </tr>
            </thead>
            <tbody>`;
    
    reportsToExport.forEach((report, index) => {
        const statusClass = report.reviewStatus.replace('_', '-');
        htmlContent += `
                <tr>
                    <td>${index + 1}</td>
                    <td>${report.studentName}</td>
                    <td>${report.studentClass}</td>
                    <td>${report.experimentName}</td>
                    <td>${report.submitTime}</td>
                    <td><span class="status-badge status-${statusClass}">${getStatusText(report.reviewStatus)}</span></td>
                    <td>${report.score !== null ? report.score + '/100' : '-'}</td>
                </tr>`;
    });
    
    htmlContent += `
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        <p>车路协同仿真教学平台 - 实验报告管理系统</p>
        <p>导出时间: ${new Date().toLocaleString()}</p>
    </div>
</body>
</html>`;
    
    return htmlContent;
}

// 下载单个文件
function downloadFile(blob, filename) {
    try {
        // 检查浏览器支持
        if (!window.URL || !window.URL.createObjectURL) {
            throw new Error('浏览器不支持文件下载功能');
        }
        
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.style.display = 'none';
        
        // 添加到DOM并触发点击
        document.body.appendChild(a);
        a.click();
        
        // 清理
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }, 100);
        
        console.log(`文件下载开始: ${filename}`);
        
    } catch (error) {
        console.error('文件下载失败:', error);
        showNotification(`文件下载失败: ${filename}`, 'error');
        
        // 备用方案：尝试使用window.open
        try {
            const url = URL.createObjectURL(blob);
            const newWindow = window.open(url, '_blank');
            if (!newWindow) {
                throw new Error('弹窗被阻止');
            }
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (fallbackError) {
            console.error('备用下载方案也失败:', fallbackError);
            showNotification('下载失败，请检查浏览器设置', 'error');
        }
    }
}

// 打包下载为ZIP
async function downloadAsZip(files) {
    try {
        // 检查JSZip是否可用
        if (typeof JSZip === 'undefined') {
            throw new Error('JSZip库未加载');
        }
        
        // 使用JSZip创建ZIP文件
        const zip = new JSZip();
        
        // 添加文件到ZIP
        files.forEach(file => {
            zip.file(file.name, file.blob);
        });
        
        // 生成ZIP文件
        const zipBlob = await zip.generateAsync({
            type: "blob",
            compression: "DEFLATE",
            compressionOptions: {
                level: 6
            }
        });
        
        // 下载ZIP文件
        const zipName = `实验报告导出_${new Date().toISOString().split('T')[0]}.zip`;
        downloadFile(zipBlob, zipName);
        
        showNotification('ZIP文件已生成并开始下载', 'success');
        
    } catch (error) {
        console.error('ZIP打包失败:', error);
        
        // 如果ZIP打包失败，回退到逐个下载
        showNotification('ZIP打包不可用，将逐个下载文件...', 'warning');
        
        // 逐个下载文件
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            setTimeout(() => {
                downloadFile(file.blob, file.name);
            }, i * 800); // 间隔800ms下载，避免浏览器阻止
        }
        
        showNotification(`正在下载 ${files.length} 个文件，请稍候...`, 'info');
    }
}

// 隐藏导出进度
function hideExportProgress() {
    const progressModal = document.getElementById('exportProgressModal');
    if (progressModal) {
        progressModal.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(progressModal);
        }, 300);
    }
}

// 取消导出
function cancelExport() {
    hideExportProgress();
    showNotification('导出已取消', 'info');
}

// 显示模板管理模态框
function showTemplateModal() {
    document.getElementById('templateModal').classList.add('show');
    
    document.getElementById('templateList').innerHTML = `
        <div style="text-align: center; color: #999; padding: 2rem;">
            <p>模板管理功能</p>
            <p>可以创建和管理实验报告模板</p>
        </div>
    `;
}

// 隐藏模板管理模态框
function hideTemplateModal() {
    document.getElementById('templateModal').classList.remove('show');
}

// 返回上一页
function handleBack() {
    // 优先尝试通过父窗口导航（iframe环境）
    if (window.parent && window.parent !== window && window.parent.navigateToTaskManagement) {
        console.log('通过父窗口导航返回教学任务管理');
        window.parent.navigateToTaskManagement();
    } 
    // 尝试通过顶层窗口导航
    else if (window.top && window.top !== window && window.top.navigateToTaskManagement) {
        console.log('通过顶层窗口导航返回教学任务管理');
        window.top.navigateToTaskManagement();
    }
    // 直接页面跳转（独立打开的情况）
    else {
        console.log('直接跳转到教学任务管理页面');
        window.location.href = '../1.1_教学任务管理/task_management.html';
    }
}

// 显示通知
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        z-index: 2000;
        animation: slideInRight 0.3s ease;
    `;
    
    const colors = {
        'success': '#67c23a',
        'error': '#f56c6c',
        'warning': '#e6a23c',
        'info': '#409EFF'
    };
    notification.style.backgroundColor = colors[type] || colors.info;
    
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            opacity: 0;
            transform: translateX(100%);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes slideOutRight {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
`;
document.head.appendChild(style);


// ========================================
// 通知和提示功能
// ========================================

// 显示通知消息
function showNotification(message, type = 'info') {
    // 移除旧的通知
    const oldNotification = document.querySelector('.notification-toast');
    if (oldNotification) {
        oldNotification.remove();
    }
    
    // 创建新通知
    const notification = document.createElement('div');
    notification.className = `notification-toast notification-${type}`;
    
    // 图标映射
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: 'ℹ️'
    };
    
    notification.innerHTML = `
        <span class="notification-icon">${icons[type] || icons.info}</span>
        <span class="notification-message">${message}</span>
    `;
    
    document.body.appendChild(notification);
    
    // 触发动画
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    // 3秒后自动移除
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 3000);
}

// 显示确认对话框
function showConfirmDialog(message, onConfirm, onCancel) {
    const dialog = document.createElement('div');
    dialog.className = 'confirm-dialog-overlay';
    dialog.innerHTML = `
        <div class="confirm-dialog">
            <div class="confirm-dialog-header">
                <span class="confirm-icon">❓</span>
                <h3>确认操作</h3>
            </div>
            <div class="confirm-dialog-body">
                <p>${message}</p>
            </div>
            <div class="confirm-dialog-footer">
                <button class="btn btn-secondary" id="confirmCancelBtn">取消</button>
                <button class="btn btn-primary" id="confirmOkBtn">确定</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(dialog);
    
    // 绑定事件
    document.getElementById('confirmOkBtn').addEventListener('click', () => {
        if (onConfirm) onConfirm();
        dialog.remove();
    });
    
    document.getElementById('confirmCancelBtn').addEventListener('click', () => {
        if (onCancel) onCancel();
        dialog.remove();
    });
    
    // 点击背景关闭
    dialog.addEventListener('click', (e) => {
        if (e.target === dialog) {
            if (onCancel) onCancel();
            dialog.remove();
        }
    });
}
