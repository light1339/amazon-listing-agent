import io
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment
F="Microsoft YaHei"; HEAD=PatternFill("solid",fgColor="1F3864"); YEL=PatternFill("solid",fgColor="FFF2CC"); GREY=PatternFill("solid",fgColor="D9D9D9")
def _sheet(ws,headers,rows,widths):
    ws.append(headers)
    for r in rows: ws.append(r)
    for c in ws[1]: c.font=Font(name=F,bold=True,color="FFFFFF"); c.fill=HEAD
    for row in ws.iter_rows(min_row=2):
        for c in row: c.font=Font(name=F); c.alignment=Alignment(wrap_text=True,vertical="top")
    for i,w in enumerate(widths): ws.column_dimensions[chr(65+i)].width=w
    ws.freeze_panes="A2"
def export(p,a,g,v):
    wb=Workbook(); ws=wb.active; ws.title="竞品分析"
    _sheet(ws,["排名","ASIN","标题","价格($)","评分","评论数"],[[c["rank"],c["asin"],c["title"],c["price"],c["rating"],c["reviews"]] for c in p["competitors"]],[7,18,70,10,8,10])
    for r in ws.iter_rows(min_row=2):
        if r[5].value<100: r[5].fill=YEL
    ws.append([]); ws.append(["说明","示例数据（模拟），评论数<100 标黄；竞争强度："+a["competition"]])
    ws2=wb.create_sheet("Listing"); items={i["field"]:i for i in v["items"]}
    rows=[["标题",g["title"]]]+[[f"五点 {i}",b] for i,b in enumerate(g["bullets"],1)]+[["后台搜索词",g["backend_terms"]]]
    out=[]
    for f,t in rows:
        it=items.get(f,{"length":len(t),"limit":"","ok":True,"errors":[]})
        out.append([f,t,it["length"],it["limit"],"✔" if it["ok"] else "✘ "+"；".join(it["errors"])])
    _sheet(ws2,["字段","内容","字数","上限","校验"],out,[12,80,8,8,30])
    for r in ws2.iter_rows(min_row=2):
        if r[4].value.startswith("✘"):
            for c in r: c.font=Font(name=F,color="C00000",bold=True)
    ws3=wb.create_sheet("广告方案")
    _sheet(ws3,["广告组","关键词","匹配方式","建议竞价","预算占比"],[[x["name"],", ".join(x["keywords"]),x["match_type"],x["suggested_bid"],x["budget_share"]] for x in g["ad_groups"]],[26,50,10,12,12])
    for r in ws3.iter_rows(min_row=2):
        for c in r[3:]:
            if "待验证" in str(c.value): c.fill=GREY
    b=io.BytesIO(); wb.save(b); return b.getvalue()
