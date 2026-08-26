import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, connectDashboardWS, user } from '../lib/api'
import { compactMoney, money, number, percent } from '../lib/format'
import { ChannelCard, KpiCard } from '../components/Cards'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AlertTriangle, ArrowUpRight, Download, RefreshCw, Trophy } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function Dashboard(){
  const [data,setData]=useState<any>(null); const [error,setError]=useState(''); const [loading,setLoading]=useState(true)
  const load=useCallback(async()=>{try{setError('');setData(await api('/dashboard/overview'))}catch(e:any){setError(e.message)}finally{setLoading(false)}},[])
  useEffect(()=>{load(); const stop=connectDashboardWS(()=>load()); const poll=setInterval(load,30000); return()=>{stop();clearInterval(poll)}},[load])
  const chart=useMemo(()=>data?.timeline?.map((x:any)=>({...x,time:new Date(x.timestamp).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})}))||[],[data])
  if(loading) return <div className="page-loader">Đang tải Command Center...</div>
  if(error) return <div className="error-state"><AlertTriangle/><b>Không tải được dashboard</b><span>{error}</span><button onClick={load}>Thử lại</button></div>
  const k=data.kpis; const me=user(); const adsConfigured=data.channels.some((x:any)=>x.ads_configured)
  return <>
    <div className="page-title"><div><span className="section-kicker">{me?.role==='ADMIN'?'ADMIN DASHBOARD':`TEAM DASHBOARD • ${me?.team_name}`}</span><h2>Tổng quan vận hành</h2><p>Dữ liệu từ database + provider • tự động cập nhật không reload</p></div><div className="page-actions"><span className={`mode-badge ${data.mode==='MOCK'?'mock':'real'}`}>{data.mode} MODE</span><button className="secondary" onClick={load}><RefreshCw size={15}/>Làm mới</button><Link className="primary action-link" to="/reports"><Download size={15}/>Xuất báo cáo</Link></div></div>

    <section className="channels-grid">{data.channels.map((x:any)=><ChannelCard key={x.id} channel={x}/>)}</section>
    <section className="kpi-grid">
      <KpiCard label="TỔNG GMV HÔM NAY" value={money(k.gmv)} sub="GMV gốc"/>
      <KpiCard label="TỔNG SỐ ĐƠN" value={number(k.orders)} sub="Đơn trong phiên"/>
      {adsConfigured&&<KpiCard label="TỔNG ADS SPEND" value={money(k.ads_spend)} sub="TikTok Ads"/>}
      <KpiCard label="AOV" value={money(k.aov)} sub="GMV / Orders"/>
      {adsConfigured&&<KpiCard label="ADS / GMV" value={percent(k.ads_percentage)} sub="Chi phí quảng cáo"/>}
      {adsConfigured&&<KpiCard label="ROAS" value={k.roas?.toFixed?.(1)||'0.0'} sub="GMV / Ads"/>}
      <KpiCard label="NET REVENUE" value={money(k.net_revenue)} sub={`Hoàn/Hủy ${percent(k.refund_rate)}`} kind="success"/>
      <KpiCard label="GMV / HOUR" value={money(k.gmv_per_hour)} sub="Hiệu suất theo giờ"/>
    </section>

    <section className="dashboard-grid"><article className="panel span-2"><div className="panel-head"><div><span className="section-kicker">CẬP NHẬT 3 PHÚT/LẦN</span><h3>GMV theo timeline</h3></div><strong>{compactMoney(k.gmv)}</strong></div><div className="chart-box"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chart}><defs><linearGradient id="gmvFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#36e189" stopOpacity={.35}/><stop offset="100%" stopColor="#36e189" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#173126" vertical={false}/><XAxis dataKey="time" stroke="#63786e" tick={{fontSize:11}}/><YAxis stroke="#63786e" tick={{fontSize:11}} tickFormatter={compactMoney}/><Tooltip contentStyle={{background:'#0b1712',border:'1px solid #244335'}} formatter={(v:any)=>money(Number(v))}/><Area type="monotone" dataKey="gmv" stroke="#36e189" fill="url(#gmvFill)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div></article>

      <article className="panel"><div className="panel-head"><div><span className="section-kicker">TOP SKU</span><h3>Sản phẩm bán chạy</h3></div></div><div className="top-list">{data.top_skus.length?data.top_skus.map((x:any,i:number)=><div key={i}><span className="rank">{i+1}</span><div><b>{x.name}</b><small>{number(x.quantity)} sản phẩm</small></div><strong>{compactMoney(x.revenue)}</strong></div>):<div className="empty">Chưa có dữ liệu SKU</div>}</div></article>

      <article className="panel"><div className="panel-head"><div><span className="section-kicker">SMART ALERTS</span><h3>Cảnh báo gần nhất</h3></div><Link to="/alerts">Xem tất cả →</Link></div><div className="alerts-list">{data.alerts.slice(0,5).map((a:any)=><div className={`alert-row ${a.severity?.toLowerCase()}`} key={a.id}><AlertTriangle size={16}/><div><b>{a.title}</b><span>{a.message}</span></div><time>{new Date(a.created_at).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'})}</time></div>)}</div></article>
    </section>

    <section className="panel optional-panel"><div><span className="section-kicker">OPTIONAL METRICS</span><h3>Chỉ số LIVE mở rộng</h3><p>App không crash khi TikTok không cấp các metric này.</p></div><div className="optional-grid">{Object.entries(data.optional_metrics).map(([key,val])=><div key={key}><small>{key.replaceAll('_',' ').toUpperCase()}</small><b>{val==null?'Chưa có dữ liệu':String(val)}</b></div>)}</div></section>
  </>
}
