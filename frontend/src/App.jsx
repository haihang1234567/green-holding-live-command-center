import { Navigate, Route, Routes } from 'react-router-dom'
import { getSessionUser } from './api'
import LoginPage from './pages/LoginPage'
import AdminLayout from './components/AdminLayout'
import AdminDashboard from './pages/AdminDashboard'
import AdminSessions from './pages/AdminSessions'
import AdminSessionDetail from './pages/AdminSessionDetail'
import AdminRanking from './pages/AdminRanking'
import AdminRefunds from './pages/AdminRefunds'
import AdminAlerts from './pages/AdminAlerts'
import AdminMock from './pages/AdminMock'
import AdminApiStatus from './pages/AdminApiStatus'
import TeamDashboard from './pages/TeamDashboard'

function Guard({role,children}){const u=getSessionUser();if(!u)return <Navigate to="/login" replace/>;if(role&&u.role!==role)return <Navigate to={u.role==='ADMIN'?'/admin':'/team'} replace/>;return children}
export default function App(){return <Routes><Route path="/login" element={<LoginPage/>}/><Route path="/admin" element={<Guard role="ADMIN"><AdminLayout/></Guard>}><Route index element={<AdminDashboard/>}/><Route path="sessions" element={<AdminSessions/>}/><Route path="sessions/:id" element={<AdminSessionDetail/>}/><Route path="ranking" element={<AdminRanking/>}/><Route path="refunds" element={<AdminRefunds/>}/><Route path="alerts" element={<AdminAlerts/>}/><Route path="mock" element={<AdminMock/>}/><Route path="api" element={<AdminApiStatus/>}/></Route><Route path="/team" element={<Guard role="TEAM"><TeamDashboard/></Guard>}/><Route path="*" element={<Navigate to="/login" replace/>}/></Routes>}
