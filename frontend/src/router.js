import { onMounted, onUnmounted, ref } from 'vue'

const NAMES = new Set([
  'dashboard',
  'orders',
  'payments',
  'products',
  'categories',
  'customers',
  'campaigns',
  'settings',
])

function parseHash() {
  const raw = (location.hash || '#/dashboard').replace(/^#/, '')
  const path = raw.startsWith('/') ? raw : `/${raw}`
  const parts = path.split('/').filter(Boolean)
  const name = NAMES.has(parts[0]) ? parts[0] : 'dashboard'
  return { name, id: parts[1] || '' }
}

export function useHashRoute() {
  const route = ref(parseHash())

  function sync() {
    route.value = parseHash()
  }

  function go(path) {
    const next = `#/${String(path).replace(/^#?\//, '')}`
    if (location.hash === next) sync()
    else location.hash = next
  }

  onMounted(() => {
    if (!location.hash) location.replace('#/dashboard')
    window.addEventListener('hashchange', sync)
  })
  onUnmounted(() => window.removeEventListener('hashchange', sync))

  return { route, go }
}
