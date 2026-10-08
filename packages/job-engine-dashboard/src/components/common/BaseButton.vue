<template>
  <component :is="tag" class="btn" :class="classes" :disabled="disabled || loading">
    <span v-if="loading" class="btn-spinner" aria-hidden="true"></span>
    <slot v-if="!loading" />
  </component>
</template>

<script setup>
// Complete button component. All styles (base, variants, sizes, shapes,
// loading spinner, favorited states) are defined in scoped styles below.
import { computed } from 'vue'

const props = defineProps({
  // Colour or quiet variant: primary, secondary, success, danger,
  // soft-blue/green/red/orange/purple, link, ghost
  variant: { type: String, default: '' },
  // Size modifier: sm | xs
  size: { type: String, default: '' },
  // Shape / state modifiers
  icon: Boolean,
  block: Boolean,
  toggle: Boolean,
  dim: Boolean,
  disabled: Boolean,
  loading: Boolean,
  // Root element or component, e.g. 'button', 'a', 'router-link'
  tag: { type: [String, Object], default: 'button' },
})

const classes = computed(() => [
  props.variant && `btn--${props.variant}`,
  props.size && `btn--${props.size}`,
  props.icon && 'btn--icon',
  props.block && 'btn--block',
  props.toggle && 'btn--toggle',
  props.dim && 'btn--dim',
  props.loading && 'btn--loading',
])
</script>

<style scoped>
/* ── Base ─────────────────────────────────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  text-decoration: none;
  white-space: nowrap;
  vertical-align: middle;
  cursor: pointer;
  transition: all 0.15s;
}
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

/* ── Solid colour variants ────────────────────────────────────────────── */
.btn--primary { background: var(--primary); color: #fff; }
.btn--primary:hover:not(:disabled) { background: var(--primary-light); }
.btn--primary.running { background: var(--warning); }

/* Variants used exclusively by BaseButton (not by direct <button> elements) */
.btn--danger { background: var(--danger); color: #fff; border-color: var(--danger); }
.btn--danger:hover:not(:disabled) { background: #c53030; border-color: #c53030; }

.btn--secondary { background: var(--surface); color: var(--text); border-color: var(--border); }
.btn--secondary:hover:not(:disabled) { background: var(--bg); border-color: var(--text-secondary); }

.btn--success { background: var(--success); color: #fff; }
.btn--success:hover:not(:disabled) { background: #15803d; }

/* ── Soft (tinted) variants ──────────────────────────────────────────── */
.btn--soft-blue   { background: #e3f2fd; color: #1565c0; }
.btn--soft-blue:hover:not(:disabled) { filter: brightness(0.94); }
.btn--soft-red   { background: #fbe9e7; color: #c62828; }
.btn--soft-red:hover:not(:disabled) { filter: brightness(0.94); }

/* ── Quiet variants ───────────────────────────────────────────────────── */
.btn--ghost { background: transparent; border-color: transparent; color: var(--text-secondary); }
.btn--ghost:hover:not(:disabled) { background: transparent; color: var(--primary); }
.btn--ghost.active { color: var(--primary); }
.btn--ghost.btn--remove:hover:not(:disabled) { color: var(--danger); background: #fef2f2; }

/* ── Sizes ────────────────────────────────────────────────────────────── */
.btn--sm { padding: 4px 12px; font-size: 12px; }
.btn--xs { padding: 2px 8px; font-size: 11px; line-height: 1.4; }

/* ── Shapes ───────────────────────────────────────────────────────────── */
.btn--toggle {
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 500;
  background: var(--surface);
  color: var(--text-secondary);
  border-color: var(--border);
  border-radius: 6px;
}
.btn--toggle:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }
.btn--toggle.active { background: var(--primary); color: #fff; border-color: var(--primary); }

.btn--dim { opacity: 0.4; }
.btn--dim.active,
.btn--dim:hover:not(:disabled) { opacity: 1; }

.btn--icon {
  min-width: 28px;
  padding: 3px 8px;
  font-size: 14px;
  background: transparent;
  border-color: var(--border);
  color: var(--text-secondary);
}
.btn--icon:hover:not(:disabled) { background: var(--bg); border-color: var(--text-secondary); color: var(--text); }
.btn--icon svg { width: 14px; height: 14px; }
.btn--icon.favorited { background: #fefce8; border-color: var(--warning); color: #d97706; }

.btn--block {
  display: block;
  width: 100%;
  text-align: left;
  padding: 7px 12px;
  border-radius: 4px;
  font-weight: 500;
}

/* ── Loading / spinner ─────────────────────────────────────────────────── */
.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: btn-spin 0.6s linear infinite;
  flex-shrink: 0;
}
@keyframes btn-spin { to { transform: rotate(360deg); } }
.btn.running .btn-spinner,
.btn--loading .btn-spinner { display: inline-block; }
.btn--loading { pointer-events: none; opacity: 0.8; }

.btn--secondary.favorited { background: #fef3c7; border-color: var(--warning); color: #d97706; }
.btn--ghost.favorited { color: #d97706; }
</style>
