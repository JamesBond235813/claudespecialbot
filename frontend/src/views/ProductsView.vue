<script setup>
import { inject, onMounted, reactive, ref } from 'vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Modal from '../components/Modal.vue'
import { money, moneyInput } from '../format.js'

const request = inject('request')
const products = ref([])
const categories = ref([])
const error = ref('')
const loading = ref(true)
const editing = ref(false)
const busy = ref(false)
const pendingDelete = ref(null)

const emptyForm = () => ({
  name: '',
  category: '默认分类',
  description: '',
  deposit_usdt: '0',
  total_usdt: '0',
  stock_quantity: '',
  delivery_note: '次日人工交付',
  is_active: true,
  sort_order: 0,
})
const form = reactive(emptyForm())

function fill(product) {
  Object.assign(form, {
    id: product.id,
    name: product.name,
    category: product.category,
    description: product.description,
    deposit_usdt: moneyInput(product.deposit_usdt),
    total_usdt: moneyInput(product.total_usdt),
    stock_quantity: product.stock_quantity == null ? '' : String(product.stock_quantity),
    delivery_note: product.delivery_note,
    is_active: product.is_active,
    sort_order: product.sort_order || 0,
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [productRes, categoryRes] = await Promise.all([
      request('/api/admin/products'),
      request('/api/admin/categories'),
    ])
    products.value = productRes.data
    categories.value = categoryRes.data
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, emptyForm(), { id: null })
  editing.value = true
}

function openEdit(product) {
  fill(product)
  editing.value = true
}

function payload() {
  return {
    name: form.name,
    category: form.category,
    description: form.description,
    deposit_usdt: form.deposit_usdt === '' ? '0' : String(form.deposit_usdt),
    total_usdt: form.total_usdt === '' ? '0' : String(form.total_usdt),
    stock_quantity: form.stock_quantity === '' ? null : Number(form.stock_quantity),
    delivery_note: form.delivery_note,
    is_active: form.is_active,
    sort_order: Number(form.sort_order || 0),
  }
}

async function save() {
  busy.value = true
  error.value = ''
  try {
    if (form.id) {
      await request(`/api/admin/products/${form.id}`, { method: 'PATCH', body: JSON.stringify(payload()) })
    } else {
      await request('/api/admin/products', { method: 'POST', body: JSON.stringify(payload()) })
    }
    editing.value = false
    await load()
  } catch (err) {
    error.value = err.message
  } finally {
    busy.value = false
  }
}

async function toggle(product) {
  error.value = ''
  try {
    await request(`/api/admin/products/${product.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: !product.is_active }),
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
    await request(`/api/admin/products/${pendingDelete.value.id}`, { method: 'DELETE' })
    pendingDelete.value = null
    await load()
  } catch (err) {
    error.value = err.message
    pendingDelete.value = null
  } finally {
    busy.value = false
  }
}

function stockText(product) {
  return product.stock_quantity == null ? '不限' : String(product.stock_quantity)
}

onMounted(load)
</script>

<template>
  <div class="toolbar">
    <span class="muted">{{ products.length }} 个商品</span>
    <button class="btn primary" type="button" @click="openCreate">新建商品</button>
  </div>
  <p v-if="error" class="alert">{{ error }}</p>
  <section class="card">
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>排序</th><th>商品</th><th>分类</th><th>价格</th><th>定金</th><th>库存</th><th>状态</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="8" class="empty">正在加载…</td></tr>
          <tr v-for="product in products" :key="product.id">
            <td>{{ product.sort_order }}</td>
            <td><b>{{ product.name }}</b><small>{{ product.delivery_note }}</small></td>
            <td>{{ product.category }}</td>
            <td>{{ money(product.total_usdt) }} USDT</td>
            <td>{{ money(product.deposit_usdt) }} USDT</td>
            <td>{{ stockText(product) }}</td>
            <td><button class="pill" :class="{ off: !product.is_active }" type="button" @click="toggle(product)">{{ product.is_active ? '在售' : '停用' }}</button></td>
            <td class="actions">
              <button class="btn ghost sm" type="button" @click="openEdit(product)">编辑</button>
              <button class="btn ghost sm" type="button" @click="pendingDelete = product">删除</button>
            </td>
          </tr>
          <tr v-if="!loading && !products.length"><td colspan="8" class="empty">还没有商品。</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <Modal v-if="editing" :title="form.id ? '编辑商品' : '新建商品'" wide @close="editing = false" @submit="save">
    <div class="form-grid">
      <label>名称<input v-model="form.name" required maxlength="255" /></label>
      <label>分类
        <input v-model="form.category" required maxlength="100" list="category-names" />
        <datalist id="category-names"><option v-for="item in categories" :key="item.id" :value="item.name" /></datalist>
      </label>
      <label class="span-2">说明<textarea v-model="form.description" required rows="4" maxlength="4000"></textarea></label>
      <label>总价 USDT<input v-model="form.total_usdt" inputmode="decimal" required /></label>
      <label>定金 USDT<input v-model="form.deposit_usdt" inputmode="decimal" required /></label>
      <label>库存<input v-model="form.stock_quantity" type="number" min="0" placeholder="留空表示不限" /></label>
      <label>排序<input v-model.number="form.sort_order" type="number" min="0" /></label>
      <label class="span-2">交付说明<input v-model="form.delivery_note" maxlength="500" /></label>
      <label class="check span-2"><input v-model="form.is_active" type="checkbox" />上架销售</label>
    </div>
    <template #footer>
      <button type="button" class="btn ghost" @click="editing = false">取消</button>
      <button class="btn primary" :disabled="busy">保存</button>
    </template>
  </Modal>

  <ConfirmDialog
    v-if="pendingDelete"
    title="删除商品"
    :message="`删除「${pendingDelete.name}」？已有订单的商品不能删除，只能停用。`"
    confirm-text="删除"
    danger
    :loading="busy"
    @cancel="pendingDelete = null"
    @confirm="remove"
  />
</template>
