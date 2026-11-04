<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { customerLabel, formatDate, money } from '../format.js'
import { ORDER_STATES, stateLabel } from '../labels.js'

const request = inject('request')
const go = inject('go')
const orders = ref([])
const total = ref(0)
const campaigns = ref([])
const q = ref('')
const status = ref('')
const campaign = ref('')
const error = ref('')
const loading = ref(false)
let timer = 0

async function loadCampaigns() {
  const { data } = await request('/api/admin/campaigns')
  campaigns.value = data
}

async function load() {
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ limit: '100' })
  if (q.value.trim()) params.set('q', q.value.trim())
  if (status.value) params.set('status', status.value)
  if (campaign.value) params.set('campaign', campaign.value)
  try {
    const result = await request(`/api/admin/orders?${params}`)
    orders.value = result.data
    total.value = result.total ?? result.data.length
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

watch([status, campaign], load)
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})
onMounted(async () => {
  try {
    await loadCampaigns()
  } catch (err) {
    error.value = err.message
  }
  await load()
})
</script>

<template>
  <div class="toolbar">
    <input v-model="q" type="search" placeholder="搜索订单号、客户或商品" />
    <select v-model="status">
      <option value="">全部状态</option>
      <option v-for="item in ORDER_STATES" :key="item" :value="item">{{ stateLabel(item) }}</option>
    </select>
    <select v-model="campaign">
      <option value="">全部来源</option>
      <option v-for="item in campaigns" :key="item.id" :value="item.code">{{ item.name }}</option>
    </select>
    <span class="muted">{{ total }} 条</span>
  </div>
  <p v-if="error" class="alert">{{ error }}</p>
  <section class="card">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>订单</th><th>商品</th><th>金额</th><th>客户</th><th>来源</th><th>交付时间</th><th>状态</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="8" class="empty">正在加载…</td></tr>
          <tr v-for="order in orders" :key="order.id">
            <td><b>{{ order.public_id }}</b><small>{{ formatDate(order.created_at) }}</small></td>
            <td>{{ order.product_name }} × {{ order.quantity }}</td>
            <td>{{ money(order.total_usdt) }}<small>定金 {{ money(order.deposit_usdt) }} USDT</small></td>
            <td>{{ customerLabel(order.customer_username, order.customer_telegram_user_id, order.customer_first_name) }}</td>
            <td>{{ order.campaign_code || '直接访问' }}</td>
            <td>{{ formatDate(order.delivery_at) }}</td>
            <td><StatusBadge :status="order.status" /></td>
            <td class="actions"><button class="btn ghost sm" type="button" @click="go(`orders/${order.id}`)">查看</button></td>
          </tr>
          <tr v-if="!loading && !orders.length"><td colspan="8" class="empty">没有符合条件的订单。</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
