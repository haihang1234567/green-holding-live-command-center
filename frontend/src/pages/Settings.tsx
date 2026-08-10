import { useEffect, useState } from 'react'
import { api, json } from '../lib/api'
import { CheckCircle2, CircleAlert, RefreshCw, Radio, ShieldCheck } from 'lucide-react'

function Status({label,ok,value}:{label:string,ok:boolean,value?:string|null}){return <div><span>{label}</span><b className={ok?'ok-text':'muted'}>{value|| (ok?'Đã cấu hình':'Chưa cấu hình')}</b></div>}

export default function Settings(){
 const[s,setS]=useState<any>(null);const[t,setT]=useState<any>(null);const[a,setA]=useState<any>(null);const[teams,setTeams]=useState<any[]>([]);const[msg,setMsg]=useState('')
 const load=()=>Promise.all([api('/integrations/status'),api('/settings/thresholds'),api('/settings/assignments'),api('/teams')]).then(([s0,t0,a0,tm]:any)=>{setS(s0);setT(t0);setA(a0);setTeams(tm)})
 useEffect(()=>{load()},[])
 async function saveThresholds(){await api('/settings/thresholds',json('PATCH',t));setMsg('Đã lưu ngưỡng cảnh báo')}
 async function saveAssignments(){await api('/settings/assignments',json('PATCH',a));setMsg('Đã lưu team phụ trách theo kênh/ca')}
 async function testShop(channel:number){setMsg(`Đang test Shop ${channel}...`);try{const r:any=await api(`/integrations/test/shop/${channel}`,{method:'POST'});setMsg(`Shop ${channel} OK • ${r.shops?.length||0} shop được cấp quyền`)}catch(e:any){setMsg(e.message)}}
 async function testAds(channel:number){setMsg(`Đang test Ads Shop ${channel}...`);try{await api(`/integrations/test/ads/${channel}`,{method:'POST'});setMsg(`Ads Shop ${channel} OK`)}catch(e:any){setMsg(e.message)}}
 if(!s||!t||!a)return <div className="page-loader">Đang tải cấu hình...</div>
 const teamSelect=(key:string)=><select value={a[key]||''} onChange={e=>setA({...a,[key]:+e.target.value})}><option value="">Chọn team</option>{teams.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select>
 return <><div className="page-title"><div><span className="section-kicker">INTEGRATION CENTER V2</span><h2>Cấu hình 2 Shop độc lập</h2><p>Mỗi shop dùng App Key/Secret/Token riêng. Secret chỉ lưu trong Render Environment, không đưa xuống trình duyệt.</p></div><button className="secondary" onClick={load}><RefreshCw size={15}/>Refresh</button></div>{msg&&<div className="notice">{msg}</div>}

 <section className="panel"><div className="panel-head"><div><span className="section-kicker">AUTOMATION STATUS</span><h3>Luồng giám sát tự động</h3></div><span className={`mode-badge ${s.data_provider==='TIKTOK'?'real':'mock'}`}>{s.data_provider} / {s.live_status_provider}</span></div><div className="optional-grid"><div><Radio size={18}/><small>LIVE POLLING</small><b>{s.polling_interval_seconds}s / lần</b></div><div><RefreshCw size={18}/><small>METRIC SYNC</small><b>{s.metric_snapshot_interval_seconds}s / lần</b></div><div><ShieldCheck size={18}/><small>SESSION CONTROL</small><b>Tự START / STOP theo tín hiệu TikTok</b></div></div></section>

 <div className="settings-grid">{s.profiles.map((p:any)=><section className="panel" key={p.slot}><div className="panel-head"><div><span className="section-kicker">SHOP {p.slot}</span><h3>{p.channel_name}</h3><p className="muted">{p.handle}</p></div>{p.shop.app_key&&p.shop.app_secret&&p.shop.access_token&&p.live.endpoint_configured?<CheckCircle2 className="ok"/>:<CircleAlert className="warn"/>}</div>
   <div className="status-list"><Status label="Shop App Key" ok={p.shop.app_key}/><Status label="Shop App Secret" ok={p.shop.app_secret}/><Status label="Shop Access Token" ok={p.shop.access_token}/><Status label="Refresh Token" ok={p.shop.refresh_token}/><Status label="Shop Cipher" ok={p.shop.shop_cipher}/><Status label="Shop ID" ok={!!p.shop.shop_id} value={p.shop.shop_id}/></div>
   <div className="status-list"><Status label="Ads App ID" ok={p.ads.app_id}/><Status label="Ads Secret" ok={p.ads.secret}/><Status label="Ads Access Token" ok={p.ads.access_token}/><Status label="Advertiser ID" ok={!!p.ads.advertiser_id} value={p.ads.advertiser_id}/></div>
   <div className="status-list"><Status label="LIVE Status Endpoint" ok={p.live.endpoint_configured}/><Status label="LIVE Auth" ok={p.live.endpoint_configured} value={p.live.auth_mode}/><Status label="LIVE JSON Path" ok={p.live.endpoint_configured} value={p.live.json_path}/></div>
   <div className="inline-actions"><button className="secondary" onClick={()=>testShop(p.channel_id)}>Test Shop {p.slot}</button><button className="secondary" onClick={()=>testAds(p.channel_id)}>Test Ads {p.slot}</button></div>
  </section>)}</div>

 <div className="settings-grid">
  <section className="panel"><div className="panel-head"><div><span className="section-kicker">ALERT THRESHOLDS</span><h3>Ngưỡng cảnh báo</h3></div></div><label>Refund vượt (%)<input type="number" value={t.refund_warning_percent} onChange={e=>setT({...t,refund_warning_percent:+e.target.value})}/></label><label>Ads/GMV vượt (%)<input type="number" value={t.ads_gmv_warning_percent} onChange={e=>setT({...t,ads_gmv_warning_percent:+e.target.value})}/></label><label>GMV 15 phút giảm (%)<input type="number" value={t.gmv_velocity_drop_percent} onChange={e=>setT({...t,gmv_velocity_drop_percent:+e.target.value})}/></label><button className="primary" onClick={saveThresholds}>Lưu thresholds</button></section>
  <section className="panel"><div className="panel-head"><div><span className="section-kicker">AUTO TEAM MAPPING</span><h3>Team theo kênh / ca</h3></div></div><div className="assignment-grid"><label>Kênh 01 • Ca sáng{teamSelect('channel_1_ca_sang_team_id')}</label><label>Kênh 01 • Ca tối{teamSelect('channel_1_ca_toi_team_id')}</label><label>Kênh 02 • Ca sáng{teamSelect('channel_2_ca_sang_team_id')}</label><label>Kênh 02 • Ca tối{teamSelect('channel_2_ca_toi_team_id')}</label></div><button className="primary" onClick={saveAssignments}>Lưu phân ca tự động</button></section>
 </div>

 <section className="panel env-panel"><span className="section-kicker">RENDER ENVIRONMENT</span><h3>Khi nhận API thật</h3><p>Đặt <code>DATA_PROVIDER=TIKTOK</code>, <code>LIVE_STATUS_PROVIDER=AUTO</code>, <code>SEED_MOCK_DATA=false</code>, sau đó nhập riêng các biến <code>SHOP1_*</code> và <code>SHOP2_*</code> trong Render. Mỗi shop có App Key, Secret, Access Token, Refresh Token, Shop Cipher, Ads Token và LIVE Status Endpoint riêng.</p></section>
 </>
}
