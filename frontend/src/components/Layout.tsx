import { Bell, ChartNoAxesCombined, FlaskConical, History, LayoutDashboard, Megaphone, Package, Radio, RefreshCcw, Settings, ShieldCheck, ShoppingCart, Trophy, Users, X, Menu } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { connectDashboardWS, logout, user } from '../lib/api'
import { useEffect, useState } from 'react'

const items = [
  ['/', 'Tổng quan', LayoutDashboard], ['/live','Giám sát LIVE',Radio], ['/sessions','Phiên LIVE',History], ['/teams','Teams',Trophy], ['/channels','Kênh TikTok',Radio],
  ['/orders','Đơn hàng',ShoppingCart], ['/products','Sản phẩm',Package], ['/ads','Ads',Megaphone], ['/refunds','Hoàn/Hủy',RefreshCcw],
  ['/reports','Báo cáo',ChartNoAxesCombined], ['/alerts','Cảnh báo',Bell], ['/users','Người dùng',Users], ['/mock','Mock Control',FlaskConical], ['/settings','Cấu hình API',Settings],
] as const

export default function Layout(){
  const me = user(); const navigate=useNavigate(); const [open,setOpen]=useState(false); const [clock,setClock]=useState(new Date()); const [toast,setToast]=useState('')
  useEffect(()=>{ const x=setInterval(()=>setClock(new Date()),1000); return()=>clearInterval(x)},[])
  useEffect(()=>{
    const stop=connectDashboardWS((event,payload)=>{
      if(event!=='channel.status') return
      const started=payload.status==='LIVE'
      const title=started?'🔴 PHÁT HIỆN LIVE':'⏹️ LIVE ĐÃ KẾT THÚC'
      const body=`Shop/Kênh ${payload.channel_id} • ${started?'đã tự tạo phiên và bắt đầu ghi nhận số liệu':'đã final-sync, chốt phiên và tạo T+0'}`
      setToast(`${title} — ${body}`)
      window.setTimeout(()=>setToast(''),9000)
      if(typeof Notification!=='undefined'&&Notification.permission==='granted') new Notification(title,{body})
    })
    return stop
  },[])
  return <div className="app-shell">
    <aside className={`sidebar ${open?'open':''}`}>
      <div className="brand"><div className="brand-mark">G</div><div><strong>GREEN HOLDING</strong><span>LIVE COMMAND CENTER</span></div><button className="mobile-close" onClick={()=>setOpen(false)}><X size={18}/></button></div>
      <nav>{items.filter(([path])=>me?.role==='ADMIN'||!['/mock','/settings','/users'].includes(path)).map(([path,label,Icon])=><NavLink key={path} to={path} end={path==='/'} onClick={()=>setOpen(false)}><Icon size={16}/><span>{label}</span></NavLink>)}</nav>
      <div className="side-bottom"><div className="user-card"><ShieldCheck size={16}/><div><b>{me?.team_name || me?.username}</b><small>{me?.role}</small></div></div><button onClick={()=>{logout();navigate('/login')}}>Đăng xuất</button></div>
    </aside>
    {open&&<div className="overlay" onClick={()=>setOpen(false)}/>} 
    <main className="main">
      <header className="topbar"><div className="top-left"><button className="menu" onClick={()=>setOpen(true)}><Menu size={20}/></button><div><h1>LIVE COMMAND CENTER</h1><p>Giám sát 2 TikTok Shop • tự động phát hiện LIVE • đồng bộ 3 phút/lần</p></div></div><div className="top-actions"><div className="api-pill"><span/><div><b>BACKEND ONLINE</b><small>WebSocket + API</small></div></div><div className="clock"><b>{clock.toLocaleTimeString('vi-VN')}</b><small>{clock.toLocaleDateString('vi-VN')}</small></div><div className="avatar">{(me?.team_name||me?.username||'AD').split(' ').map(x=>x[0]).join('').slice(0,2).toUpperCase()}</div></div></header>
      {toast&&<div className="global-live-toast">{toast}</div>}
      <div className="content"><Outlet/></div>
    </main>
  </div>
}
