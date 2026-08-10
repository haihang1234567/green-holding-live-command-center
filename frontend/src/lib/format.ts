export const money = (n?: number | null) => n == null ? 'Chưa có dữ liệu' : `${Math.round(n).toLocaleString('vi-VN')}đ`
export const number = (n?: number | null) => n == null ? 'Chưa có dữ liệu' : Math.round(n).toLocaleString('vi-VN')
export const percent = (n?: number | null, digits = 2) => n == null ? 'Chưa có dữ liệu' : `${n.toLocaleString('vi-VN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`
export const compactMoney = (n?: number | null) => {
  if (n == null) return '—'
  if (Math.abs(n) >= 1e9) return `${(n/1e9).toLocaleString('vi-VN',{maximumFractionDigits:1})}B`
  if (Math.abs(n) >= 1e6) return `${(n/1e6).toLocaleString('vi-VN',{maximumFractionDigits:1})}M`
  return money(n)
}
export const duration = (seconds?: number | null) => {
  const s = Math.max(0, Math.floor(seconds || 0)); const h = Math.floor(s/3600); const m = Math.floor((s%3600)/60); const r=s%60
  return [h,m,r].map(x=>String(x).padStart(2,'0')).join(':')
}
export const dt = (iso?: string | null) => iso ? new Date(iso).toLocaleString('vi-VN') : '—'
