import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, saveSession } from '../api'

export default function LoginPage(){
  const [username,setUsername]=useState('admin'), [password,setPassword]=useState('admin123'), [error,setError]=useState(''), [loading,setLoading]=useState(false)
  const nav=useNavigate()
  const submit=async(e)=>{e.preventDefault();setLoading(true);setError('');try{const r=await api.login(username,password);saveSession(r.access_token,{username:r.username,role:r.role,team_id:r.team_id});nav(r.role==='ADMIN'?'/admin':'/team')}catch(err){setError(err.message)}finally{setLoading(false)}}
  return <div className="login-page"><form className="login-card" onSubmit={submit}><div className="login-logo">LC</div><h1>Live Command Center</h1><p>Đăng nhập để xem dashboard</p><label>Tài khoản<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username"/></label><label>Mật khẩu<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password"/></label>{error&&<div className="form-error">{error}</div>}<button disabled={loading}>{loading?'Đang đăng nhập...':'Đăng nhập'}</button><div className="login-demo"><b>Tài khoản demo</b><span>Admin: admin / admin123</span><span>Team: team1 / team123</span></div></form></div>
}
