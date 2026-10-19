// 学生信息管理模块JavaScript交互功能

// 全局变量
let students = [];
let filteredStudents = [];
let currentPage = 1;
let pageSize = 20;
let sortField = '';
let sortDirection = 'asc';
let selectedStudents = [];

// 模拟学生数据
const mockStudents = [
    {
        id: 1,
        studentId: "2021001",
        name: "张三",
        class: "交通工程2021级",
        major: "交通工程",
        phone: "13800138001",
        email: "zhangsan@example.com",
        enrollmentYear: 2021,
        completedTasks: 4,
        totalTasks: 6,
        averageScore: 88.5,
        lastLoginTime: "2024-12-20 14:30:00",
        status: "active"
    },
    {
        id: 2,
        studentId: "2021002",
        name: "李四",
        class: "交通工程2021级",
        major: "交通工程",
        phone: "13800138002",
        email: "lisi@example.com",
        enrollmentYear: 2021,
        completedTasks: 3,
        totalTasks: 6,
        averageScore: 82.3,
        lastLoginTime: "2024-12-19 16:45:00",
        status: "active"
    },
    {
        id: 3,
        studentId: "2022001",
        name: "王五",
        class: "智能交通2022级",
        major: "智能交通",
        phone: "13800138003",
        email: "wangwu@example.com",
        enrollmentYear: 2022,
        completedTasks: 5,
        totalTasks: 5,
        averageScore: 92.1,
        lastLoginTime: "2024-12-21 09:15:00",
        status: "active"
    },
    {
        id: 4,
        studentId: "2022002",
        name: "赵六",
        class: "智能交通2022级",
        major: "智能交通",
        phone: "13800138004",
        email: "zhaoliu@example.com",
        enrollmentYear: 2022,
        completedTasks: 2,
        totalTasks: 5,
        averageScore: 75.8,
        lastLoginTime: "2024-12-18 11:20:00",
        status: "active"
    },
    {
        id: 5,
        studentId: "2023001",
        name: "孙七",
        class: "交通运输2023级",
        major: "交通运输",
        phone: "13800138005",
        email: "sunqi@example.com",
        enrollmentYear: 2023,
        completedTasks: 1,
        totalTasks: 4,
        averageScore: 68.9,
        lastLoginTime: "2024-12-17 13:30:00",
        status: "active"
    }
];

// DOM元素
const elements = {
    // 按钮
    addStudentBtn: document.getElementById('addStudentBtn'),
    importBtn: document.getElementById('importBtn'),
    exportBtn: document.getElementById('exportBtn'),
    backBtn: document.getElementById('backBtn'),
    
    // 统计数据
    totalStudents: document.getElementById('totalStudents'),
    activeStudents: document.getElementById('activeStudents'),
    averageScore: document.getElementById('averageScore'),
    completionRate: document.getElementById('completionRate'),
    
    // 筛选器
    classFilter: document.getElementById('classFilter'),
    majorFilter: document.getElementById('majorFilter'),
    yearFilter: document.getElementById('yearFilter'),
    searchInput: document.getElementById('searchInput'),
    
    // 表格相关
    studentTable: document.getElementById('studentTable'),
    studentTableBody: document.getElementById('studentTableBody'),
    selectAllCheckbox: document.getElementById('selectAllCheckbox'),
    selectAllBtn: document.getElementById('selectAllBtn'),
    batchDeleteBtn: document.getElementById('batchDeleteBtn'),
    selectedCount: document.getElementById('selectedCount'),
    
    // 分页
    pagination: document.getElementById('pagination'),
    prevPageBtn: document.getElementById('prevPageBtn'),
    nextPageBtn: document.getElementById('nextPageBtn'),
    pageNumbers: document.getElementById('pageNumbers'),
    pageSizeSelect: document.getElementById('pageSizeSelect'),
    
    // 模态框
    addStudentModal: document.getElementById('addStudentModal'),
    editStudentModal: document.getElementById('editStudentModal'),
    studentDetailModal: document.getElementById('studentDetailModal'),
    importModal: document.getElementById('importModal'),
    
    // 表单
    addStudentForm: document.getElementById('addStudentForm'),
    editStudentForm: document.getElementById('editStudentForm'),
    studentDetail: document.getElementById('studentDetail'),
    
    // 文件上传
    uploadZone: document.getElementById('uploadZone'),
    fileInput: document.getElementById('fileInput')
};

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    // 检查用户权限
    const userRole = localStorage.getItem('userRole');
    if (userRole === 'student') {
        showPermissionDeniedPage();
        return;
    }
    
    students = [...mockStudents];
    filteredStudents = [...students];
    
    initializeEventListeners();
    updateClassFilter();
    updateStatistics();
    renderStudentTable();
    renderPagination();
});

// 事件监听器初始化
function initializeEventListeners() {
    // 主要按钮事件
    elements.addStudentBtn.addEventListener('click', showAddStudentModal);
    elements.importBtn.addEventListener('click', showImportModal);
    elements.exportBtn.addEventListener('click', exportStudentData);
    elements.backBtn.addEventListener('click', handleBack);
    
    // 筛选器事件
    elements.classFilter.addEventListener('change', applyFilters);
    elements.majorFilter.addEventListener('change', applyFilters);
    elements.yearFilter.addEventListener('change', applyFilters);
    elements.searchInput.addEventListener('input', debounce(applyFilters, 300));
    
    // 表格事件
    elements.selectAllCheckbox.addEventListener('change', handleSelectAll);
    elements.selectAllBtn.addEventListener('click', handleSelectAll);
    elements.batchDeleteBtn.addEventListener('click', handleBatchDelete);
    
    // 分页事件
    elements.prevPageBtn.addEventListener('click', () => changePage(currentPage - 1));
    elements.nextPageBtn.addEventListener('click', () => changePage(currentPage + 1));
    elements.pageSizeSelect.addEventListener('change', handlePageSizeChange);
    
    // 表格排序事件
    document.querySelectorAll('.sortable').forEach(th => {
        th.addEventListener('click', () => handleSort(th.dataset.sort));
    });
    
    // 模态框事件
    setupModalEvents();
    
    // 表单提交事件
    elements.addStudentForm.addEventListener('submit', handleAddStudent);
    elements.editStudentForm.addEventListener('submit', handleEditStudent);
    
    // 文件上传事件
    setupFileUploadEvents();
}

// 模态框事件设置
function setupModalEvents() {
    // 添加学生模态框
    document.getElementById('closeAddModal').addEventListener('click', hideAddStudentModal);
    document.getElementById('cancelAddBtn').addEventListener('click', hideAddStudentModal);
    document.getElementById('confirmAddBtn').addEventListener('click', handleAddStudent);
    
    // 编辑学生模态框
    document.getElementById('closeEditModal').addEventListener('click', hideEditStudentModal);
    document.getElementById('cancelEditBtn').addEventListener('click', hideEditStudentModal);
    document.getElementById('confirmEditBtn').addEventListener('click', handleEditStudent);
    
    // 学生详情模态框
    document.getElementById('closeDetailModal').addEventListener('click', hideStudentDetailModal);
    document.getElementById('closeDetailBtn').addEventListener('click', hideStudentDetailModal);
    
    // 导入模态框
    document.getElementById('closeImportModal').addEventListener('click', hideImportModal);
    document.getElementById('cancelImportBtn').addEventListener('click', hideImportModal);
    document.getElementById('confirmImportBtn').addEventListener('click', handleImport);
    document.getElementById('downloadTemplate').addEventListener('click', downloadTemplate);
    
    // 点击模态框背景关闭
    [elements.addStudentModal, elements.editStudentModal, elements.studentDetailModal, elements.importModal].forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('show');
            }
        });
    });
}

// 文件上传事件设置
function setupFileUploadEvents() {
    elements.uploadZone.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileSelect);
    
    // 拖拽上传
    elements.uploadZone.addEventListener('dragover', handleDragOver);
    elements.uploadZone.addEventListener('dragleave', handleDragLeave);
    elements.uploadZone.addEventListener('drop', handleFileDrop);
}

// 显示添加学生模态框
function showAddStudentModal() {
    elements.addStudentModal.classList.add('show');
    elements.addStudentForm.reset();
}

// 隐藏添加学生模态框
function hideAddStudentModal() {
    elements.addStudentModal.classList.remove('show');
}

// 处理添加学生
function handleAddStudent(e) {
    e.preventDefault();
    
    const formData = new FormData(elements.addStudentForm);
    const studentData = {
        id: students.length + 1,
        studentId: formData.get('studentId'),
        name: formData.get('name'),
        class: formData.get('class'),
        major: formData.get('major'),
        phone: formData.get('phone') || '',
        email: formData.get('email') || '',
        enrollmentYear: parseInt(formData.get('enrollmentYear')),
        completedTasks: 0,
        totalTasks: 0,
        averageScore: 0,
        lastLoginTime: '',
        status: 'active'
    };
    
    // 验证学号唯一性
    if (students.some(s => s.studentId === studentData.studentId)) {
        showNotification('学号已存在，请使用其他学号', 'error');
        return;
    }
    
    students.push(studentData);
    applyFilters();
    updateStatistics();
    updateClassFilter();
    hideAddStudentModal();
    
    showNotification('学生添加成功！', 'success');
}

// 显示编辑学生模态框
function showEditStudentModal(studentId) {
    const student = students.find(s => s.id === studentId);
    if (!student) return;
    
    // 填充表单数据
    document.getElementById('editStudentId').value = student.id;
    document.getElementById('editStudentNumber').value = student.studentId;
    document.getElementById('editStudentName').value = student.name;
    document.getElementById('editStudentClass').value = student.class;
    document.getElementById('editStudentMajor').value = student.major;
    document.getElementById('editStudentPhone').value = student.phone;
    document.getElementById('editStudentEmail').value = student.email;
    document.getElementById('editEnrollmentYear').value = student.enrollmentYear;
    
    elements.editStudentModal.classList.add('show');
}

// 隐藏编辑学生模态框
function hideEditStudentModal() {
    elements.editStudentModal.classList.remove('show');
}

// 处理编辑学生
function handleEditStudent(e) {
    e.preventDefault();
    
    const formData = new FormData(elements.editStudentForm);
    const studentId = parseInt(formData.get('id'));
    const studentIndex = students.findIndex(s => s.id === studentId);
    
    if (studentIndex === -1) return;
    
    // 检查学号唯一性（排除当前学生）
    const newStudentId = formData.get('studentId');
    if (students.some(s => s.studentId === newStudentId && s.id !== studentId)) {
        showNotification('学号已存在，请使用其他学号', 'error');
        return;
    }
    
    // 更新学生信息
    students[studentIndex] = {
        ...students[studentIndex],
        studentId: newStudentId,
        name: formData.get('name'),
        class: formData.get('class'),
        major: formData.get('major'),
        phone: formData.get('phone') || '',
        email: formData.get('email') || '',
        enrollmentYear: parseInt(formData.get('enrollmentYear'))
    };
    
    applyFilters();
    updateStatistics();
    updateClassFilter();
    hideEditStudentModal();
    
    showNotification('学生信息更新成功！', 'success');
}

// 显示学生详情模态框
function showStudentDetailModal(studentId) {
    const student = students.find(s => s.id === studentId);
    if (!student) return;
    
    const completionRate = student.totalTasks > 0 ? Math.round(student.completedTasks / student.totalTasks * 100) : 0;
    
    elements.studentDetail.innerHTML = `
        <div class="detail-section">
            <h4>基本信息</h4>
            <div class="detail-item">
                <span class="detail-label">学号</span>
                <span class="detail-value">${student.studentId}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">姓名</span>
                <span class="detail-value">${student.name}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">班级</span>
                <span class="detail-value">${student.class}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">专业</span>
                <span class="detail-value">${student.major}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">入学年份</span>
                <span class="detail-value">${student.enrollmentYear}</span>
            </div>
        </div>
        <div class="detail-section">
            <h4>联系方式</h4>
            <div class="detail-item">
                <span class="detail-label">手机号码</span>
                <span class="detail-value">${student.phone || '未填写'}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">邮箱地址</span>
                <span class="detail-value">${student.email || '未填写'}</span>
            </div>
        </div>
        <div class="detail-section">
            <h4>学习情况</h4>
            <div class="detail-item">
                <span class="detail-label">完成任务</span>
                <span class="detail-value">${student.completedTasks}/${student.totalTasks}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">完成率</span>
                <span class="detail-value">${completionRate}%</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">平均成绩</span>
                <span class="detail-value">${student.averageScore.toFixed(1)}分</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">最后登录</span>
                <span class="detail-value">${student.lastLoginTime || '从未登录'}</span>
            </div>
        </div>
    `;
    
    elements.studentDetailModal.classList.add('show');
}

// 隐藏学生详情模态框
function hideStudentDetailModal() {
    elements.studentDetailModal.classList.remove('show');
}

// 删除学生
function deleteStudent(studentId) {
    if (confirm('确定要删除这名学生吗？此操作不可撤销。')) {
        const index = students.findIndex(s => s.id === studentId);
        if (index !== -1) {
            students.splice(index, 1);
            applyFilters();
            updateStatistics();
            updateClassFilter();
            showNotification('学生删除成功！', 'success');
        }
    }
}

// 处理全选
function handleSelectAll() {
    const isChecked = elements.selectAllCheckbox.checked;
    const checkboxes = document.querySelectorAll('#studentTableBody input[type="checkbox"]');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = isChecked;
    });
    
    updateSelectedStudents();
}

// 更新选中的学生
function updateSelectedStudents() {
    const checkboxes = document.querySelectorAll('#studentTableBody input[type="checkbox"]:checked');
    selectedStudents = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    elements.selectedCount.textContent = selectedStudents.length;
    elements.batchDeleteBtn.disabled = selectedStudents.length === 0;
    
    // 更新全选状态
    const totalCheckboxes = document.querySelectorAll('#studentTableBody input[type="checkbox"]').length;
    elements.selectAllCheckbox.checked = selectedStudents.length === totalCheckboxes && totalCheckboxes > 0;
    elements.selectAllCheckbox.indeterminate = selectedStudents.length > 0 && selectedStudents.length < totalCheckboxes;
}

// 批量删除
function handleBatchDelete() {
    if (selectedStudents.length === 0) return;
    
    if (confirm(`确定要删除选中的 ${selectedStudents.length} 名学生吗？此操作不可撤销。`)) {
        students = students.filter(s => !selectedStudents.includes(s.id));
        selectedStudents = [];
        applyFilters();
        updateStatistics();
        updateClassFilter();
        showNotification(`成功删除 ${selectedStudents.length} 名学生！`, 'success');
    }
}

// 应用筛选条件
function applyFilters() {
    const classFilter = elements.classFilter.value;
    const majorFilter = elements.majorFilter.value;
    const yearFilter = elements.yearFilter.value;
    const searchText = elements.searchInput.value.toLowerCase().trim();
    
    filteredStudents = students.filter(student => {
        const classMatch = classFilter === 'all' || student.class === classFilter;
        const majorMatch = majorFilter === 'all' || student.major === majorFilter;
        const yearMatch = yearFilter === 'all' || student.enrollmentYear.toString() === yearFilter;
        const searchMatch = !searchText || 
            student.name.toLowerCase().includes(searchText) ||
            student.studentId.toLowerCase().includes(searchText);
        
        return classMatch && majorMatch && yearMatch && searchMatch;
    });
    
    currentPage = 1;
    renderStudentTable();
    renderPagination();
}

// 处理排序
function handleSort(field) {
    if (sortField === field) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortField = field;
        sortDirection = 'asc';
    }
    
    // 更新排序图标
    document.querySelectorAll('.sortable').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
    });
    
    const currentTh = document.querySelector(`[data-sort="${field}"]`);
    currentTh.classList.add(`sort-${sortDirection}`);
    
    // 排序数据
    filteredStudents.sort((a, b) => {
        let aVal = a[field];
        let bVal = b[field];
        
        if (typeof aVal === 'string') {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
        }
        
        if (sortDirection === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    });
    
    renderStudentTable();
}

// 渲染学生表格
function renderStudentTable() {
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = startIndex + pageSize;
    const pageStudents = filteredStudents.slice(startIndex, endIndex);
    
    const tableHTML = pageStudents.map(student => {
        const completionRate = student.totalTasks > 0 ? Math.round(student.completedTasks / student.totalTasks * 100) : 0;
        return `
            <tr>
                <td><input type="checkbox" value="${student.id}" onchange="updateSelectedStudents()"></td>
                <td>${student.studentId}</td>
                <td>${student.name}</td>
                <td>${student.class}</td>
                <td>${student.major}</td>
                <td>${student.phone || '-'}</td>
                <td>${student.completedTasks}/${student.totalTasks} (${completionRate}%)</td>
                <td>${student.averageScore.toFixed(1)}</td>
                <td>${student.lastLoginTime || '从未登录'}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn btn-sm btn-info" onclick="showStudentDetailModal(${student.id})">详情</button>
                        <button class="btn btn-sm btn-primary" onclick="showEditStudentModal(${student.id})">编辑</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteStudent(${student.id})">删除</button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
    
    elements.studentTableBody.innerHTML = tableHTML || '<tr><td colspan="10" style="text-align: center; color: #999; padding: 2rem;">暂无学生数据</td></tr>';
    
    // 重置选择状态
    selectedStudents = [];
    updateSelectedStudents();
}

// 渲染分页
function renderPagination() {
    const totalPages = Math.ceil(filteredStudents.length / pageSize);
    
    // 更新按钮状态
    elements.prevPageBtn.disabled = currentPage <= 1;
    elements.nextPageBtn.disabled = currentPage >= totalPages;
    
    // 生成页码
    let pageNumbersHTML = '';
    const maxVisiblePages = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    
    if (endPage - startPage < maxVisiblePages - 1) {
        startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }
    
    for (let i = startPage; i <= endPage; i++) {
        pageNumbersHTML += `
            <button class="page-number ${i === currentPage ? 'active' : ''}" onclick="changePage(${i})">
                ${i}
            </button>
        `;
    }
    
    elements.pageNumbers.innerHTML = pageNumbersHTML;
}

// 切换页面
function changePage(page) {
    const totalPages = Math.ceil(filteredStudents.length / pageSize);
    if (page < 1 || page > totalPages) return;
    
    currentPage = page;
    renderStudentTable();
    renderPagination();
}

// 处理每页条数变化
function handlePageSizeChange() {
    pageSize = parseInt(elements.pageSizeSelect.value);
    currentPage = 1;
    renderStudentTable();
    renderPagination();
}

// 更新班级筛选器
function updateClassFilter() {
    const classes = [...new Set(students.map(s => s.class))].sort();
    const currentValue = elements.classFilter.value;
    
    elements.classFilter.innerHTML = '<option value="all">全部班级</option>' +
        classes.map(cls => `<option value="${cls}">${cls}</option>`).join('');
    
    if (classes.includes(currentValue)) {
        elements.classFilter.value = currentValue;
    }
}

// 更新统计数据
function updateStatistics() {
    const total = students.length;
    const active = students.filter(s => s.status === 'active').length;
    const totalScore = students.reduce((sum, s) => sum + s.averageScore, 0);
    const avgScore = total > 0 ? (totalScore / total).toFixed(1) : 0;
    const totalTasks = students.reduce((sum, s) => sum + s.totalTasks, 0);
    const completedTasks = students.reduce((sum, s) => sum + s.completedTasks, 0);
    const completionRate = totalTasks > 0 ? Math.round(completedTasks / totalTasks * 100) : 0;
    
    elements.totalStudents.textContent = total;
    elements.activeStudents.textContent = active;
    elements.averageScore.textContent = avgScore;
    elements.completionRate.textContent = completionRate + '%';
}

// 显示导入模态框
function showImportModal() {
    elements.importModal.classList.add('show');
}

// 隐藏导入模态框
function hideImportModal() {
    elements.importModal.classList.remove('show');
    elements.fileInput.value = '';
    document.getElementById('confirmImportBtn').disabled = true;
}

// 处理文件选择
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        validateFile(file);
    }
}

// 处理拖拽
function handleDragOver(e) {
    e.preventDefault();
    elements.uploadZone.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    elements.uploadZone.classList.remove('dragover');
}

function handleFileDrop(e) {
    e.preventDefault();
    elements.uploadZone.classList.remove('dragover');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        validateFile(files[0]);
    }
}

// 验证文件
function validateFile(file) {
    const validTypes = ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel'];
    
    if (!validTypes.includes(file.type)) {
        showNotification('请选择Excel文件（.xlsx或.xls格式）', 'error');
        return;
    }
    
    if (file.size > 5 * 1024 * 1024) { // 5MB
        showNotification('文件大小不能超过5MB', 'error');
        return;
    }
    
    document.getElementById('confirmImportBtn').disabled = false;
    showNotification('文件验证通过，可以开始导入', 'success');
}

// 处理导入
function handleImport() {
    // 模拟导入过程
    showNotification('正在导入数据...', 'info');
    
    setTimeout(() => {
        // 模拟添加一些学生数据
        const newStudents = [
            {
                id: students.length + 1,
                studentId: "2024001",
                name: "导入学生1",
                class: "交通工程2024级",
                major: "交通工程",
                phone: "13800138010",
                email: "import1@example.com",
                enrollmentYear: 2024,
                completedTasks: 0,
                totalTasks: 0,
                averageScore: 0,
                lastLoginTime: '',
                status: 'active'
            }
        ];
        
        students.push(...newStudents);
        applyFilters();
        updateStatistics();
        updateClassFilter();
        hideImportModal();
        
        showNotification(`成功导入 ${newStudents.length} 名学生！`, 'success');
    }, 2000);
}

// 下载模板
function downloadTemplate(e) {
    e.preventDefault();
    
    const templateData = `学号,姓名,班级,专业,联系电话,邮箱,入学年份
2024001,李明,交通工程2024级1班,交通工程,13800138000,student@dlut.edu.cn,2024`;
    
    const blob = new Blob([templateData], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '学生信息导入模板.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showNotification('模板下载成功！', 'success');
}

// 导出学生数据
function exportStudentData() {
    const csvContent = '学号,姓名,班级,专业,联系电话,邮箱,入学年份,完成任务,总任务,平均成绩,最后登录\n' +
        students.map(s => `${s.studentId},${s.name},${s.class},${s.major},${s.phone},${s.email},${s.enrollmentYear},${s.completedTasks},${s.totalTasks},${s.averageScore},${s.lastLoginTime}`).join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `学生信息_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showNotification('数据导出成功！', 'success');
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

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
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
//
 显示权限拒绝页面
function showPermissionDeniedPage() {
    document.body.innerHTML = `
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            font-family: 'Microsoft YaHei', sans-serif;
            text-align: center;
            padding: 2rem;
        ">
            <div style="
                background: white;
                border-radius: 12px;
                padding: 3rem;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
                max-width: 500px;
                width: 100%;
            ">
                <div style="font-size: 4rem; color: #f56c6c; margin-bottom: 1.5rem;">🚫</div>
                <h1 style="color: #333; margin-bottom: 1rem; font-size: 1.8rem;">访问受限</h1>
                <p style="color: #666; margin-bottom: 2rem; line-height: 1.6; font-size: 1.1rem;">
                    抱歉，您没有访问该功能的权限。<br>
                    学生信息管理功能仅限教师和管理员使用。
                </p>
                <div style="display: flex; gap: 1rem; justify-content: center;">
                    <button onclick="goBack()" style="
                        background: #2C5AA0;
                        color: white;
                        border: none;
                        padding: 0.75rem 2rem;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 1rem;
                        font-weight: 500;
                        transition: background-color 0.3s ease;
                    " onmouseover="this.style.backgroundColor='#1e3f73'" 
                       onmouseout="this.style.backgroundColor='#2C5AA0'">
                        返回上一页
                    </button>
                    <button onclick="goToStudentHome()" style="
                        background: #28a745;
                        color: white;
                        border: none;
                        padding: 0.75rem 2rem;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 1rem;
                        font-weight: 500;
                        transition: background-color 0.3s ease;
                    " onmouseover="this.style.backgroundColor='#1e7e34'" 
                       onmouseout="this.style.backgroundColor='#28a745'">
                        返回学生首页
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // 添加全局函数
    window.goBack = function() {
        history.back();
    };
    
    window.goToStudentHome = function() {
        window.location.href = '../../student.html';
    };
}
