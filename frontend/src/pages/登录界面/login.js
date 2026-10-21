/**
 * 登录页面JavaScript
 * 调用后端API进行认证
 */

const API_BASE = '/api/v1';

document.addEventListener('DOMContentLoaded', function () {
    const loginForm = document.getElementById('loginForm');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const roleSelect = document.getElementById('role');
    const loginButton = loginForm.querySelector('.login-button');
    const buttonText = loginButton.querySelector('.button-text');
    const statusText = document.getElementById('statusText');
    const statusDot = document.getElementById('statusDot');

    // 局域网教学模式默认使用公共学生账号，仍允许教师/管理员手动改填。
    if (!usernameInput.value) usernameInput.value = 'student';
    if (!passwordInput.value) passwordInput.value = '123456';
    if (roleSelect && !roleSelect.value) roleSelect.value = 'student';

    // 检查是否已登录
    checkLoginStatus();

    // 表单提交事件
    loginForm.addEventListener('submit', handleLogin);

    function checkLoginStatus() {
        const userRole = localStorage.getItem('userRole');
        const username = localStorage.getItem('username');
        if (userRole && username) {
            redirectToHome(userRole);
        }
    }

    async function handleLogin(e) {
        e.preventDefault();

        const username = usernameInput.value.trim();
        const password = passwordInput.value.trim();
        const role = roleSelect.value;

        if (!username || !password) {
            showStatus('请输入用户名和密码', 'error');
            return;
        }

        setButtonLoading(true);

        try {
            // 调用后端JSON登录接口
            const resp = await fetch(API_BASE + '/auth/login/json', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username, password: password })
            });

            if (!resp.ok) {
                const err = await resp.json().catch(function () { return null; });
                throw new Error((err && err.detail && err.detail.message) || '用户名或密码错误');
            }

            const data = await resp.json();
            const token = data.access_token;

            // 用token获取用户信息，验证角色
            const meResp = await fetch(API_BASE + '/auth/me', {
                headers: { 'Authorization': 'Bearer ' + token }
            });

            if (!meResp.ok) {
                throw new Error('获取用户信息失败');
            }

            const user = await meResp.json();

            // 如果用户选择了角色，验证是否匹配；如果没选，使用后端返回的角色
            var actualRole = user.role;
            if (role && role !== actualRole) {
                throw new Error('所选角色与账号角色不匹配');
            }

            // 保存登录信息
            localStorage.setItem('username', user.username);
            localStorage.setItem('userRole', actualRole);
            localStorage.setItem('token', token);
            localStorage.setItem('loginTime', new Date().toISOString());

            showStatus('登录成功！正在跳转...', 'success');

            // 直接跳转，不用 alert 阻塞
            setTimeout(function () { redirectToHome(actualRole); }, 600);

        } catch (error) {
            showStatus(error.message || '登录失败，请检查后端服务是否启动', 'error');
            setButtonLoading(false);
            addErrorAnimation();
        }
    }

    function setButtonLoading(loading) {
        loginButton.disabled = loading;
        buttonText.textContent = loading ? '登录中...' : '登录系统';
    }

    function showStatus(message, type) {
        if (statusText && statusDot) {
            statusText.textContent = message;
            if (type === 'error') {
                statusDot.style.background = '#dc3545';
                statusText.style.color = '#dc3545';
            } else if (type === 'success') {
                statusDot.style.background = '#28a745';
                statusText.style.color = '#28a745';
            }
        }
    }

    function addErrorAnimation() {
        document.querySelectorAll('.input-container').forEach(function (c) {
            c.classList.add('error');
            setTimeout(function () { c.classList.remove('error'); }, 500);
        });
    }

    function redirectToHome(role) {
        if (role === 'student') {
            window.location.href = '/student.html';
        } else if (role === 'teacher') {
            window.location.href = '/teacher.html';
        } else if (role === 'admin') {
            window.location.href = '/admin.html';
        } else {
            window.location.href = '/student.html';
        }
    }

    // 回车键登录
    [usernameInput, passwordInput, roleSelect].forEach(function (input) {
        input.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                loginForm.dispatchEvent(new Event('submit'));
            }
        });
    });
});
