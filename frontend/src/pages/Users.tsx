import { FormEvent, useEffect, useState } from 'react'
import { api, json } from '../lib/api'
import { UserPlus } from 'lucide-react'

export default function Users(){
  const [rows,setRows]=useState<any[]>([]); const [teams,setTeams]=useState<any[]>([]); const [msg,setMsg]=useState('')
  const load=()=>Promise.all([api('/users'),api('/teams')]).then(([u,t]:any)=>{setRows(u);setTeams(t)})
  useEffect(()=>{load()},[])
  async function create(e:FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget);const role=String(f.get('role'));const payload:any={username:f.get('username'),password:f.get('password'),role};if(role==='TEAM')payload.team_id=Number(f.get('team_id'));try{await api('/users',json('POST',payload));setMsg('Đã tạo tài khoản');e.currentTarget.reset();load()}catch(err:any){setMsg(err.message)}}
  async function toggle(x:any){try{await api(`/users/${x.id}`,json('PATCH',{is_active:!x.is_active}));load()}catch(err:any){setMsg(err.message)}}
  async function reset(x:any){const password=prompt(`Mật khẩu mới cho ${x.username} (tối thiểu 6 ký tự):`);if(!password)return;try{await api(`/users/${x.id}`,json('PATCH',{password}));setMsg('Đã đổi mật khẩu')}catch(err:any){setMsg(err.message)}}
  return <><div className="page-title"><div><span className="section-kicker">ACCESS CONTROL</span><h2>Người dùng</h2><p>Admin xem toàn hệ thống; Team user chỉ thấy dữ liệu team của mình.</p></div></div>{msg&&<div className="notice">{msg}</div>}
  <div className="settings-grid"><form className="panel" onSubmit={create}><div className="panel-head"><div><span className="section-kicker">CREATE USER</span><h3>Tạo tài khoản</h3></div><UserPlus/></div><label>Username<input name="username" required minLength={3}/></label><label>Mật khẩu<input name="password" type="password" required minLength={6}/></label><label>Quyền<select name="role" defaultValue="TEAM"><option value="TEAM">TEAM</option><option value="ADMIN">ADMIN</option></select></label><label>Team<select name="team_id">{teams.map(x=><option value={x.id} key={x.id}>{x.name}</option>)}</select></label><button className="primary">Tạo người dùng</button></form>
  <section className="panel table-panel span-2"><div className="table-scroll"><table><thead><tr><th>Username</th><th>Role</th><th>Team</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{rows.map(x=><tr key={x.id}><td><b>{x.username}</b></td><td>{x.role}</td><td>{x.team_name||'—'}</td><td><span className={`badge ${x.is_active?'live':'offline'}`}>{x.is_active?'ACTIVE':'LOCKED'}</span></td><td><div className="inline-actions"><button className="secondary" onClick={()=>reset(x)}>Đổi mật khẩu</button><button className="secondary" onClick={()=>toggle(x)}>{x.is_active?'Khóa':'Mở khóa'}</button></div></td></tr>)}</tbody></table></div></section></div></>
}
