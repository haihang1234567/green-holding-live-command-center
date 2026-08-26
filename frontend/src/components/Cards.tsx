import { Activity, CircleDollarSign, Clock3, Megaphone, PackageCheck, Radio, ReceiptText, RotateCcw, ShoppingCart, TrendingUp } from 'lucide-react'
import { duration, money, number, percent } from '../lib/format'
import { useNavigate } from 'react-router-dom'

export function KpiCard({label,value,sub,kind='default'}:{label:string,value:string,sub?:string,kind?:string}){
  return <div className={`kpi-card ${kind}`}><small>{label}</small><strong>{value}</strong>{sub&&<span>{sub}</span>}</div>
}

export function ChannelCard({channel}:{channel:any}){
  const navigate=useNavigate(); const s=channel.session; const isLive=channel.status==='LIVE'
  return <article className={`channel-card ${channel.status==='LIVE'?'live':''}`}>
    <div className="channel-head"><div><div className="eyebrow">{channel.name}</div><h3>{channel.handle||'Chưa gán handle'}</h3></div><div className={`status ${isLive?'live':''}`}><span/>{isLive?'ĐANG LIVE':s?'BÁO CÁO TIKTOK':'CHƯA CÓ DỮ LIỆU'}</div></div>
    {s?<><div className="channel-meta"><div><b>TikTok API</b><small>Nguồn</small></div><div><b>{duration(s.duration_seconds)}</b><small>Thời lượng phiên</small></div></div><div className="channel-kpis"><div><small>GMV</small><b>{money(s.gmv)}</b></div><div><small>Đơn hàng</small><b>{number(s.orders)}</b></div></div><button className="link-button" onClick={()=>navigate(`/sessions/${s.id}`)}>Xem dữ liệu phiên →</button></>:<div className="offline-content"><Radio size={36}/><div><b>Chưa có báo cáo TikTok</b><span>Hệ thống tự kiểm tra lại sau mỗi 3 phút</span></div></div>}
  </article>
}
