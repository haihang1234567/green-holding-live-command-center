import { Bell, Wifi } from 'lucide-react'
export default function AdminHeader({ title, subtitle, right }) {
  return <header className="page-header"><div><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div><div className="page-header-right">{right}<span className="header-chip"><Wifi size={15}/> Realtime</span><span className="header-icon"><Bell size={18}/></span></div></header>
}
