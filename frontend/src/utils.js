export const money = (v) => `${new Intl.NumberFormat('vi-VN').format(Number(v || 0))} ₫`
export const num = (v) => new Intl.NumberFormat('vi-VN').format(Number(v || 0))
export const pct = (v) => `${Number(v || 0).toFixed(2).replace('.', ',')}%`
export const duration = (seconds=0) => {
  const h = Math.floor(seconds/3600), m = Math.floor((seconds%3600)/60), s = seconds%60
  return [h,m,s].map(x=>String(x).padStart(2,'0')).join(':')
}
export const when = (date) => date ? new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'short'}).format(new Date(date)) : '—'
export const SNAPSHOTS = [
  ['T0','Ngay sau LIVE'], ['T1H','Sau 1 giờ'], ['T3H','Sau 3 giờ'], ['T6H','Sau 6 giờ'],
  ['T12H','Sau 12 giờ'], ['T24H','Sau 24 giờ'], ['T48H','Sau 48 giờ'], ['FINAL','Final']
]
