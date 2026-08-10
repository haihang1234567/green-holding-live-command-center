export default function KpiCard({ label, value, hint, tone='default', compact=false }) {
  return <div className={`kpi-card tone-${tone} ${compact ? 'compact' : ''}`}>
    <div className="kpi-label">{label}</div>
    <div className="kpi-value">{value ?? 'Chưa có dữ liệu'}</div>
    {hint && <div className="kpi-hint">{hint}</div>}
  </div>
}
