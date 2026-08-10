import { useCallback, useEffect, useState } from 'react'
import { api, connectDashboardWS } from '../lib/api'
import { duration, money, number } from '../lib/format'
import { Bell, BellRing, Radio, RefreshCw, ShieldCheck, Wifi } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function LiveControl(){
 const [channels,setChannels]=useState<any[]>([])
 const [msg,setMsg]=useState('')
 const [notify,setNotify]=useState(typeof Notification!=='undefined'?Notification.permission:'unsupported')
 const load=useCallback(()=>api('/dashboard/overview').then((d:any)=>setChannels(d.channels)),[])

 useEffect(()=>{
   load()
   const stop=connectDashboardWS((event,payload)=>{
     if(event==='channel.status'){
       load()
       const title=payload.status==='LIVE'?'🔴 PHÁT HIỆN LIVE':'⏹️ LIVE ĐÃ KẾT THÚC'
       const body=`Kênh ${payload.channel_id} • hệ thống đã ${payload.status==='LIVE'?'tự tạo phiên và bắt đầu ghi nhận số liệu':'tự chốt phiên và chuyển sang theo dõi hoàn/hủy'}`
       setMsg(`${title} • ${body}`)
       if(typeof Notification!=='undefined'&&Notification.permission==='granted') new Notification(title,{body})
     }
     if(event==='session.updated') load()
   })
   const poll=setInterval(load,30000)
   return()=>{stop();clearInterval(poll)}
 },[load])

 async function enableNotifications(){
   if(typeof Notification==='undefined'){setMsg('Trình duyệt này không hỗ trợ thông báo desktop');return}
   const p=await Notification.requestPermission();setNotify(p)
   setMsg(p==='granted'?'Đã bật thông báo LIVE trên trình duyệt':'Chưa được cấp quyền thông báo')
 }

 return <>
  <div className="page-title"><div><span className="section-kicker">AUTOMATIC LIVE MONITOR</span><h2>Giám sát LIVE 2 Shop</h2><p>Không phát LIVE từ dashboard. TikTok bắt đầu/kết thúc LIVE ở bên ngoài; server tự kiểm tra tín hiệu mỗi 3 phút và tự tạo/chốt phiên.</p></div><div className="page-actions"><button className="secondary" onClick={load}><RefreshCw size={15}/>Làm mới</button><button className="primary" onClick={enableNotifications}>{notify==='granted'?<BellRing size={15}/>:<Bell size={15}/>} {notify==='granted'?'Thông báo đã bật':'Bật thông báo'}</button></div></div>
  {msg&&<div className="notice">{msg}</div>}

  <section className="panel live-monitor-info"><div className="panel-head"><div><span className="section-kicker">SERVER WORKFLOW</span><h3>Luồng tự động</h3></div><span className="mode-badge real">3 PHÚT / LẦN</span></div><div className="optional-grid"><div><Wifi size={18}/><small>1. DETECT</small><b>Kiểm tra trạng thái LIVE từng shop</b></div><div><Radio size={18}/><small>2. START</small><b>Tự tạo session khi phát hiện LIVE</b></div><div><RefreshCw size={18}/><small>3. SYNC</small><b>Đồng bộ GMV • đơn • Ads mỗi 180s</b></div><div><ShieldCheck size={18}/><small>4. END</small><b>Tự chốt phiên khi TikTok OFFLINE</b></div><div><Bell size={18}/><small>5. REFUND</small><b>T+0 • 1H • 3H • 6H • 12H • 24H • 48H • FINAL</b></div></div></section>

  <div className="cards-2">{channels.map((ch:any)=><article className={`panel mock-card ${ch.status==='LIVE'?'live':''}`} key={ch.id}>
    <div className="panel-head"><div><span className="section-kicker">{ch.id===1?'SHOP 1':'SHOP 2'} • {ch.name}</span><h3>{ch.handle}</h3></div><span className={`badge ${ch.status.toLowerCase()}`}>{ch.status==='LIVE'?'ĐANG LIVE':'OFFLINE'}</span></div>
    {ch.session?<>
      <div className="notice success-notice">🔴 Đã bắt được tín hiệu LIVE • hệ thống đang tự ghi nhận dữ liệu</div>
      <div className="mock-stats"><div><small>TEAM</small><b>{ch.session.team_name}</b></div><div><small>LIVE TIME</small><b>{duration(ch.session.duration_seconds)}</b></div><div><small>GMV</small><b>{money(ch.session.gmv)}</b></div><div><small>ORDERS</small><b>{number(ch.session.orders)}</b></div></div>
      <div className="inline-actions"><Link className="primary action-link" to={`/sessions/${ch.session.id}`}>Xem phiên đang ghi nhận</Link></div>
    </>:<div className="offline-content"><Radio size={32}/><div><b>Đang chờ tín hiệu LIVE từ TikTok</b><span>Không cần thao tác trên dashboard • server kiểm tra độc lập shop này mỗi 3 phút</span></div></div>}
  </article>)}</div>
 </>
}
