<script setup>
defineProps({
  title: { type: String, required: true },
  wide: { type: Boolean, default: false },
})
defineEmits(['close', 'submit'])
</script>

<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <form class="modal" :class="{ wide }" @submit.prevent="$emit('submit')">
      <header class="modal-head">
        <h3>{{ title }}</h3>
        <button type="button" class="icon-btn" aria-label="关闭" @click="$emit('close')">×</button>
      </header>
      <div class="modal-body">
        <slot />
      </div>
      <footer v-if="$slots.footer" class="modal-foot">
        <slot name="footer" />
      </footer>
    </form>
  </div>
</template>
