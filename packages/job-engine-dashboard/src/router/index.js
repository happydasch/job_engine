import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'dashboard',
    meta: { title: 'Dashboard' },
    component: () => import('../views/DashboardView.vue'),
  },
  {
    path: '/jobs',
    name: 'jobs',
    meta: { title: 'Jobs' },
    component: () => import('../views/JobsView.vue'),
  },
  {
    path: '/jobs/:id',
    name: 'job-detail',
    meta: { title: 'Job Detail' },
    component: () => import('../views/JobDetailView.vue'),
  },
  {
    path: '/companies',
    name: 'companies',
    meta: { title: 'Companies' },
    component: () => import('../views/CompaniesView.vue'),
  },
  {
    path: '/companies/:id',
    name: 'company-detail',
    meta: { title: 'Company Detail' },
    component: () => import('../views/CompanyDetailView.vue'),
  },
  {
    path: '/applications',
    name: 'applications',
    meta: { title: 'Applications' },
    component: () => import('../views/ApplicationsView.vue'),
  },
  {
    path: '/scrapers',
    name: 'scrapers',
    meta: { title: 'Scrapers' },
    component: () => import('../views/ScrapersView.vue'),
  },
  {
    path: '/skills',
    name: 'skills',
    meta: { title: 'Skills' },
    component: () => import('../views/SkillsView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  const base = 'Job Engine'
  const page = to.meta?.title
  document.title = page ? `${base} — ${page}` : base
})

export default router