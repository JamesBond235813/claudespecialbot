<script setup>
import { computed, onMounted, ref } from 'vue'

const API_BASE = import.meta.env.VITE_API_BASE || (location.port === '5174' ? 'http://127.0.0.1:8001' : '')
const key = ref(sessionStorage.getItem('adminKey') || '')
const authenticated = ref(false)
const loading = ref(false)
const error = ref('')
const dashboard = ref({ total_orders: 0, pending_orders: 0, completed_orders: 0, active_products: 0 })
const orders = ref([])
const products = ref([])
const campaigns = ref([])
const pendingPayments = ref([])
const paymentConfig = ref({ configured: false, network: '', receiving_address: '' })
const view = ref('orders')
const deliveryOrder = ref(null)
const deliveryMessage = ref('')
const deliveryConfirmed = ref(false)
const productForm = ref({ name: '', category: '默认分类', description: '', deposit_usdt: 0, total_usdt: 0, stock_quantity: null, delivery_note: '次日人工交付' })
const editingProductId = ref(null)
const editForm = ref({ name: '', category: '默认分类', description: '', deposit_usdt: 0, total_usdt: 0, stock_quantity: null, delivery_note: '次日人工交付' })
const campaignForm = ref({ code: '', name: '', source_url: '' })

const states = ['RESERVED', 'DEPOSIT_PENDING', 'DEPOSIT_PAID', 'PREPARING', 'READY', 'DELIVERING', 'COMPLETED', 'CANCELLED', 'REFUNDED', 'DELIVERY_FAILED']
const stateLabels = {
  RESERVED: '已预约', DEPOSIT_PENDING: '待定金', DEPOSIT_PAID: '定金已付', PREPARING: '准备中',
  READY: '待交付', DELIVERING: '交付中', COMPLETED: '已完成', CANCELLED: '已取消',
  REFUNDED: '已退款', DELIVERY_FAILED: '交付失败'
}

const xLink = computed(() => (code) => `https://t.me/${import.meta.env.VITE_BOT_USERNAME || 'ClaudeSpecialbot'}?start=${code}`)

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-Admin-Key': key.value, ...(options.headers || {}) }
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || `请求失败：${response.status}`)
  }
  return response.status === 204 ? null : response.json()
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [d, o, p, c, payments, payConfig] = await Promise.all([
      request('/api/admin/dashboard'), request('/api/admin/orders'),
      request('/api/admin/products'), request('/api/admin/campaigns'),
      request('/api/admin/payments/pending'), request('/api/admin/payment-config')
    ])
    dashboard.value = d
    orders.value = o
    products.value = p
    campaigns.value = c
    pendingPayments.value = payments
    paymentConfig.value = payConfig
    authenticated.value = true
    sessionStorage.setItem('adminKey', key.value)
  } catch (e) {
    error.value = e.message
    authenticated.value = false
  } finally {
    loading.value = false
  }
}

async function updateStatus(order, status) {
  try {
    await request(`/api/admin/orders/${order.id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) })
    await loadAll()
  } catch (e) { error.value = e.message }
}

async function addProduct() {
  try {
    await request('/api/admin/products', { method: 'POST', body: JSON.stringify(productForm.value) })
    productForm.value = { name: '', category: '默认分类', description: '', deposit_usdt: 0, total_usdt: 0, stock_quantity: null, delivery_note: '次日人工交付' }
    await loadAll()
  } catch (e) { error.value = e.message }
}

async function confirmPayment(payment) {
  try {
    await request(`/api/admin/payments/${payment.id}/confirm`, {
      method: 'POST', body: JSON.stringify({ confirmed: true })
    })
    await loadAll()
  } catch (e) { error.value = e.message }
}

function openDelivery(order) {
  deliveryOrder.value = order
  deliveryMessage.value = ''
  deliveryConfirmed.value = false
}

async function sendDelivery() {
  if (!deliveryOrder.value) return
  try {
    await request(`/api/admin/orders/${deliveryOrder.value.id}/deliver`, {
      method: 'POST',
      body: JSON.stringify({ message: deliveryMessage.value, confirmed: deliveryConfirmed.value })
    })
    deliveryOrder.value = null
    deliveryMessage.value = ''
    deliveryConfirmed.value = false
    await loadAll()
  } catch (e) { error.value = e.message }
}

async function toggleProduct(product) {
  try {
    await request(`/api/admin/products/${product.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !product.is_active }) })
    await loadAll()
  } catch (e) { error.value = e.message }
}

function startEdit(product) {
  editingProductId.value = product.id
  editForm.value = {
    name: product.name,
    category: product.category,
    description: product.description,
    deposit_usdt: Number(product.deposit_usdt),
    total_usdt: Number(product.total_usdt),
    stock_quantity: product.stock_quantity,
    delivery_note: product.delivery_note,
    is_active: product.is_active
  }
}

function clearStockIfEmpty(event, form) {
  if (event.target.value === '') form.stock_quantity = null
}

async function saveProduct() {
  try {
    await request(`/api/admin/products/${editingProductId.value}`, {
      method: 'PATCH', body: JSON.stringify(editForm.value)
    })
    editingProductId.value = null
    await loadAll()
  } catch (e) { error.value = e.message }
}

async function addCampaign() {
  try {
    await request('/api/admin/campaigns', { method: 'POST', body: JSON.stringify(campaignForm.value) })
    campaignForm.value = { code: '', name: '', source_url: '' }
    await loadAll()
  } catch (e) { error.value = e.message }
}

async function copyLink(code) {
  await navigator.clipboard.writeText(xLink.value(code))
}

function formatDate(value) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(`${value}Z`)) : '—'
}

onMounted(() => { if (key.value) loadAll() })
</script>

<template>
  <main class="shell">
    <section v-if="!authenticated" class="login-card">
      <div class="brand-mark">D</div>
      <h1>数字服务交付后台</h1>
      <p>输入本机配置的管理密钥</p>
      <form @submit.prevent="loadAll">
        <input v-model="key" type="password" placeholder="Admin API Key" autocomplete="current-password" />
        <button :disabled="loading">{{ loading ? '连接中…' : '进入后台' }}</button>
      </form>
      <div v-if="error" class="error">{{ error }}</div>
    </section>

    <template v-else>
      <header>
        <div><span class="eyebrow">OPERATIONS</span><h1>数字服务交付</h1></div>
        <button class="quiet" @click="loadAll">刷新数据</button>
      </header>

      <nav>
        <button v-for="item in [['orders','订单'],['payments','付款核验'],['products','商品'],['campaigns','获客链接']]" :key="item[0]" :class="{ active: view === item[0] }" @click="view = item[0]">{{ item[1] }}<span v-if="item[0] === 'payments' && pendingPayments.length"> · {{ pendingPayments.length }}</span></button>
      </nav>

      <section class="metrics">
        <article><span>全部订单</span><strong>{{ dashboard.total_orders }}</strong></article>
        <article><span>待处理</span><strong>{{ dashboard.pending_orders }}</strong></article>
        <article><span>已完成</span><strong>{{ dashboard.completed_orders }}</strong></article>
        <article><span>在售商品</span><strong>{{ dashboard.active_products }}</strong></article>
      </section>

      <div v-if="error" class="error inline">{{ error }}</div>

      <section v-if="view === 'orders'" class="panel">
        <div class="panel-head"><div><span class="eyebrow">QUEUE</span><h2>交付订单</h2></div><span>{{ orders.length }} 条</span></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>订单</th><th>商品</th><th>客户</th><th>来源</th><th>交付时间</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="order in orders" :key="order.id">
                <td><b>{{ order.public_id }}</b><small>{{ formatDate(order.created_at) }}</small></td>
                <td>{{ order.product_name }} × {{ order.quantity }}<small>定金 {{ order.deposit_usdt }} USDT</small></td>
                <td>{{ order.customer_username ? '@' + order.customer_username : order.customer_telegram_user_id }}</td>
                <td>{{ order.campaign_code || '直接访问' }}</td>
                <td>{{ formatDate(order.delivery_at) }}</td>
                <td><select :value="order.status" @change="updateStatus(order, $event.target.value)"><option v-for="state in states" :key="state" :value="state">{{ stateLabels[state] || state }}</option></select></td>
                <td><button v-if="['READY','DELIVERING'].includes(order.status)" class="deliver-button" @click="openDelivery(order)">发送交付</button><span v-else>—</span></td>
              </tr>
              <tr v-if="!orders.length"><td colspan="7" class="empty">尚无订单，先用 Telegram Bot 创建一笔测试预约。</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="view === 'payments'" class="panel">
        <div class="panel-head"><div><span class="eyebrow">USDT SETTLEMENT</span><h2>待核验付款</h2></div><span>{{ pendingPayments.length }} 条</span></div>
        <p v-if="!paymentConfig.configured" class="error">尚未配置 USDT 网络和公共收款地址。配置 .env 后重启服务。</p>
        <p v-else class="wallet-note">当前收款网络：<b>{{ paymentConfig.network }}</b><code>{{ paymentConfig.receiving_address }}</code></p>
        <div v-for="payment in pendingPayments" :key="payment.id" class="list-card">
          <div><b>{{ payment.public_id }} · {{ payment.product_name }} · {{ payment.stage === 'balance' ? '尾款' : '定金' }}</b><p>{{ payment.amount }} {{ payment.currency }} · {{ payment.network || paymentConfig.network }} · 客户 {{ payment.customer_telegram_user_id }}</p><code>{{ payment.tx_hash }}</code></div>
          <button @click="confirmPayment(payment)">确认到账</button>
        </div>
        <div v-if="!pendingPayments.length" class="empty">暂无待核验交易。客户提交 TXID 后会显示在这里。</div>
      </section>

      <section v-if="view === 'products'" class="two-column">
        <div class="panel">
          <div class="panel-head"><h2>商品目录</h2><span>{{ products.length }} 个商品位</span></div>
          <article v-for="product in products" :key="product.id" class="list-card">
          <div><b>{{ product.name }}</b><p>{{ product.description }}</p><small>{{ product.category }} · {{ product.stock_quantity == null ? '库存不限' : `库存 ${product.stock_quantity}` }} · {{ product.deposit_usdt ? `定金 ${product.deposit_usdt} USDT/件` : '0 定金' }} · {{ product.delivery_note }}</small></div>
            <div class="actions"><button class="quiet" @click="startEdit(product)">编辑</button><button class="pill" :class="{ off: !product.is_active }" @click="toggleProduct(product)">{{ product.is_active ? '在售' : '停用' }}</button></div>
          </article>
        </div>
        <form v-if="!editingProductId" class="panel form" @submit.prevent="addProduct">
          <h2>新增商品</h2>
          <label>名称<input v-model="productForm.name" required maxlength="255" /></label>
          <label>分类<input v-model="productForm.category" required maxlength="100" /></label>
          <label>说明<textarea v-model="productForm.description" required rows="5"></textarea></label>
          <div class="form-row"><label>定金 USDT<input v-model.number="productForm.deposit_usdt" type="number" min="0" step="0.000001" /></label><label>总价 USDT<input v-model.number="productForm.total_usdt" type="number" min="0" step="0.000001" /></label></div>
          <label>库存数量<input v-model.number="productForm.stock_quantity" @input="clearStockIfEmpty($event, productForm)" type="number" min="0" placeholder="留空表示不限库存" /></label>
          <label>交付说明<input v-model="productForm.delivery_note" /></label>
          <button>创建商品</button>
        </form>
        <form v-else class="panel form" @submit.prevent="saveProduct">
          <h2>编辑商品槽位</h2>
          <label>名称<input v-model="editForm.name" required maxlength="255" /></label>
          <label>分类<input v-model="editForm.category" required maxlength="100" /></label>
          <label>说明<textarea v-model="editForm.description" required rows="5"></textarea></label>
          <div class="form-row"><label>定金 USDT<input v-model.number="editForm.deposit_usdt" type="number" min="0" step="0.000001" /></label><label>总价 USDT<input v-model.number="editForm.total_usdt" type="number" min="0" step="0.000001" /></label></div>
          <label>库存数量<input v-model.number="editForm.stock_quantity" @input="clearStockIfEmpty($event, editForm)" type="number" min="0" placeholder="留空表示不限库存" /></label>
          <label>交付说明<input v-model="editForm.delivery_note" /></label>
          <label class="check-row"><input v-model="editForm.is_active" type="checkbox" />在售</label>
          <div class="actions"><button>保存商品</button><button type="button" class="quiet" @click="editingProductId = null">取消</button></div>
        </form>
      </section>

      <section v-if="view === 'campaigns'" class="two-column">
        <div class="panel">
          <div class="panel-head"><h2>X 获客链接</h2></div>
          <article v-for="campaign in campaigns" :key="campaign.id" class="list-card campaign">
            <div><b>{{ campaign.name }}</b><code>{{ xLink(campaign.code) }}</code></div>
            <button class="quiet" @click="copyLink(campaign.code)">复制</button>
          </article>
        </div>
        <form class="panel form" @submit.prevent="addCampaign">
          <h2>新建来源</h2>
          <label>来源码<input v-model="campaignForm.code" required pattern="[A-Za-z0-9_-]{1,64}" placeholder="x_post_001" /></label>
          <label>活动名称<input v-model="campaignForm.name" required placeholder="11 月产品帖" /></label>
          <label>X 帖子地址<input v-model="campaignForm.source_url" placeholder="https://x.com/..." /></label>
          <button>生成链接</button>
        </form>
      </section>

      <div v-if="deliveryOrder" class="modal-backdrop" @click.self="deliveryOrder = null">
        <form class="delivery-modal" @submit.prevent="sendDelivery">
          <span class="eyebrow">MANUAL DELIVERY</span>
          <h2>发送订单 {{ deliveryOrder.public_id }}</h2>
          <p>收件人 Telegram ID：{{ deliveryOrder.customer_telegram_user_id }}。交付正文会直接发给客户，不写入订单日志。</p>
          <label>交付内容<textarea v-model="deliveryMessage" required maxlength="4000" rows="8" placeholder="输入该订单的交付说明或交付资料"></textarea></label>
          <label class="check-row"><input v-model="deliveryConfirmed" type="checkbox" required />我已核对收件人和交付内容，确认发送并完成订单</label>
          <div class="actions"><button :disabled="!deliveryConfirmed || !deliveryMessage.trim()">确认发送</button><button type="button" class="quiet" @click="deliveryOrder = null">取消</button></div>
        </form>
      </div>
    </template>
  </main>
</template>

