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
    _sheet(ws3,["广告组","关键词","匹配方式"],[[x.get("name",""),", ".join(x.get("keywords") or []),x.get("match_type","")] for x in g["ad_groups"]],[26,50,10])
    c=a.get("ad_calc")
    if c:
        ws3.append([]); ws3.append(["预算与出价参考（估算）"]); ws3.cell(ws3.max_row,1).font=Font(name=F,bold=True)
        for i in c["inputs"]: ws3.append([i["label"],f'{i["value"]}{i["unit"]}' if i["unit"]!="$" else f'${i["value"]:.2f}',i["source"]])
        if c.get("price_position"): ws3.append(["竞品价格对比",c["price_position"]["text"]])
        ws3.append(["单件利润",f'${c["unit_profit"]:.2f}（利润率 {c["margin_pct"]}%）'])
        if c["profitable"]:
            for k,v in [("盈亏平衡 ACoS",f'{c["breakeven_acos_pct"]}%'),("目标 ACoS",f'{c["target_acos_pct"]}%'),("建议起步出价",f'${c["start_bid"]:.2f}'),
                        ("建议最高出价",f'${c["max_bid"]:.2f}'),("建议日预算",f'${c["daily_budget"]:.2f}'),("预计日订单",f'{c["daily_orders"]} 单')]: ws3.append([k,v,"估算"])
        else: ws3.append([c["message"],c["reason"]])
        ws3.append(["说明",c["note"]])
    b=io.BytesIO(); wb.save(b); return b.getvalue()
