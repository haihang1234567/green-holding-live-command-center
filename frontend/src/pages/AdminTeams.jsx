import {useEffect,useState} from 'react'
import {api} from '../api'
import {money,num} from '../utils'
import AdminHeader from '../components/AdminHeader'
export default function AdminTeams(){const [rows,setRows]=useState([]);useEffect(()=>{api.teams().then(setRows)},[]);return <><AdminHeader title="Teams" subtitle="Tổng quan 4 team"/><div className="ranking-cards">{rows.map(t=><div className="rank-card" key={t.id}><span className="rank-big">TEAM {String(t.id).padStart(2,'0')}</span><h2>{t.name}</h2><strong>{money(t.net_revenue)}</strong><small>Net Revenue</small><div><span>GMV <b>{money(t.gmv)}</b></span><span>Orders <b>{num(t.orders)}</b></span><span>Ads <b>{money(t.ads_spend)}</b></span><span>Sessions <b>{t.sessions}</b></span></div></div>)}</div></>}
