<script setup>
import { inject, onMounted, ref } from 'vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { customerLabel, formatDate, money } from '../format.js'
import { stageLabel } from '../labels.js'

const request = inject('request')
const go = inject('go')
const refreshPending = inject('refreshPending')
const payments = ref([])
const config = ref(null)
const error = ref('')
const loading = ref(true)
const action = ref(null)
const rejectReason = ref('')
const busy = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [paymentRes, configRes] = await Promise.all([
      request('/api/admin/payments/pending'),
      request('/api/admin/payment-config'),
    ])
    payments.value = paymentRes.data
    config.value = configRes.data
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function run() {
  if (!action.value) return
  busy.value = true
  error.value = ''
  try {
    if (action.value.type === 'confirm') {
      await request(`/api/admin/payments/${action.value.payment.id}/confirm`, {
        method: 'POST',
        body: JSON.stringify({ confirmed: true }),
      })
    } else {
      await request(`/api/admin/payments/${action.value.payment.id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: rejectReason.value.trim() }),
      })
    }
    action.value = null
    rejectReason.value = ''
    await refreshPending()
    await load()
  } catch (err) {
    error.value = err.message
    action.value = null
  } finally {
    busy.value = false
  }
}

async function copy(value) {
  await navigator.clipboard.writeText(value)
}

onMounted(load)
</script>

<template>
  <p v-if="error" class="alert">{{ error }}</p>
  <p v-if="config && !config.configured" class="alert">尚未配置 USDT 网络和收款地址。请在服务器 .env 中设置后重启。</p>
  <p v-else-if="config" class="notice static">
    <b>{{ config.network }}</b>
    <code>{{ config.receiving_address }}</code>
    <button class="btn ghost sm" type="button" @click="copy(config.receiving_address)">复制地址</button>
  </p>
  <section class="card">
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>订单</th><th>阶段</th><th>金额</th><th>客户</th><th>交易哈希</th><th>提交时间</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="7" class="empty">正在加载…</td></tr>
          <tr v-for="payment in payments" :key="payment.id">
            <td>
              <button class="link" type="button" @click="go(`orders/${payment.order_id}`)">{{ payment.public_id }}</button>
              <small>{{ payment.product_name }}</small>
            </td>
            <td>{{ stageLabel(payment.stage) }}</td>
            <td>{{ money(payment.amount) }} {{ payment.currency }}<small>{{ payment.network || config?.network || '—' }}</small></td>
            <td>{{ customerLabel(payment.customer_username, payment.customer_telegram_user_id) }}</td>
            <td class="mono">{{ payment.tx_hash }}</td>
            <td>{{ formatDate(payment.created_at) }}</td>
            <td class="actions">
              <button class="btn primary sm" type="button" @click="action = { type: 'confirm', payment }">确认到账</button>
              <button class="btn ghost sm" type="button" @click="action = { type: 'reject', payment }; rejectReason = ''">驳回</button>
            </td>
          </tr>
          <tr v-if="!loading && !payments.length"><td colspan="7" class="empty">暂无待核验交易。客户提交 /txid 后会显示在这里。</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <ConfirmDialog
    v-if="action?.type === 'confirm'"
    title="确认到账"
    :message="`确认订单 ${action.payment.public_id} 的 ${money(action.payment.amount)} ${action.payment.currency} 已经到账？`"
    confirm-text="确认到账"
    :loading="busy"
    @cancel="action = null"
    @confirm="run"
  />
  <ConfirmDialog
    v-if="action?.type === 'reject'"
    title="驳回交易哈希"
    message="驳回后客户可以重新提交。请填写原因，这条原因会发给客户。"
    confirm-text="驳回"
    danger
    :loading="busy || !rejectReason.trim()"
    @cancel="action = null"
    @confirm="run"
  >
    <label>原因<input v-model="rejectReason" required maxlength="500" /></label>
  </ConfirmDialog>
</template>
