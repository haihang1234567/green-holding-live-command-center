import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { dt, money, percent } from '../lib/format'
import { Link } from 'react-router-dom'

export default function Refunds(){const[rows,setRows]=useState<any[]>([]);useEffect(()=>{api('/sessions?status=ENDED').then(setRows)},[]);return <><div className="page-title"><div><span className="section-kicker">REFUND / CANCEL</span><h2>Hoàn / Hủy</h2><p>Snapshot được lưu theo từng mốc, không ghi đè số cũ.</p></div></div><div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Session</th><th>Team</th><th>Kênh</th><th>Kết thúc</th><th>GMV gốc</th><th>Refund/Cancel hiện tại</th><th>Net revenue</th><th></th></tr></thead><tbody>{rows.map(x=><tr key={x.id}><td><b>{x.session_code}</b></td><td>{x.team_name}</td><td>{x.channel_name}</td><td>{dt(x.ended_at)}</td><td>{money(x.gmv)}</td><td>{percent(x.refund_rate)}</td><td>{money(x.net_revenue)}</td><td><Link to={`/sessions/${x.id}`}>Xem snapshots →</Link></td></tr>)}</tbody></table></div></div></>}
