<template>
  <div class="pf-edit-actions">
    <BaseButton variant="primary" size="sm" :disabled="saving" @click="$emit('save')">
      {{ saving ? 'Saving...' : 'Save' }}
    </BaseButton>
    <BaseButton variant="ghost" size="sm" :disabled="saving" @click="$emit('cancel')">Cancel</BaseButton>
  </div>
</template>

<script setup>
import BaseButton from '../common/BaseButton.vue'

defineProps({
  saving: { type: Boolean, default: false },
})
defineEmits(['save', 'cancel'])
</script>

<style scoped>
.pf-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border, var(--border, #e2e8f0));
}
</style>