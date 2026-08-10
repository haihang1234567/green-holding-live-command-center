import { SNAPSHOTS } from '../utils'
export default function SnapshotSelect({ value, onChange, compact=false }) {
  return <label className={`snapshot-select ${compact ? 'compact':''}`}>
    {!compact && <span>Mốc hoàn/hủy</span>}
    <select value={value} onChange={e=>onChange(e.target.value)}>
      {SNAPSHOTS.map(([v,l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  </label>
}
