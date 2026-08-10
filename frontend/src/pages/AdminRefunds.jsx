import { useEffect,useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { money,pct } from '../utils'
import AdminHeader from '../components/AdminHeader'
import SnapshotSelect from '../components/SnapshotSelect'
export default function AdminRefunds(){const [rows,setRows]=useState([]),[snapshot,setSnapshot]=useState('T3H');useEffect(()=>{api.sessions(snapshot).then(setRows)},[snapshot]);return <><AdminHeader title="Hoàn / Hủy" subtitle="Chọn mốc đánh giá, số cũ vẫn được lưu độc lập" right={<SnapshotSelect value={snapshot} onChange={setSnapshot} compact/>}/><section className="panel"><div className="table-wrap"><table><thead><tr><th>Session</th><th>Team</th><th>GMV ban đầu</th><th>Mốc</th><th>Tỷ lệ hoàn/hủy</th><th>Doanh thu giữ</th><th></th></tr></thead><tbody>{rows.map(s=><tr key={s.id}><td><b>{s.session_code}</b></td><td>{s.team_name}</td><td>{money(s.metrics.gmv)}</td><td><span className="mini-tag">{snapshot}</span></td><td><b className={s.metrics.refund_rate>20?'danger-text':''}>{pct(s.metrics.refund_rate)}</b></td><td>{money(s.metrics.net_revenue)}</td><td><Link className="text-link" to={`/admin/sessions/${s.id}`}>So sánh các mốc →</Link></td></tr>)}</tbody></table></div></section></>}
