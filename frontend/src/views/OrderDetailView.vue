<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { customerLabel, formatDate, money } from '../format.js'
import { ORDER_STATES, PAYMENT_LABELS, actorLabel, stageLabel, stateLabel } from '../labels.js'

const props = defineProps({ orderId: { type: String, required: true } })
const request = inject('request')
const go = inject('go')
const refreshPending = inject('refreshPending')

const order = ref(null)
const error = ref('')
const loading = ref(true)
const nextStatus = ref('')
const reason = ref('')
const notes = ref('')
const statusDialog = ref(false)
const deliverOpen = ref(false)
const deliveryMessage = ref('')
const deliveryConfirmed = ref(false)
const paymentAction = ref(null)
const rejectReason = ref('')
const busy = ref(false)

const editableStates = ORDER_STATES.filter((item) => item !== 'COMPLETED')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await request(`/api/admin/orders/${props.orderId}`)
    order.value = data
    nextStatus.value = data.status === 'COMPLETED' ? 'COMPLETED' : data.status
    notes.value = data.notes || ''
  } catch (err) {
    error.value = err.message
    order.value = null
  } finally {
    loading.value = false
  }
}

function askStatus() {
  if (!order.value || nextStatus.value === order.value.status) return
  statusDialog.value = true
}

async function applyStatus() {
  busy.value = true
  error.value = ''
  try {
    await request(`/api/admin/orders/${order.value.id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status: nextStatus.value, reason: reason.value.trim() || null }),
    })
    statusDialog.value = false
    reason.value = ''
    await load()
  } catch (err) {
    error.value = err.message
    statusDialog.value = false
  } finally {
    busy.value = false
  }
}

async function saveNotes() {
  busy.value = true
  error.value = ''
  try {
    const { data } = await request(`/api/admin/orders/${order.value.id}/notes`, {
      method: 'PATCH',
      body: JSON.stringify({ notes: notes.value }),
    })
    order.value = data
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

async function sendDelivery() {
  busy.value = true
  error.value = ''
  try {
    await request(`/api/admin/orders/${order.value.id}/deliver`, {
      method: 'POST',
      body: JSON.stringify({ message: deliveryMessage.value, confirmed: deliveryConfirmed.value }),
    })
    deliverOpen.value = false
    deliveryMessage.value = ''
    deliveryConfirmed.value = false
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

async function runPaymentAction() {
  if (!paymentAction.value) return
  busy.value = true
  error.value = ''
  const { type, payment } = paymentAction.value
  try {
    if (type === 'confirm') {
      await request(`/api/admin/payments/${payment.id}/confirm`, {
        method: 'POST',
        body: JSON.stringify({ confirmed: true }),
      })
    } else {
      await request(`/api/admin/payments/${payment.id}/reject`, {
        method: 'POST',
        body: JSON.stringify({ reason: rejectReason.value.trim() }),
      })
    }
    paymentAction.value = null
    rejectReason.value = ''
    await refreshPending()
    await load()
  } catch (err) {
    error.value = err.message
    paymentAction.value = null
  } finally {
    busy.value = false
  }
}

watch(() => props.orderId, load)
onMounted(load)
</script>

<template>
  <button class="btn ghost sm back" type="button" @click="go('orders')">返回订单列表</button>
  <p v-if="error" class="alert">{{ error }}</p>
  <p v-if="loading" class="muted">正在加载订单…</p>
  <template v-else-if="order">
    <header class="detail-title">
      <div>
        <h2>{{ order.public_id }}</h2>
        <StatusBadge :status="order.status" />
      </div>
      <button v-if="['READY', 'DELIVERING'].includes(order.status)" class="btn primary" type="button" @click="deliverOpen = true">发送交付</button>
    </header>

    <div class="split detail-grid">
      <section class="card stack">
        <h2>订单信息</h2>
        <dl class="facts">
          <div><dt>商品</dt><dd>{{ order.product_name }} × {{ order.quantity }}</dd></div>
          <div><dt>总价 / 定金</dt><dd>{{ money(order.total_usdt) }} / {{ money(order.deposit_usdt) }} USDT</dd></div>
          <div><dt>客户</dt><dd>{{ customerLabel(order.customer_username, order.customer_telegram_user_id, order.customer_first_name) }}<small>ID {{ order.customer_telegram_user_id }}</small></dd></div>
          <div><dt>来源</dt><dd>{{ order.campaign_code || '直接访问' }}</dd></div>
          <div><dt>预计交付</dt><dd>{{ formatDate(order.delivery_at) }}</dd></div>
          <div><dt>实际交付</dt><dd>{{ formatDate(order.delivered_at) }}</dd></div>
          <div><dt>条款</dt><dd>{{ order.terms_version }}<small>{{ formatDate(order.terms_accepted_at) }}</small></dd></div>
        </dl>
        <label>内部备注
          <textarea v-model="notes" rows="3" maxlength="4000" placeholder="仅后台可见"></textarea>
        </label>
        <div class="actions"><button class="btn ghost" type="button" :disabled="busy" @click="saveNotes">保存备注</button></div>

        <h2>更新状态</h2>
        <div class="inline-form">
          <select v-model="nextStatus" :disabled="order.status === 'COMPLETED'">
            <option v-if="order.status === 'COMPLETED'" value="COMPLETED">已完成</option>
            <option v-for="item in editableStates" :key="item" :value="item">{{ stateLabel(item) }}</option>
          </select>
          <input v-model="reason" maxlength="500" placeholder="原因，可选" :disabled="order.status === 'COMPLETED'" />
          <button class="btn primary" type="button" :disabled="busy || order.status === 'COMPLETED' || nextStatus === order.status" @click="askStatus">更新</button>
        </div>
        <p class="hint">完成订单请使用「发送交付」。交付正文会直接发给客户，不写入订单记录。</p>
      </section>

      <div class="stack">
        <section class="card">
          <h2>付款</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>阶段</th><th>金额</th><th>状态</th><th>交易哈希</th><th></th></tr></thead>
              <tbody>
                <tr v-for="payment in order.payments" :key="payment.id">
                  <td>{{ stageLabel(payment.stage) }}</td>
                  <td>{{ money(payment.amount) }} {{ payment.currency }}<small>{{ payment.network || '—' }}</small></td>
                  <td>{{ PAYMENT_LABELS[payment.status] || payment.status }}</td>
                  <td class="mono">{{ payment.tx_hash || '—' }}</td>
                  <td class="actions" v-if="payment.status === 'PENDING' && payment.tx_hash">
                    <button class="btn primary sm" type="button" @click="paymentAction = { type: 'confirm', payment }">确认到账</button>
                    <button class="btn ghost sm" type="button" @click="paymentAction = { type: 'reject', payment }; rejectReason = ''">驳回</button>
                  </td>
                  <td v-else>—</td>
                </tr>
                <tr v-if="!order.payments.length"><td colspan="5" class="empty">这笔订单没有付款记录。</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="card">
          <h2>状态历史</h2>
          <ol class="timeline">
            <li v-for="item in order.history" :key="item.id">
              <b>{{ item.from_status ? `${stateLabel(item.from_status)} → ` : '' }}{{ stateLabel(item.to_status) }}</b>
              <small>{{ formatDate(item.created_at) }} · {{ actorLabel(item.actor) }}</small>
              <p v-if="item.reason">{{ item.reason }}</p>
            </li>
            <li v-if="!order.history.length" class="empty">暂无记录。</li>
          </ol>
        </section>
      </div>
    </div>

    <ConfirmDialog
      v-if="statusDialog"
      title="更新订单状态"
      :message="`将 ${order.public_id} 的状态改为「${stateLabel(nextStatus)}」？客户会收到通知。`"
      confirm-text="确认更新"
      :loading="busy"
      @cancel="statusDialog = false"
      @confirm="applyStatus"
    />

    <div v-if="deliverOpen" class="modal-backdrop" @click.self="deliverOpen = false">
      <form class="modal" @submit.prevent="sendDelivery">
        <header class="modal-head">
          <h3>发送交付 {{ order.public_id }}</h3>
          <button type="button" class="icon-btn" aria-label="关闭" @click="deliverOpen = false">×</button>
        </header>
        <div class="modal-body stack">
          <p class="dialog-copy">收件人 Telegram ID：{{ order.customer_telegram_user_id }}。正文会直接发送，不写入订单日志。</p>
          <label>交付内容
            <textarea v-model="deliveryMessage" required maxlength="4000" rows="8" placeholder="输入该订单的交付说明或交付资料"></textarea>
          </label>
          <label class="check"><input v-model="deliveryConfirmed" type="checkbox" />我已核对收件人和交付内容</label>
        </div>
        <footer class="modal-foot">
          <button type="button" class="btn ghost" @click="deliverOpen = false">取消</button>
          <button class="btn primary" :disabled="busy || !deliveryConfirmed || !deliveryMessage.trim()">确认发送并完成</button>
        </footer>
      </form>
    </div>

    <ConfirmDialog
      v-if="paymentAction?.type === 'confirm'"
      title="确认到账"
      :message="`确认已核对订单 ${order.public_id} 的这笔 USDT 到账？`"
      confirm-text="确认到账"
      :loading="busy"
      @cancel="paymentAction = null"
      @confirm="runPaymentAction"
    />
    <ConfirmDialog
      v-if="paymentAction?.type === 'reject'"
      title="驳回交易哈希"
      message="驳回后客户可以重新提交交易哈希。订单状态不会改变。"
      confirm-text="驳回"
      danger
      :loading="busy || !rejectReason.trim()"
      @cancel="paymentAction = null"
      @confirm="runPaymentAction"
    >
      <label>原因
        <input v-model="rejectReason" required maxlength="500" placeholder="例如：金额或网络不符" />
      </label>
    </ConfirmDialog>
  </template>
</template>
