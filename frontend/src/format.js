export function money(value) {
  if (value === null || value === undefined || value === '') return '0'
  const text = String(value)
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text
  if (!text.includes('.')) return text
  return text.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
}

export function moneyInput(value) {
  return money(value ?? '0')
}

export function formatDate(value) {
  if (!value) return '—'
  const raw = String(value)
  const date = new Date(raw.endsWith('Z') || raw.includes('+') ? raw : `${raw}Z`)
  if (Number.isNaN(date.getTime())) return raw
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

export function customerLabel(username, telegramId, firstName) {
  if (username) return `@${username}`
  if (firstName) return firstName
  return String(telegramId ?? '—')
}
