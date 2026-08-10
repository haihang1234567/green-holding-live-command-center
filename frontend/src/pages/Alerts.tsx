import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { dt } from '../lib/format'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'

export default function Alerts(){const[rows,setRows]=useState<any[]>([]);const load=()=>api('/alerts').then(setRows);useEffect(()=>{load()},[]);async function ack(id:number){await api(`/alerts/${id}/ack`,{method:'POST'});load()}return <><div className="page-title"><div><span className="section-kicker">ALERT CENTER</span><h2>Cảnh báo</h2><p>LIVE start/end, GMV velocity, Ads/GMV, Refund và lỗi tích hợp</p></div></div><div className="panel"><div className="alert-full-list">{rows.map(x=><div className={`alert-full ${x.severity?.toLowerCase()}`} key={x.id}><div className="alert-icon"><AlertTriangle size={18}/></div><div><b>{x.title}</b><p>{x.message}</p><small>{dt(x.created_at)} • {x.type}</small></div>{x.acknowledged?<span className="ack"><CheckCircle2 size={14}/>Đã xử lý</span>:<button className="secondary" onClick={()=>ack(x.id)}>Đánh dấu đã xem</button>}</div>)}</div></div></>}
