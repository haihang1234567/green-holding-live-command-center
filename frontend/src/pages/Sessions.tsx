import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarDays, Database, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { dt, duration, money, number } from '../lib/format'

const statusLabel: Record<string,string> = { LIVE:'ĐANG LIVE', ENDED:'ĐÃ KẾT THÚC', OFFLINE:'OFFLINE' }

export default function Sessions(){
  const [rows,setRows]=useState<any[]>([])
  const [status,setStatus]=useState('')
  const [dateFrom,setDateFrom]=useState('')
  const [dateTo,setDateTo]=useState('')
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')

  const load=useCallback(async()=>{
    const params=new URLSearchParams()
    if(status)params.set('status',status)
    if(dateFrom)params.set('date_from',dateFrom)
    if(dateTo)params.set('date_to',dateTo)
    params.set('limit','500')
    try{
      setError('')
      setRows(await api(`/sessions?${params.toString()}`))
    }catch(e:any){setError(e.message)}finally{setLoading(false)}
  },[status,dateFrom,dateTo])

  useEffect(()=>{load();const timer=window.setInterval(load,30000);return()=>window.clearInterval(timer)},[load])
  const totals=useMemo(()=>rows.reduce((acc,x)=>({gmv:acc.gmv+Number(x.gmv||0),orders:acc.orders+Number(x.orders||0),snapshots:acc.snapshots+Number(x.snapshot_count||0)}),{gmv:0,orders:0,snapshots:0}),[rows])

  return <>
    <div className="page-title"><div><span className="section-kicker">LIVE DATABASE</span><h2>Lịch sử phiên LIVE</h2><p>Mỗi live_id TikTok được lưu thành một phiên riêng và tự cập nhật 3 phút/lần.</p></div><div className="page-actions"><button className="secondary" onClick={load}><RefreshCw size={15}/>Làm mới</button></div></div>

    <section className="history-summary">
      <div><Database size={18}/><span>Phiên đã lưu</span><b>{number(rows.length)}</b></div>
      <div><CalendarDays size={18}/><span>Snapshot chỉ số</span><b>{number(totals.snapshots)}</b></div>
      <div><span>GMV trong danh sách</span><b>{money(totals.gmv)}</b></div>
      <div><span>Đơn trong danh sách</span><b>{number(totals.orders)}</b></div>
    </section>

    <section className="panel history-filters">
      <label><span>Từ ngày</span><input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/></label>
      <label><span>Đến ngày</span><input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/></label>
      <label><span>Trạng thái</span><select value={status} onChange={e=>setStatus(e.target.value)}><option value="">Tất cả</option><option value="LIVE">Đang LIVE</option><option value="ENDED">Đã kết thúc</option></select></label>
      <button className="secondary" onClick={()=>{setDateFrom('');setDateTo('');setStatus('')}}>Xóa bộ lọc</button>
    </section>

    {error&&<div className="notice">Không tải được lịch sử: {error}</div>}
    <div className="panel table-panel"><div className="table-scroll"><table><thead><tr><th>Mã phiên TikTok</th><th>Kênh</th><th>Trạng thái</th><th>Bắt đầu</th><th>Kết thúc</th><th>Thời lượng</th><th>GMV</th><th>Đơn</th><th>Lần ghi gần nhất</th><th></th></tr></thead><tbody>
      {rows.map(x=><tr key={x.id}><td><b>{x.session_code}</b><small className="cell-sub">{x.source==='TIKTOK_ANALYTICS'?'TikTok LIVE Analytics':'TikTok API'}</small></td><td>{x.channel_name}</td><td><span className={`badge ${x.status.toLowerCase()}`}>{statusLabel[x.status]||x.status}</span></td><td>{dt(x.started_at)}</td><td>{x.ended_at?dt(x.ended_at):'—'}</td><td>{duration(x.duration_seconds)}</td><td><b>{money(x.gmv)}</b></td><td>{number(x.orders)}</td><td>{x.latest_snapshot_at?<>{dt(x.latest_snapshot_at)}<small className="cell-sub">{number(x.snapshot_count)} snapshot</small></>:'Chưa có'}</td><td><Link to={`/sessions/${x.id}`}>Chi tiết →</Link></td></tr>)}
      {!loading&&!rows.length&&<tr><td colSpan={10}><div className="empty">Chưa có phiên LIVE trong khoảng thời gian đã chọn.</div></td></tr>}
      {loading&&<tr><td colSpan={10}><div className="empty">Đang tải lịch sử phiên LIVE...</div></td></tr>}
    </tbody></table></div></div>
  </>
}
