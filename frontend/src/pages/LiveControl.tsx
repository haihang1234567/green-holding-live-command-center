import { useEffect, useState } from 'react'
import { api, json, user } from '../lib/api'
import { duration, money, number } from '../lib/format'
import { PlayCircle, StopCircle } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function LiveControl(){
 const [channels,setChannels]=useState<any[]>([]);const[teams,setTeams]=useState<any[]>([]);const[team,setTeam]=useState(1);const[shift,setShift]=useState('CA_SANG');const[msg,setMsg]=useState('')
 const load=()=>Promise.all([api('/dashboard/overview'),api('/teams')]).then(([d,t]:any)=>{setChannels(d.channels);setTeams(t);if(t.length&&!team)setTeam(t[0].id)})
 useEffect(()=>{load();const p=setInterval(load,15000);return()=>clearInterval(p)},[])
 async function start(channel_id:number){try{await api('/sessions/manual/start',json('POST',{channel_id,team_id:team,shift}));setMsg('Đã mở phiên LIVE thủ công');load()}catch(e:any){setMsg(e.message)}}
 async function stop(id:number){try{await api(`/sessions/${id}/stop`,{method:'POST'});setMsg('Đã kết thúc phiên LIVE');load()}catch(e:any){setMsg(e.message)}}
 return <><div className="page-title"><div><span className="section-kicker">LIVE OPERATIONS</span><h2>LIVE hiện tại</h2><p>Dùng tự động khi có nguồn LIVE status; nếu TikTok không cấp status API có thể Start/Stop thủ công mà dữ liệu Shop/Ads vẫn đồng bộ.</p></div></div>{msg&&<div className="notice">{msg}</div>}{user()?.role==='ADMIN'&&<div className="mock-toolbar"><label>Team khi Start thủ công<select value={team} onChange={e=>setTeam(+e.target.value)}>{teams.map(x=><option value={x.id} key={x.id}>{x.name}</option>)}</select></label><label>Ca<select value={shift} onChange={e=>setShift(e.target.value)}><option value="CA_SANG">Ca sáng</option><option value="CA_TOI">Ca tối</option></select></label></div>}
 <div className="cards-2">{channels.map(ch=><article className={`panel mock-card ${ch.status==='LIVE'?'live':''}`} key={ch.id}><div className="panel-head"><div><span className="section-kicker">{ch.name}</span><h3>{ch.handle}</h3></div><span className={`badge ${ch.status.toLowerCase()}`}>{ch.status}</span></div>{ch.session?<><div className="mock-stats"><div><small>TEAM</small><b>{ch.session.team_name}</b></div><div><small>LIVE TIME</small><b>{duration(ch.session.duration_seconds)}</b></div><div><small>GMV</small><b>{money(ch.session.gmv)}</b></div><div><small>ORDERS</small><b>{number(ch.session.orders)}</b></div></div><div className="inline-actions"><Link className="primary action-link" to={`/sessions/${ch.session.id}`}>Mở phiên</Link>{user()?.role==='ADMIN'&&<button className="danger" onClick={()=>stop(ch.session.id)}><StopCircle size={15}/>STOP LIVE</button>}</div></>:user()?.role==='ADMIN'?<button className="primary big" onClick={()=>start(ch.id)}><PlayCircle size={17}/>START LIVE {ch.name}</button>:<div className="empty">Kênh đang OFFLINE</div>}</article>)}</div></>
}
