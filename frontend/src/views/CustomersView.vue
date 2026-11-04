<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { formatDate, money } from '../format.js'

const request = inject('request')
const customers = ref([])
const q = ref('')
const error = ref('')
const loading = ref(false)
const pending = ref(null)
const busy = ref(false)
let timer = 0

async function load() {
  loading.value = true
  error.value = ''
  const params = new URLSearchParams({ limit: '200' })
  if (q.value.trim()) params.set('q', q.value.trim())
  try {
    const { data } = await request(`/api/admin/customers?${params}`)
    customers.value = data
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function applyBlock() {
  if (!pending.value) return
  busy.value = true
  error.value = ''
  try {
    await request(`/api/admin/customers/${pending.value.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_blocked: !pending.value.is_blocked }),
    })
    pending.value = null
    await load()
  } catch (err) {
    error.value = err.message
    pending.value = null
  } finally {
    busy.value = false
  }
}

watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
})
onMounted(load)
</script>

<template>
  <div class="toolbar">
    <input v-model="q" type="search" placeholder="搜索用户名、名字或 Telegram ID" />
    <span class="muted">{{ customers.length }} 位客户</span>
  </div>
  <p v-if="error" class="alert">{{ error }}</p>
  <section class="card">
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>客户</th><th>Telegram ID</th><th>订单</th><th>已确认消费</th><th>注册</th><th>状态</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="7" class="empty">正在加载…</td></tr>
          <tr v-for="customer in customers" :key="customer.id">
            <td>
              <b>{{ customer.username ? '@' + customer.username : (customer.first_name || '未命名') }}</b>
              <small v-if="customer.first_name && customer.username">{{ customer.first_name }}</small>
            </td>
            <td class="mono">{{ customer.telegram_user_id }}</td>
            <td>{{ customer.order_count }}</td>
            <td>{{ money(customer.spent_usdt) }} USDT</td>
            <td>{{ formatDate(customer.created_at) }}</td>
            <td><span class="pill" :class="{ off: customer.is_blocked }">{{ customer.is_blocked ? '已限制' : '正常' }}</span></td>
            <td class="actions">
              <button class="btn ghost sm" type="button" @click="pending = customer">{{ customer.is_blocked ? '解除限制' : '限制下单' }}</button>
            </td>
          </tr>
          <tr v-if="!loading && !customers.length"><td colspan="7" class="empty">还没有客户。用户发送 /start 后会出现在这里。</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <ConfirmDialog
    v-if="pending"
    :title="pending.is_blocked ? '解除限制' : '限制下单'"
    :message="pending.is_blocked ? '解除后，该客户可以再次预约。' : '限制后，该客户仍可浏览商品，但不能创建新订单。'"
    :confirm-text="pending.is_blocked ? '解除' : '限制'"
    :danger="!pending.is_blocked"
    :loading="busy"
    @cancel="pending = null"
    @confirm="applyBlock"
  />
</template>
