<script setup>
import { stateLabel } from '../labels.js'

defineProps({ status: { type: String, required: true } })
</script>

<template>
  <span class="badge" :data-status="status">{{ stateLabel(status) }}</span>
</template>
