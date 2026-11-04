<script setup>
import { inject, onMounted, reactive, ref } from 'vue'

const request = inject('request')
const form = reactive({
  show_categories: false,
  welcome_text: '',
  store_prompt: '',
  product_prompt: '',
  terms_text: '',
})
const meta = ref(null)
const error = ref('')
const saved = ref(false)
const loading = ref(true)
const busy = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await request('/api/admin/settings')
    meta.value = data
    Object.assign(form, {
      show_categories: data.show_categories,
      welcome_text: data.welcome_text,
      store_prompt: data.store_prompt,
      product_prompt: data.product_prompt,
      terms_text: data.terms_text,
    })
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

async function save() {
  busy.value = true
  error.value = ''
  saved.value = false
  try {
    const { data } = await request('/api/admin/settings', {
      method: 'PUT',
      body: JSON.stringify({
        show_categories: form.show_categories,
        welcome_text: form.welcome_text,
        store_prompt: form.store_prompt,
        product_prompt: form.product_prompt,
        terms_text: form.terms_text,
      }),
    })
    meta.value = data
    saved.value = true
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <p v-if="error" class="alert">{{ error }}</p>
  <p v-if="saved" class="success">已保存，机器人下次回复时就会使用新设置。</p>
  <p v-if="loading" class="muted">正在加载设置…</p>
  <form v-else class="settings" @submit.prevent="save">
    <section class="card stack">
      <h2>商店展示</h2>
      <label class="toggle">
        <input v-model="form.show_categories" type="checkbox" />
        <span>
          <b>显示分类步骤</b>
          <small>开启时，用户先看到分类按钮。关闭时跳过分类，直接列出所有可见分类中的在售商品。隐藏的分类无论开关都会被排除。</small>
        </span>
      </label>
      <label>欢迎文案
        <textarea v-model="form.welcome_text" rows="3" maxlength="2000" placeholder="留空则 /start 直接显示商店引导和商品按钮"></textarea>
        <small>只在 /start 时加在同一条商店消息顶部，不会单独再发一条欢迎。渠道参数（如 x_default）仍会归因。</small>
      </label>
      <label>商店引导文案
        <input v-model="form.store_prompt" required maxlength="500" />
        <small>分类列表或全部商品列表上方的主文案。</small>
      </label>
      <label>分类内引导文案
        <input v-model="form.product_prompt" required maxlength="500" />
        <small>用户进入某个分类后，商品按钮上方的文案。</small>
      </label>
    </section>

    <section class="card stack">
      <h2>服务条款</h2>
      <label>条款正文
        <textarea v-model="form.terms_text" rows="6" maxlength="4000" :placeholder="meta?.terms_default"></textarea>
        <small>留空时 /terms 使用内置条款。版本号仍来自环境变量 TERMS_VERSION<span v-if="meta">（当前 {{ meta.terms_version }}）</span>。</small>
      </label>
    </section>

    <section v-if="meta" class="card stack">
      <h2>运行信息</h2>
      <dl class="facts">
        <div><dt>机器人</dt><dd>@{{ meta.bot_username }}</dd></div>
        <div><dt>客服</dt><dd>{{ meta.support_handle }}</dd></div>
        <div><dt>USDT</dt><dd>{{ meta.usdt_configured ? `${meta.usdt_network} · ${meta.usdt_receiving_address}` : '未配置' }}</dd></div>
      </dl>
      <p class="hint">收款地址、客服和条款版本在服务器 .env 中配置，修改后需要重启服务。</p>
    </section>

    <div class="actions">
      <button class="btn primary" :disabled="busy">{{ busy ? '保存中…' : '保存设置' }}</button>
    </div>
  </form>
</template>
