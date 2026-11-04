<script setup>
import { inject, onMounted, reactive, ref } from 'vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Modal from '../components/Modal.vue'

const request = inject('request')
const categories = ref([])
const settings = ref(null)
const error = ref('')
const loading = ref(true)
const editing = ref(false)
const busy = ref(false)
const pendingDelete = ref(null)
const form = reactive({ id: null, name: '', is_visible: true, sort_order: 0 })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [categoryRes, settingRes] = await Promise.all([
      request('/api/admin/categories'),
      request('/api/admin/settings'),
    ])
    categories.value = categoryRes.data
    settings.value = settingRes.data
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: null, name: '', is_visible: true, sort_order: categories.value.length })
  editing.value = true
}

function openEdit(category) {
  Object.assign(form, category)
  editing.value = true
}

async function save() {
  busy.value = true
  error.value = ''
  const body = { name: form.name, is_visible: form.is_visible, sort_order: Number(form.sort_order || 0) }
  try {
    if (form.id) {
      await request(`/api/admin/categories/${form.id}`, { method: 'PATCH', body: JSON.stringify(body) })
    } else {
      await request('/api/admin/categories', { method: 'POST', body: JSON.stringify(body) })
    }
    editing.value = false
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

async function toggle(category) {
  error.value = ''
  try {
    await request(`/api/admin/categories/${category.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_visible: !category.is_visible }),
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
    await request(`/api/admin/categories/${pendingDelete.value.id}`, { method: 'DELETE' })
    pendingDelete.value = null
    await load()
  } catch (err) {
    error.value = err.message
    pendingDelete.value = null
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <p v-if="settings" class="notice static">
    <b>分类步骤{{ settings.show_categories ? '已开启' : '已关闭' }}</b>
    <span>隐藏分类后，其中的商品不会出现在机器人里。全局开关在「设置」。</span>
  </p>
  <div class="toolbar">
    <span class="muted">{{ categories.length }} 个分类</span>
    <button class="btn primary" type="button" @click="openCreate">新建分类</button>
  </div>
  <p v-if="error" class="alert">{{ error }}</p>
  <section class="card">
    <div class="table-wrap">
      <table>
        <thead><tr><th>排序</th><th>名称</th><th>商品数</th><th>显示</th><th></th></tr></thead>
        <tbody>
          <tr v-if="loading"><td colspan="5" class="empty">正在加载…</td></tr>
          <tr v-for="category in categories" :key="category.id">
            <td>{{ category.sort_order }}</td>
            <td><b>{{ category.name }}</b></td>
            <td>{{ category.product_count }}</td>
            <td><button class="pill" :class="{ off: !category.is_visible }" type="button" @click="toggle(category)">{{ category.is_visible ? '显示' : '隐藏' }}</button></td>
            <td class="actions">
              <button class="btn ghost sm" type="button" @click="openEdit(category)">编辑</button>
              <button class="btn ghost sm" type="button" :disabled="category.product_count > 0" @click="pendingDelete = category">删除</button>
            </td>
          </tr>
          <tr v-if="!loading && !categories.length"><td colspan="5" class="empty">还没有分类。保存商品时会按分类名自动创建。</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <Modal v-if="editing" :title="form.id ? '编辑分类' : '新建分类'" @close="editing = false" @submit="save">
    <div class="form-grid">
      <label class="span-2">名称<input v-model="form.name" required maxlength="100" /></label>
      <label>排序<input v-model.number="form.sort_order" type="number" min="0" /></label>
      <label class="check"> <input v-model="form.is_visible" type="checkbox" />在机器人中显示</label>
    </div>
    <template #footer>
      <button type="button" class="btn ghost" @click="editing = false">取消</button>
      <button class="btn primary" :disabled="busy">保存</button>
    </template>
  </Modal>

  <ConfirmDialog
    v-if="pendingDelete"
    title="删除分类"
    :message="`删除分类「${pendingDelete.name}」？分类下还有商品时不能删除。`"
    confirm-text="删除"
    danger
    :loading="busy"
    @cancel="pendingDelete = null"
    @confirm="remove"
  />
</template>
