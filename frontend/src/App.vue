<script setup>
import { computed, onMounted, provide, ref, watch } from 'vue'
import Icon from './components/Icon.vue'
import { useHashRoute } from './router.js'
import CampaignsView from './views/CampaignsView.vue'
import CategoriesView from './views/CategoriesView.vue'
import CustomersView from './views/CustomersView.vue'
import DashboardView from './views/DashboardView.vue'
import OrderDetailView from './views/OrderDetailView.vue'
import OrdersView from './views/OrdersView.vue'
import PaymentsView from './views/PaymentsView.vue'
import ProductsView from './views/ProductsView.vue'
import SettingsView from './views/SettingsView.vue'

const API_BASE = import.meta.env.VITE_API_BASE || (location.port === '5174' ? 'http://127.0.0.1:8001' : '')
const key = ref(sessionStorage.getItem('adminKey') || '')
const authenticated = ref(false)
const loading = ref(false)
const error = ref('')
const pendingCount = ref(0)
const { route, go } = useHashRoute()

const nav = [
  { name: 'dashboard', label: '概览', icon: 'dashboard' },
  { name: 'orders', label: '订单', icon: 'orders' },
  { name: 'payments', label: '付款核验', icon: 'payments' },
  { name: 'products', label: '商品', icon: 'products' },
  { name: 'categories', label: '分类', icon: 'categories' },
  { name: 'customers', label: '客户', icon: 'customers' },
  { name: 'campaigns', label: '来源链接', icon: 'campaigns' },
  { name: 'settings', label: '设置', icon: 'settings' },
]

const titles = {
  dashboard: '概览',
  orders: '订单',
  payments: '付款核验',
  products: '商品',
  categories: '分类',
  customers: '客户',
  campaigns: '来源链接',
  settings: '设置',
}

const pageTitle = computed(() => (route.value.name === 'orders' && route.value.id ? '订单详情' : titles[route.value.name]))

function formatError(detail, status) {
  if (Array.isArray(detail)) return detail.map((item) => item.msg || '输入无效').join('；')
  if (typeof detail === 'string') return detail
  return `请求失败：${status}`
}

async function request(path, options = {}) {
  const headers = { 'X-Admin-Key': key.value }
  if (options.body) headers['Content-Type'] = 'application/json'
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) },
  })
  if (response.status === 401) {
    authenticated.value = false
    sessionStorage.removeItem('adminKey')
    throw new Error('管理密钥无效')
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(formatError(data.detail, response.status))
  }
  if (response.status === 204) return { data: null, total: null }
  const data = await response.json()
  const totalHeader = response.headers.get('X-Total-Count')
  return { data, total: totalHeader == null ? null : Number(totalHeader) }
}

async function refreshPending() {
  try {
    const { data } = await request('/api/admin/payments/pending')
    pendingCount.value = data.length
  } catch {
    pendingCount.value = 0
  }
}

async function login() {
  loading.value = true
  error.value = ''
  try {
    await request('/api/admin/dashboard')
    authenticated.value = true
    sessionStorage.setItem('adminKey', key.value)
    if (!location.hash || location.hash === '#') go('dashboard')
    await refreshPending()
  } catch (err) {
    error.value = err.message
    authenticated.value = false
  } finally {
    loading.value = false
  }
}

function logout() {
  sessionStorage.removeItem('adminKey')
  key.value = ''
  authenticated.value = false
  pendingCount.value = 0
}

provide('request', request)
provide('go', go)
provide('refreshPending', refreshPending)

watch(() => route.value.name, () => {
  if (authenticated.value) refreshPending()
})

onMounted(() => {
  if (key.value) login()
})
</script>

<template>
  <main v-if="!authenticated" class="login-screen">
    <form class="login-card" @submit.prevent="login">
      <div class="brand-mark">店</div>
      <h1>商店管理后台</h1>
      <p>使用管理密钥登录。密钥通过请求头 X-Admin-Key 发送，只保存在当前浏览器会话。</p>
      <label>管理密钥
        <input v-model="key" type="password" autocomplete="current-password" required />
      </label>
      <button class="btn primary" :disabled="loading || !key">{{ loading ? '正在验证…' : '进入后台' }}</button>
      <p v-if="error" class="alert">{{ error }}</p>
    </form>
  </main>

  <div v-else class="layout">
    <aside class="sidebar">
      <div class="brand">
        <strong>商店管理</strong>
        <span>数字服务交付</span>
      </div>
      <nav>
        <button
          v-for="item in nav"
          :key="item.name"
          type="button"
          :class="{ active: route.name === item.name }"
          @click="go(item.name)"
        >
          <Icon :name="item.icon" />
          <span>{{ item.label }}</span>
          <em v-if="item.name === 'payments' && pendingCount">{{ pendingCount }}</em>
        </button>
      </nav>
      <div class="sidebar-foot">
        <button class="btn ghost light" type="button" @click="logout">退出登录</button>
      </div>
    </aside>

    <section class="content">
      <header class="topbar">
        <h1>{{ pageTitle }}</h1>
        <button class="btn ghost logout-mobile" type="button" @click="logout">退出</button>
      </header>
      <DashboardView v-if="route.name === 'dashboard'" />
      <OrderDetailView v-else-if="route.name === 'orders' && route.id" :order-id="route.id" />
      <OrdersView v-else-if="route.name === 'orders'" />
      <PaymentsView v-else-if="route.name === 'payments'" />
      <ProductsView v-else-if="route.name === 'products'" />
      <CategoriesView v-else-if="route.name === 'categories'" />
      <CustomersView v-else-if="route.name === 'customers'" />
      <CampaignsView v-else-if="route.name === 'campaigns'" />
      <SettingsView v-else-if="route.name === 'settings'" />
    </section>
  </div>
</template>
