import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api, connectRealtime } from '../api'
import { money, num, pct, duration } from '../utils'
import AdminHeader from '../components/AdminHeader'
import KpiCard from '../components/KpiCard'
import SnapshotSelect from '../components/SnapshotSelect'
import StatusPill from '../components/StatusPill'

export default function AdminDashboard(){
 const [data,setData]=useState(null),[snapshot,setSnapshot]=useState('T3H'),[error,setError]=useState('')
 const load=()=>api.overview(snapshot).then(setData).catch(e=>setError(e.message))
 useEffect(()=>{load();const stop=connectRealtime(()=>load());const id=setInterval(load,30000);return()=>{stop();clearInterval(id)}},[snapshot])
 if(!data)return <div className="page-loading">{error||'Đang tải dashboard...'}</div>
 const t=data.totals
 const rankChart=data.ranking.map(r=>({name:r.team_name,gmv:r.gmv,net:r.net_revenue}))
 return <div>
  <AdminHeader title="Tổng quan LIVE" subtitle="Theo dõi 2 kênh, 4 team và KPI trong một màn hình" right={<SnapshotSelect value={snapshot} onChange={setSnapshot} compact/>}/>
  <section className="channel-grid">{data.channels.map(c=><div className="channel-card" key={c.id}><div className="channel-head"><div><span className="eyebrow">KÊNH {String(c.id).padStart(2,'0')}</span><h3>{c.name}</h3></div><StatusPill status={c.status}/></div>{c.session?<><div className="channel-meta"><span><b>{c.session.team_name}</b><small>{c.session.shift==='MORNING'?'Ca sáng':'Ca tối'}</small></span><span><b>{duration(c.session.metrics.duration_seconds)}</b><small>Thời lượng</small></span></div><div className="channel-kpis"><span><small>GMV</small><b>{money(c.session.metrics.gmv)}</b></span><span><small>Đơn</small><b>{num(c.session.metrics.orders)}</b></span><span><small>Ads</small><b>{money(c.session.metrics.ads_spend)}</b></span><span><small>ROAS</small><b>{c.session.metrics.roas}</b></span></div></>:<div className="offline-space">Kênh đang không LIVE</div>}</div>)}</section>
  <section className="kpi-grid six"><KpiCard label="Tổng GMV" value={money(t.gmv)} hint="Tổng kỳ đang hiển thị"/><KpiCard label="Tổng đơn" value={num(t.orders)} hint={`AOV ${money(t.aov)}`}/><KpiCard label="Ads Spend" value={money(t.ads_spend)} hint={`${pct(t.ads_gmv_pct)} / GMV`}/><KpiCard label="ROAS" value={t.roas} hint="GMV / Ads"/><KpiCard label={`Hoàn/hủy ${snapshot}`} value={pct(t.refund_rate)} hint={`Net ${money(t.net_revenue)}`} tone="danger"/><KpiCard label="Team dẫn đầu" value={data.ranking[0]?.team_name||'—'} hint={data.ranking[0]?money(data.ranking[0].net_revenue):''} tone="good"/></section>
  <section className="dashboard-two"><div className="panel"><div className="panel-title"><div><h3>So sánh doanh thu 4 team</h3><p>GMV và doanh thu giữ lại theo mốc hoàn/hủy</p></div></div><div className="chart-box"><ResponsiveContainer width="100%" height="100%"><BarChart data={rankChart}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name"/><YAxis tickFormatter={v=>`${Math.round(v/1e6)}M`}/><Tooltip formatter={v=>money(v)}/><Bar dataKey="gmv" name="GMV" fill="#3867d6" radius={[6,6,0,0]}/><Bar dataKey="net" name="Net Revenue" fill="#20a464" radius={[6,6,0,0]}/></BarChart></ResponsiveContainer></div></div><div className="panel"><div className="panel-title"><div><h3>Cảnh báo gần đây</h3><p>Ưu tiên các bất thường cần xử lý</p></div></div><div className="alert-list">{data.alerts.map(a=><div className={`alert-row sev-${a.severity.toLowerCase()}`} key={a.id}><i/><div><b>{a.title}</b><span>{a.message}</span></div></div>)}</div></div></section>
  <section className="panel ranking-panel"><div className="panel-title"><div><h3>Xếp hạng team</h3><p>Sắp theo doanh thu giữ lại</p></div></div><div className="table-wrap"><table><thead><tr><th>#</th><th>Team</th><th>GMV</th><th>Đơn</th><th>AOV</th><th>Ads</th><th>Ads/GMV</th><th>ROAS</th><th>Hoàn/Hủy</th><th>Net Revenue</th><th>GMV/Giờ</th></tr></thead><tbody>{data.ranking.map(r=><tr key={r.team_id}><td><span className={`rank-badge rank-${r.rank}`}>{r.rank}</span></td><td><b>{r.team_name}</b></td><td>{money(r.gmv)}</td><td>{num(r.orders)}</td><td>{money(r.aov)}</td><td>{money(r.ads_spend)}</td><td>{pct(r.ads_gmv_pct)}</td><td>{r.roas}</td><td>{pct(r.refund_rate)}</td><td><b>{money(r.net_revenue)}</b></td><td>{money(r.gmv_per_hour)}</td></tr>)}</tbody></table></div></section>
 </div>
}
