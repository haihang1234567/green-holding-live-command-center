import {useEffect,useState} from 'react'
import {api} from '../api'
import {money,num,when} from '../utils'
import AdminHeader from '../components/AdminHeader'
export default function AdminOrders(){const [rows,setRows]=useState([]);useEffect(()=>{api.orders().then(setRows)},[]);return <><AdminHeader title="Đơn hàng" subtitle="Đơn hàng gắn với từng phiên LIVE"/><div className="panel"><div className="table-wrap"><table><thead><tr><th>Order ID</th><th>Thời gian</th><th>Team</th><th>Kênh</th><th>Sản phẩm</th><th>SL</th><th>Thanh toán</th><th>Trạng thái</th><th>Hoàn</th><th>Hủy</th></tr></thead><tbody>{rows.map(o=><tr key={o.order_id}><td><b>{o.order_id}</b></td><td>{when(o.created_at)}</td><td>{o.team_name}</td><td>{o.channel_name}</td><td>{o.product_name}</td><td>{num(o.quantity)}</td><td>{money(o.payment_amount)}</td><td><span className="mini-tag">{o.status}</span></td><td>{money(o.refund_amount)}</td><td>{money(o.cancelled_amount)}</td></tr>)}</tbody></table></div></div></>}
