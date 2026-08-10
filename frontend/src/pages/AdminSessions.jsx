import { useEffect,useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { money,num,when } from '../utils'
import AdminHeader from '../components/AdminHeader'
import SnapshotSelect from '../components/SnapshotSelect'
import StatusPill from '../components/StatusPill'

export default function AdminSessions(){const [rows,setRows]=useState([]),[snapshot,setSnapshot]=useState('T3H');useEffect(()=>{api.sessions(snapshot).then(setRows)},[snapshot]);return <><AdminHeader title="Phiên LIVE" subtitle="Lịch sử và trạng thái tất cả phiên" right={<SnapshotSelect value={snapshot} onChange={setSnapshot} compact/>}/><div className="panel"><div className="table-wrap"><table><thead><tr><th>Session</th><th>Kênh</th><th>Team</th><th>Ca</th><th>Bắt đầu</th><th>Trạng thái</th><th>GMV</th><th>Đơn</th><th>Hoàn/Hủy</th><th>Net Revenue</th><th></th></tr></thead><tbody>{rows.map(s=><tr key={s.id}><td><b>{s.session_code}</b></td><td>{s.channel_name}</td><td>{s.team_name}</td><td>{s.shift==='MORNING'?'Sáng':'Tối'}</td><td>{when(s.started_at)}</td><td><StatusPill status={s.status}/></td><td>{money(s.metrics.gmv)}</td><td>{num(s.metrics.orders)}</td><td>{s.metrics.refund_rate.toFixed(2)}%</td><td><b>{money(s.metrics.net_revenue)}</b></td><td><Link className="text-link" to={`/admin/sessions/${s.id}`}>Chi tiết →</Link></td></tr>)}</tbody></table></div></div></>}
