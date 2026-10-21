import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
  },
  // 管理员模块
  {
    path: '/',
    component: () => import('@/layouts/AdminLayout.vue'),
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue') },
      { path: 'orgs', name: 'Orgs', component: () => import('@/views/Orgs/OrgList.vue') },
      { path: 'orgs/:id', name: 'OrgDetail', component: () => import('@/views/Orgs/OrgDetail.vue') },
      { path: 'licenses', name: 'Licenses', component: () => import('@/views/Licenses/LicenseList.vue') },
      { path: 'users', name: 'Users', component: () => import('@/views/Users/UserList.vue') },
      { path: 'password-requests', name: 'PasswordRequests', component: () => import('@/views/Users/PasswordRequests.vue') },
      { path: 'analytics', name: 'Analytics', component: () => import('@/views/Analytics/AnalyticsView.vue') },
      { path: 'updates', name: 'Updates', component: () => import('@/views/Updates/UpdateList.vue') },
    ],
  },
  // 教师模块
  {
    path: '/teacher',
    component: () => import('@/layouts/TeacherLayout.vue'),
    children: [
      { path: '', redirect: '/teacher/classes' },
      { path: 'classes', name: 'TeacherClasses', component: () => import('@/views/Teacher/TeacherClasses.vue') },
      { path: 'tasks', name: 'TeacherTasks', component: () => import('@/views/Teacher/TeacherTasks.vue') },
      { path: 'messages', name: 'TeacherMessages', component: () => import('@/views/Teacher/TeacherMessages.vue') },
      { path: 'reports', name: 'TeacherReports', component: () => import('@/views/Teacher/TeacherReports.vue') },
      { path: 'self-algorithms', name: 'TeacherSelfAlgorithms', component: () => import('@/views/Teacher/TeacherSelfAlgorithms.vue') },
      { path: 'analytics', name: 'TeacherAnalytics', component: () => import('@/views/Teacher/TeacherAnalytics.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.path === '/') {
    return { name: 'Login' }
  }
  const token = localStorage.getItem('access_token')
  if (!to.meta.public && !token) {
    return { name: 'Login' }
  }
  const user = JSON.parse(localStorage.getItem('user') || 'null')
  if (token && user) {
    if (user.role === 'student') {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
      return { name: 'Login' }
    }
    if (to.path.startsWith('/teacher') && user.role !== 'teacher') return '/dashboard'
    if (!to.path.startsWith('/teacher') && !to.meta.public && user.role === 'teacher') return '/teacher/classes'
  }
})

export default router
