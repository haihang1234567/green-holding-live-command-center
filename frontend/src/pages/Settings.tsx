import { useEffect,useState } from 'react'
import { api,json } from '../lib/api'
import { CheckCircle2,CircleAlert,Radio,RefreshCw,ShieldCheck } from 'lucide-react'

function Flag({label,ok,value}:{label:string,ok?:boolean,value?:any}){
 return <div><span>{label}</span><b className={ok?'ok-text':'muted'}>{value??(ok?'Đã cấu hình':'Chưa cấu hình')}</b></div>
}

export default function Settings(){
 const[status,setStatus]=useState<any>(null)
 const[thresholds,setThresholds]=useState<any>(null)
 const[message,setMessage]=useState('')
 const load=()=>Promise.all([api('/integrations/status'),api('/settings/thresholds')]).then(([s,t]:any)=>{setStatus(s);setThresholds(t)})
 useEffect(()=>{load()},[])
 async function test(kind:'shop'|'ads'|'live',channelId:number){
  setMessage(`Đang test ${kind.toUpperCase()} Shop ${channelId}...`)
  try{
   const r:any=await api(`/integrations/test/${kind}/${channelId}`,{method:'POST'})
   setMessage(`${kind.toUpperCase()} Shop ${channelId}: OK${r.result?.status?` • ${r.result.status}`:''}`)
  }catch(e:any){setMessage(e.message)}
 }
 async function saveThresholds(){await api('/settings/thresholds',json('PATCH',thresholds));setMessage('Đã lưu ngưỡng cảnh báo')}
 if(!status||!thresholds)return <div className="page-loader">Đang tải cấu hình...</div>
 const shopCount=status.active_shop_count||status.shops.length
 return <>
  <div className="page-title"><div><span className="section-kicker">API INTEGRATION CENTER</span><h2>{shopCount} Shop • API riêng cho Shop 1</h2><p>Hệ thống tự nhận diện phiên LIVE và ghi nhận chỉ số TikTok API, không cần phân ca.</p></div><button className="secondary" onClick={load}><RefreshCw size={15}/>Refresh</button></div>
  {message&&<div className="notice">{message}</div>}
  <section className="panel monitor-summary"><div className="panel-head"><div><span className="section-kicker">PRODUCTION FLOW</span><h3>{status.data_provider} / {status.live_status_provider}</h3></div><span className="mode-badge real">{status.polling_interval_seconds}s / lần</span></div><p className="muted">TikTok báo LIVE → hệ thống tự mở phiên → ghi nhận GMV, đơn hàng và chỉ số LIVE → tự đóng phiên khi kết thúc.</p></section>
  <div className="cards-2">{status.shops.map((s:any)=>{const shopConnected=s.shop.app_key&&s.shop.app_secret&&s.shop.access_token&&s.shop.refresh_token&&s.shop.shop_cipher&&s.shop.shop_id;return <section className="panel" key={s.channel_id}><div className="panel-head"><div><span className="section-kicker">{s.name}</span><h3>{s.channel_name}</h3></div>{shopConnected?<CheckCircle2 className="ok"/>:<CircleAlert className="warn"/>}</div><div className="status-list"><Flag label="Shop App Key" ok={s.shop.app_key}/><Flag label="Shop App Secret" ok={s.shop.app_secret}/><Flag label="Shop Access Token" ok={s.shop.access_token}/><Flag label="Shop Refresh Token" ok={s.shop.refresh_token}/><Flag label="Shop Cipher" ok={s.shop.shop_cipher}/><Flag label="Shop ID" ok={!!s.shop.shop_id} value={s.shop.shop_id||'Chưa cấu hình'}/><Flag label="Ads Access Token" ok={s.ads.access_token}/><Flag label="Advertiser ID" ok={!!s.ads.advertiser_id} value={s.ads.advertiser_id||'Chưa cấu hình'}/><Flag label="LIVE Status API" ok={s.live.status_endpoint}/><Flag label="LIVE Metrics API" ok={s.live.metrics_endpoint}/><Flag label="LIVE Auth" ok={true} value={s.live.status_auth_mode}/></div><div className="inline-actions"><button className="secondary" onClick={()=>test('live',s.channel_id)}><Radio size={14}/>Test LIVE</button><button className="secondary" onClick={()=>test('shop',s.channel_id)}>Test Shop</button><button className="secondary" onClick={()=>test('ads',s.channel_id)}>Test Ads</button></div></section>})}</div>
  <section className="panel"><div className="panel-head"><div><span className="section-kicker">ALERT THRESHOLDS</span><h3>Ngưỡng cảnh báo</h3></div></div><label>Hoàn/Hủy vượt (%)<input type="number" value={thresholds.refund_warning_percent} onChange={e=>setThresholds({...thresholds,refund_warning_percent:+e.target.value})}/></label><label>Ads/GMV vượt (%)<input type="number" value={thresholds.ads_gmv_warning_percent} onChange={e=>setThresholds({...thresholds,ads_gmv_warning_percent:+e.target.value})}/></label><label>GMV 15 phút giảm (%)<input type="number" value={thresholds.gmv_velocity_drop_percent} onChange={e=>setThresholds({...thresholds,gmv_velocity_drop_percent:+e.target.value})}/></label><button className="primary" onClick={saveThresholds}>Lưu thresholds</button></section>
  <section className="panel env-panel"><div className="panel-head"><div><span className="section-kicker">REAL API MODE</span><h3>TikTok Shop API đang tự động ghi nhận</h3></div><ShieldCheck className="ok"/></div><div className="code-list"><code>ACTIVE_SHOP_COUNT=1</code><code>DATA_PROVIDER=TIKTOK</code><code>LIVE_STATUS_PROVIDER=AUTO</code><code>TIKTOK SHOP ANALYTICS</code><code>POLLING_INTERVAL_SECONDS=180</code></div></section>
 </>
}
