import { useEffect,useState } from 'react'
import { api } from '../api'
import { money,num,pct } from '../utils'
import AdminHeader from '../components/AdminHeader'
import SnapshotSelect from '../components/SnapshotSelect'
export default function AdminRanking(){const [rows,setRows]=useState([]),[snapshot,setSnapshot]=useState('T3H');useEffect(()=>{api.ranking(snapshot).then(setRows)},[snapshot]);return <><AdminHeader title="Xếp hạng 4 team" subtitle="So sánh hiệu quả theo cùng một mốc hoàn/hủy" right={<SnapshotSelect value={snapshot} onChange={setSnapshot} compact/>}/><div className="ranking-cards">{rows.map(r=><div className="rank-card" key={r.team_id}><span className={`rank-big rank-${r.rank}`}>#{r.rank}</span><h2>{r.team_name}</h2><strong>{money(r.net_revenue)}</strong><small>Net Revenue</small><div><span>GMV <b>{money(r.gmv)}</b></span><span>Đơn <b>{num(r.orders)}</b></span><span>ROAS <b>{r.roas}</b></span><span>Hoàn/Hủy <b>{pct(r.refund_rate)}</b></span></div></div>)}</div></>}
