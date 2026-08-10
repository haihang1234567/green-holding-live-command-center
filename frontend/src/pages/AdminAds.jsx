import {useEffect,useState} from 'react'
import {api} from '../api'
import {money,pct,when} from '../utils'
import AdminHeader from '../components/AdminHeader'
export default function AdminAds(){const [rows,setRows]=useState([]);useEffect(()=>{api.ads().then(setRows)},[]);return <><AdminHeader title="Ads" subtitle="Chi phí quảng cáo theo phiên LIVE"/><div className="panel"><div className="table-wrap"><table><thead><tr><th>Session</th><th>Thời gian</th><th>Team</th><th>Kênh</th><th>Ads Spend</th><th>Attributed Revenue</th><th>Ads/GMV</th><th>ROAS</th></tr></thead><tbody>{rows.map(r=><tr key={r.session_id}><td><b>{r.session_code}</b></td><td>{when(r.started_at)}</td><td>{r.team_name}</td><td>{r.channel_name}</td><td>{money(r.spend)}</td><td>{money(r.attributed_revenue)}</td><td>{pct(r.ads_gmv_pct)}</td><td><b>{r.roas}</b></td></tr>)}</tbody></table></div></div></>}
