<script setup>
import { inject, onMounted, reactive, ref } from 'vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Modal from '../components/Modal.vue'
import { formatDate, money } from '../format.js'

const request = inject('request')
const campaigns = ref([])
const botUsername = ref('ClaudeSpecialbot')
const error = ref('')
const loading = ref(true)
const creating = ref(false)
const busy = ref(false)
const copied = ref('')
const pendingDelete = ref(null)
const form = reactive({ code: '', name: '', source_url: '' })

function link(code) {
  return `https://t.me/${botUsername.value}?start=${code}`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [campaignRes, settingRes] = await Promise.all([
      request('/api/admin/campaigns'),
      request('/api/admin/settings'),
    ])
    campaigns.value = campaignRes.data
    botUsername.value = settingRes.data.bot_username || botUsername.value
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function create() {
  busy.value = true
  error.value = ''
  try {
    await request('/api/admin/campaigns', {
      method: 'POST',
      body: JSON.stringify({
        code: form.code.trim(),
        name: form.name.trim(),
        source_url: form.source_url.trim() || null,
      }),
    })
    Object.assign(form, { code: '', name: '', source_url: '' })
    creating.value = false
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

async function toggle(campaign) {
  error.value = ''
  try {
    await request(`/api/admin/campaigns/${campaign.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: !campaign.is_active }),
    })
    await load()
  } catch (err) {
    error.value = err.message
  }
}

async function remove() {
  if (!pendingDelete.value) return
  busy.value = true
  error.value = ''
  try {
    await request(`/api/admin/campaigns/${pendingDelete.value.id}`, { method: 'DELETE' })
    pendingDelete.value = null
    await load()
  } catch (err) {
    error.value = err.message
    pendingDelete.value = null
  } finally {
    busy.value = false
  }
}

async function copy(code) {
  await navigator.clipboard.writeText(link(code))
  copied.value = code
}

onMounted(load)
</script>

<template>
  <p class="notice static">
    <span>把链接放在帖子或广告里。用户通过 <b>/start 参数</b> 打开机器人时仍会归因，并直接进入商店。停用只作标记，已发出的链接继续统计。</span>
  </p>
  <div class="toolbar">
    <span class="muted">{{ campaigns.length }} 个来源</span>
    <button class="btn primary" type="button" @click="creating = true">新建来源</button>
  </div>
  <p v-if="error" class="alert">{{ error }}</p>
  <section class="card">
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>来源</th><th>链接</th><th>订单</th><th>已确认收款</th><th>状态</th><th>创建</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="7" class="empty">正在加载…</td></tr>
          <tr v-for="campaign in campaigns" :key="campaign.id">
            <td>
              <b>{{ campaign.name }}</b>
              <small>{{ campaign.code }}<template v-if="campaign.source_url"> · {{ campaign.source_url }}</template></small>
            </td>
            <td class="mono link-cell">{{ link(campaign.code) }}</td>
            <td>{{ campaign.order_count }}</td>
            <td>{{ money(campaign.revenue_usdt) }} USDT</td>
            <td><button class="pill" :class="{ off: !campaign.is_active }" type="button" @click="toggle(campaign)">{{ campaign.is_active ? '启用' : '停用' }}</button></td>
            <td>{{ formatDate(campaign.created_at) }}</td>
            <td class="actions">
              <button class="btn ghost sm" type="button" @click="copy(campaign.code)">{{ copied === campaign.code ? '已复制' : '复制' }}</button>
              <button class="btn ghost sm" type="button" :disabled="campaign.order_count > 0" @click="pendingDelete = campaign">删除</button>
            </td>
          </tr>
          <tr v-if="!loading && !campaigns.length"><td colspan="7" class="empty">还没有来源链接。</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <Modal v-if="creating" title="新建来源" @close="creating = false" @submit="create">
    <div class="form-grid">
      <label>来源码<input v-model="form.code" required pattern="[A-Za-z0-9_-]{1,64}" placeholder="x_post_001" /></label>
      <label>名称<input v-model="form.name" required maxlength="255" placeholder="11 月产品帖" /></label>
      <label class="span-2">来源地址<input v-model="form.source_url" maxlength="1024" placeholder="https://x.com/..." /></label>
    </div>
    <template #footer>
      <button type="button" class="btn ghost" @click="creating = false">取消</button>
      <button class="btn primary" :disabled="busy">生成链接</button>
    </template>
  </Modal>

  <ConfirmDialog
    v-if="pendingDelete"
    title="删除来源"
    :message="`删除「${pendingDelete.name}」？已有订单的来源不能删除，可以停用。`"
    confirm-text="删除"
    danger
    :loading="busy"
    @cancel="pendingDelete = null"
    @confirm="remove"
  />
</template>
