import { FormEvent, useState } from 'react'
import { login } from '../lib/api'
import { useNavigate } from 'react-router-dom'
import { Activity, LockKeyhole } from 'lucide-react'

export default function Login(){
  const nav=useNavigate(); const [username,setUsername]=useState('admin'); const [password,setPassword]=useState('admin123'); const [error,setError]=useState(''); const [busy,setBusy]=useState(false)
  async function submit(e:FormEvent){e.preventDefault();setBusy(true);setError('');try{await login(username,password);nav('/')}catch(e:any){setError(e.message)}finally{setBusy(false)}}
  return <div className="login-page"><div className="login-glow"/><form className="login-card" onSubmit={submit}><div className="login-logo"><Activity/><span>G</span></div><h1>GREEN HOLDING</h1><h2>LIVE COMMAND CENTER</h2><p>Hệ thống quản lý & theo dõi livestream TikTok</p><label>Tài khoản<input value={username} onChange={e=>setUsername(e.target.value)} autoFocus/></label><label>Mật khẩu<input type="password" value={password} onChange={e=>setPassword(e.target.value)}/></label>{error&&<div className="form-error">{error}</div>}<button className="primary big" disabled={busy}><LockKeyhole size={16}/>{busy?'Đang đăng nhập...':'Đăng nhập'}</button><small className="login-hint">Demo mặc định: admin / admin123</small></form></div>
}
