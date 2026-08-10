import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { dt, duration, money, number, percent } from '../lib/format'
import { Link } from 'react-router-dom'

export default function Sessions(){
  const [rows,setRows]=useState<any[]>([]); const [status,setStatus]=useState('')
  useEffect(()=>{api(`/sessions${status?`?status=${status}`:''}`).then(setRows)},[status])
  return <><div className="page-title"><div><span className="section-kicker">LIVE SESSIONS</span><h2>Lịch sử phiên LIVE</h2><p>Tất cả phiên theo kênh, team, ca và trạng thái</p></div><div className="page-actions"><select value={status} onChange={e=>setStatus(e.target.value)}><option value="">Tất cả trạng thái</option><option>LIVE</option><option>ENDED</option></select></div></div><div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Session</th><th>Team</th><th>Kênh</th><th>Ca</th><th>Trạng thái</th><th>Bắt đầu</th><th>Thời lượng</th><th>GMV</th><th>Orders</th><th>Ads</th><th>Refund</th><th></th></tr></thead><tbody>{rows.map(x=><tr key={x.id}><td><b>{x.session_code}</b></td><td>{x.team_name}</td><td>{x.channel_name}</td><td>{x.shift==='CA_SANG'?'Ca sáng':'Ca tối'}</td><td><span className={`badge ${x.status.toLowerCase()}`}>{x.status}</span></td><td>{dt(x.started_at)}</td><td>{duration(x.duration_seconds)}</td><td>{money(x.gmv)}</td><td>{number(x.orders)}</td><td>{money(x.ads_spend)}</td><td>{percent(x.refund_rate)}</td><td><Link to={`/sessions/${x.id}`}>Mở →</Link></td></tr>)}</tbody></table></div></div></>
}
