<script setup>
import { inject, onMounted, ref } from 'vue'
import StatusBadge from '../components/StatusBadge.vue'
import { customerLabel, formatDate, money } from '../format.js'

const request = inject('request')
const go = inject('go')
const dashboard = ref(null)
const orders = ref([])
const payments = ref([])
const settings = ref(null)
const error = ref('')
const loading = ref(true)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [stats, orderRes, paymentRes, settingRes] = await Promise.all([
      request('/api/admin/dashboard'),
      request('/api/admin/orders?limit=8'),
      request('/api/admin/payments/pending'),
      request('/api/admin/settings'),
    ])
    dashboard.value = stats.data
    orders.value = orderRes.data
    payments.value = paymentRes.data
    settings.value = settingRes.data
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <p v-if="error" class="alert">{{ error }}</p>
  <p v-else-if="loading" class="muted">正在加载概览…</p>
  <template v-else-if="dashboard">
    <section class="stats">
      <article>
        <span>今日订单</span>
        <strong>{{ dashboard.today_orders }}</strong>
        <small>按营业时区计算</small>
      </article>
      <article>
        <span>全部订单</span>
        <strong>{{ dashboard.total_orders }}</strong>
        <small>待处理 {{ dashboard.pending_orders }} · 已完成 {{ dashboard.completed_orders }}</small>
      </article>
      <article>
        <span>待核验付款</span>
        <strong>{{ dashboard.pending_payment_count }}</strong>
        <small>{{ money(dashboard.pending_payment_amount) }} USDT</small>
      </article>
      <article>
        <span>已确认收款</span>
        <strong>{{ money(dashboard.revenue_usdt) }}</strong>
        <small>USDT · 客户 {{ dashboard.customer_count }} · 在售 {{ dashboard.active_products }}</small>
      </article>
    </section>

    <button v-if="settings" class="notice" type="button" @click="go('settings')">
      <b>分类步骤{{ settings.show_categories ? '已开启' : '已关闭' }}</b>
      <span>{{ settings.show_categories ? '用户先选择分类，再选择商品。' : '用户打开商店后直接看到全部可见商品。' }}</span>
      <em>去设置</em>
    </button>

    <div class="split">
      <section class="card">
        <header class="card-head">
          <h2>最近订单</h2>
          <button class="btn ghost sm" type="button" @click="go('orders')">全部订单</button>
        </header>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>订单</th><th>商品</th><th>金额</th><th>客户</th><th>状态</th></tr>
            </thead>
            <tbody>
              <tr v-for="order in orders" :key="order.id" class="clickable" @click="go(`orders/${order.id}`)">
                <td><b>{{ order.public_id }}</b><small>{{ formatDate(order.created_at) }}</small></td>
                <td>{{ order.product_name }} × {{ order.quantity }}</td>
                <td>{{ money(order.total_usdt) }} USDT</td>
                <td>{{ customerLabel(order.customer_username, order.customer_telegram_user_id, order.customer_first_name) }}</td>
                <td><StatusBadge :status="order.status" /></td>
              </tr>
              <tr v-if="!orders.length"><td colspan="5" class="empty">还没有订单。</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card">
        <header class="card-head">
          <h2>待核验</h2>
          <button class="btn ghost sm" type="button" @click="go('payments')">去核验</button>
        </header>
        <ul class="plain-list">
          <li v-for="payment in payments.slice(0, 6)" :key="payment.id">
            <div>
              <b>{{ payment.public_id }}</b>
              <small>{{ payment.product_name }} · {{ money(payment.amount) }} {{ payment.currency }}</small>
            </div>
          </li>
          <li v-if="!payments.length" class="empty">没有待核验的交易哈希。</li>
        </ul>
      </section>
    </div>
  </template>
</template>
