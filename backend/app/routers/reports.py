from datetime import date,datetime,time,timezone
from io import BytesIO
from fastapi import APIRouter,Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4,landscape
from app.db import get_db
from app.deps import require_admin
from app.models import LiveSession
from app.services.kpi import session_metrics,get_refund_snapshot,top_skus,SNAPSHOT_ORDER

router=APIRouter(prefix="/admin/reports",tags=["reports"],dependencies=[Depends(require_admin)])

def _query(db,date_from=None,date_to=None,team_id=None,channel_id=None,shift=None):
    q=db.query(LiveSession)
    if date_from:q=q.filter(LiveSession.started_at>=datetime.combine(date_from,time.min).replace(tzinfo=timezone.utc))
    if date_to:q=q.filter(LiveSession.started_at<=datetime.combine(date_to,time.max).replace(tzinfo=timezone.utc))
    if team_id:q=q.filter(LiveSession.team_id==team_id)
    if channel_id:q=q.filter(LiveSession.channel_id==channel_id)
    if shift:q=q.filter(LiveSession.shift==shift.upper())
    return q.order_by(LiveSession.started_at.desc()).all()

def _rows(db,sessions,snapshot_type):
    out=[]
    for s in sessions:
        m=session_metrics(s,get_refund_snapshot(db,s.id,snapshot_type));top=top_skus(db,s.id,1)
        out.append({"session_code":s.session_code,"date":s.started_at.date().isoformat(),"team":s.team.name,"channel":s.channel.name,"shift":"Ca sáng" if s.shift=="MORNING" else "Ca tối","gmv":m['gmv'],"net_revenue":m['net_revenue'],"orders":m['orders'],"refund_rate":m['refund_rate'],"ads":m['ads_spend'],"roas":m['roas'],"aov":m['aov'],"gmv_per_hour":m['gmv_per_hour'],"top_sku":top[0]['product_name'] if top else "Chưa có dữ liệu"})
    return out

@router.get("/summary")
def summary(date_from:date|None=None,date_to:date|None=None,team_id:int|None=None,channel_id:int|None=None,shift:str|None=None,snapshot_type:str="T3H",db:Session=Depends(get_db)):
    if snapshot_type not in SNAPSHOT_ORDER:snapshot_type="T3H"
    rows=_rows(db,_query(db,date_from,date_to,team_id,channel_id,shift),snapshot_type);t={"gmv":sum(r['gmv'] for r in rows),"net_revenue":sum(r['net_revenue'] for r in rows),"orders":sum(r['orders'] for r in rows),"ads":sum(r['ads'] for r in rows)}
    t['aov']=round(t['gmv']/t['orders']) if t['orders'] else 0;t['roas']=round(t['gmv']/t['ads'],2) if t['ads'] else 0;t['refund_rate']=round((t['gmv']-t['net_revenue'])/t['gmv']*100,2) if t['gmv'] else 0
    return {"snapshot_type":snapshot_type,"totals":t,"rows":rows}

@router.get("/excel")
def excel(date_from:date|None=None,date_to:date|None=None,team_id:int|None=None,channel_id:int|None=None,shift:str|None=None,snapshot_type:str="T3H",db:Session=Depends(get_db)):
    data=summary(date_from,date_to,team_id,channel_id,shift,snapshot_type,db);wb=Workbook();ws=wb.active;ws.title="Live Report";headers=["Session","Ngày","Team","Kênh","Ca","GMV","Net Revenue","Orders","Refund Rate %","Ads","ROAS","AOV","GMV/Hour","Top SKU"];ws.append(headers)
    for c in ws[1]:c.font=Font(bold=True,color="FFFFFF");c.fill=PatternFill("solid",fgColor="172033");c.alignment=Alignment(horizontal="center")
    for r in data['rows']:ws.append([r['session_code'],r['date'],r['team'],r['channel'],r['shift'],r['gmv'],r['net_revenue'],r['orders'],r['refund_rate'],r['ads'],r['roas'],r['aov'],r['gmv_per_hour'],r['top_sku']])
    for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=min(max(len(str(c.value or '')) for c in col)+2,28)
    bio=BytesIO();wb.save(bio);bio.seek(0);return StreamingResponse(bio,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=live-report.xlsx"})

def _font():
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/dejavu/DejaVuSans.ttf"]:
        try:pdfmetrics.registerFont(TTFont("DejaVu",p));return "DejaVu"
        except Exception:pass
    return "Helvetica"

@router.get("/pdf")
def pdf(date_from:date|None=None,date_to:date|None=None,team_id:int|None=None,channel_id:int|None=None,shift:str|None=None,snapshot_type:str="T3H",db:Session=Depends(get_db)):
    data=summary(date_from,date_to,team_id,channel_id,shift,snapshot_type,db);font=_font();bio=BytesIO();c=canvas.Canvas(bio,pagesize=landscape(A4));w,h=landscape(A4)
    def header():c.setFont(font,18);c.drawString(35,h-40,"Báo cáo Livestream");c.setFont(font,9);c.drawString(35,h-57,f"Mốc hoàn/hủy: {snapshot_type}")
    header();y=h-85;c.setFont(font,9);heads=["Ngày","Team","Kênh","GMV","Net","Đơn","Refund%","Ads","ROAS"];xs=[35,92,180,290,380,470,520,580,680]
    for x,t in zip(xs,heads):c.drawString(x,y,t)
    y-=15
    for r in data['rows']:
        if y<35:c.showPage();header();y=h-85;c.setFont(font,9)
        vals=[r['date'],r['team'],r['channel'],f"{r['gmv']:,}",f"{r['net_revenue']:,}",str(r['orders']),f"{r['refund_rate']:.2f}",f"{r['ads']:,}",f"{r['roas']:.2f}"]
        for x,v in zip(xs,vals):c.drawString(x,y,str(v)[:22])
        y-=14
    c.save();bio.seek(0);return StreamingResponse(bio,media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=live-report.pdf"})
