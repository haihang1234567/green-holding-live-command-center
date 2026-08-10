import { Activity, CircleDollarSign, Clock3, Megaphone, PackageCheck, Radio, ReceiptText, RotateCcw, ShoppingCart, TrendingUp } from 'lucide-react'
import { duration, money, number, percent } from '../lib/format'
import { useNavigate } from 'react-router-dom'

export function KpiCard({label,value,sub,kind='default'}:{label:string,value:string,sub?:string,kind?:string}){
  return <div className={`kpi-card ${kind}`}><small>{label}</small><strong>{value}</strong>{sub&&<span>{sub}</span>}</div>
}

export function ChannelCard({channel}:{channel:any}){
  const navigate=useNavigate(); const s=channel.session
  return <article className={`channel-card ${channel.status==='LIVE'?'live':''}`}>
    <div className="channel-head"><div><div className="eyebrow">{channel.name}</div><h3>{channel.handle||'Chưa gán handle'}</h3></div><div className={`status ${channel.status==='LIVE'?'live':''}`}><span/>{channel.status==='LIVE'?'ĐANG LIVE':'OFFLINE'}</div></div>
    {s?<><div className="channel-meta"><div><b>{s.team_name}</b><small>Team</small></div><div><b>{s.shift==='CA_SANG'?'Ca sáng':'Ca tối'}</b><small>Ca</small></div><div><b>{duration(s.duration_seconds)}</b><small>LIVE time</small></div></div><div className="channel-kpis"><div><small>GMV</small><b>{money(s.gmv)}</b></div><div><small>Orders</small><b>{number(s.orders)}</b></div><div><small>Ads</small><b>{money(s.ads_spend)}</b></div><div><small>ROAS</small><b>{s.roas?.toFixed?.(1)||'0.0'}</b></div></div><button className="link-button" onClick={()=>navigate(`/sessions/${s.id}`)}>Mở phiên LIVE →</button></>:<div className="offline-content"><Radio size={36}/><div><b>Chưa có phiên LIVE</b><span>Sẵn sàng nhận tín hiệu từ provider</span></div></div>}
  </article>
}
