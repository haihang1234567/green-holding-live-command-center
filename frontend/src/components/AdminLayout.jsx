import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Radio, List, Trophy, RotateCcw, Bell, FlaskConical, Settings, LogOut } from 'lucide-react'
import { clearSession } from '../api'

const nav = [
  ['/admin', LayoutDashboard, 'Tổng quan', true],
  ['/admin/sessions', List, 'Phiên LIVE'],
  ['/admin/ranking', Trophy, 'Xếp hạng team'],
  ['/admin/refunds', RotateCcw, 'Hoàn / Hủy'],
  ['/admin/alerts', Bell, 'Cảnh báo'],
  ['/admin/mock', FlaskConical, 'Mock Control'],
  ['/admin/api', Settings, 'API & Hệ thống'],
]

export default function AdminLayout() {
  const navigate = useNavigate()
  return <>
    <div className="admin-mobile-block">
      <div><Radio size={34}/><h2>Admin dùng trên máy tính</h2><p>Màn hình quản trị được tối ưu cho desktop từ 1100px trở lên.</p></div>
    </div>
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand"><span className="brand-mark">LC</span><div><b>Live Command</b><small>Admin Console</small></div></div>
        <nav>{nav.map(([to,Icon,label,end]) => <NavLink key={to} to={to} end={end} className={({isActive})=>isActive?'active':''}><Icon size={18}/><span>{label}</span></NavLink>)}</nav>
        <button className="logout" onClick={()=>{clearSession(); navigate('/login')}}><LogOut size={18}/>Đăng xuất</button>
      </aside>
      <main className="admin-main"><Outlet/></main>
    </div>
  </>
}
