import {useEffect,useState} from 'react'
import {api} from '../api'
import {money,num,pct} from '../utils'
import AdminHeader from '../components/AdminHeader'
export default function AdminProducts(){const [rows,setRows]=useState([]);useEffect(()=>{api.products().then(setRows)},[]);return <><AdminHeader title="Sản phẩm" subtitle="Top SKU và tỷ trọng doanh thu"/><div className="panel"><div className="table-wrap"><table><thead><tr><th>#</th><th>SKU</th><th>Sản phẩm</th><th>SL</th><th>Đơn</th><th>Doanh thu</th><th>Tỷ trọng</th></tr></thead><tbody>{rows.map((p,i)=><tr key={`${p.sku_id}-${i}`}><td>{i+1}</td><td>{p.sku_id||'—'}</td><td><b>{p.product_name}</b></td><td>{num(p.quantity)}</td><td>{num(p.orders)}</td><td>{money(p.revenue)}</td><td>{pct(p.revenue_share)}</td></tr>)}</tbody></table></div></div></>}
