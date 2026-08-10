export default function StatusPill({ status }) {
  const s = String(status || 'OFFLINE').toUpperCase()
  return <span className={`status-pill status-${s.toLowerCase()}`}><i />{s === 'LIVE' ? 'ĐANG LIVE' : s === 'ENDED' ? 'ĐÃ KẾT THÚC' : s === 'UNKNOWN' ? 'CHƯA CÓ DỮ LIỆU' : 'OFFLINE'}</span>
}
