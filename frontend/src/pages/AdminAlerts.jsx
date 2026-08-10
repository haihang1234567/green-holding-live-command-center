import { useEffect,useState } from 'react'
import { api } from '../api'
import { when } from '../utils'
import AdminHeader from '../components/AdminHeader'
export default function AdminAlerts(){const [rows,setRows]=useState([]);const load=()=>api.alerts().then(setRows);useEffect(()=>{load()},[]);return <><AdminHeader title="Cảnh báo" subtitle="LIVE start, Ads, hoàn/hủy và KPI bất thường"/><div className="alert-page">{rows.map(a=><div className={`alert-card sev-${a.severity.toLowerCase()} ${a.acknowledged?'ack':''}`} key={a.id}><div><span className="alert-type">{a.type}</span><h3>{a.title}</h3><p>{a.message}</p><small>{when(a.created_at)}</small></div>{!a.acknowledged&&<button className="secondary-btn" onClick={async()=>{await api.ackAlert(a.id);load()}}>Đã xử lý</button>}</div>)}</div></>}
