<script setup>
defineProps({
  title: { type: String, required: true },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确认' },
  danger: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
})
defineEmits(['confirm', 'cancel'])
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('cancel')">
    <form class="modal modal-sm" @submit.prevent="$emit('confirm')">
      <header class="modal-head">
        <h3>{{ title }}</h3>
        <button type="button" class="icon-btn" aria-label="关闭" @click="$emit('cancel')">×</button>
      </header>
      <div class="modal-body">
        <p v-if="message" class="dialog-copy">{{ message }}</p>
        <slot />
      </div>
      <footer class="modal-foot">
        <button type="button" class="btn ghost" @click="$emit('cancel')">取消</button>
        <button class="btn" :class="danger ? 'danger' : 'primary'" :disabled="loading">{{ confirmText }}</button>
      </footer>
    </form>
  </div>
</template>
