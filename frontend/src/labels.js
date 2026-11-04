export const ORDER_STATES = [
  'RESERVED',
  'DEPOSIT_PENDING',
  'DEPOSIT_PAID',
  'PREPARING',
  'READY',
  'DELIVERING',
  'COMPLETED',
  'CANCELLED',
  'EXPIRED',
  'REFUND_PENDING',
  'REFUNDED',
  'DISPUTED',
  'DELIVERY_FAILED',
]

export const STATE_LABELS = {
  RESERVED: '已预约',
  DEPOSIT_PENDING: '待定金',
  DEPOSIT_PAID: '定金已付',
  PREPARING: '准备中',
  READY: '待交付',
  DELIVERING: '交付中',
  COMPLETED: '已完成',
  CANCELLED: '已取消',
  EXPIRED: '已过期',
  REFUND_PENDING: '待退款',
  REFUNDED: '已退款',
  DISPUTED: '争议中',
  DELIVERY_FAILED: '交付失败',
}

export function stateLabel(status) {
  return STATE_LABELS[status] || status || '—'
}

export function actorLabel(actor) {
  if (!actor) return '系统'
  if (actor === 'admin-api') return '后台'
  if (actor.startsWith('telegram:')) return `客户 ${actor.slice('telegram:'.length)}`
  return actor
}

export const PAYMENT_LABELS = {
  PENDING: '待处理',
  SUCCEEDED: '已到账',
  REFUNDED: '已退款',
  FAILED: '失败',
}

export function stageLabel(stage) {
  if (stage === 'balance') return '尾款'
  if (stage === 'deposit') return '定金'
  return stage || '—'
}
