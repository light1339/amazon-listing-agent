"""上传文件解析（内存中完成，不落盘）。支持 .json（同 mock_data.json）、.csv、.xlsx（扁平表，见 COLUMNS）。"""
import csv,io,json,re,zipfile
MAX_BYTES=2*1024*1024; MAX_PRODUCTS=50; MAX_COMPS=20; MAX_STR=500
COLUMNS=["asin","name","noun","category","price","cost","fee_rate","cvr","features","keywords","comp_rank","comp_asin","comp_brand","comp_title","comp_price","comp_rating","comp_reviews","comp_bullets"]
HELP={"asin":"商品 ASIN（必填，4–20 位字母数字）","name":"商品中文名","noun":"英文品名（必填）","category":"类目","price":"售价（数字）","cost":"进货成本 $（可选，0≤成本<售价×5；空=按售价 30% 示例假设）","fee_rate":"平台佣金+配送费占售价比例（可选，0–0.8，如 0.3；空=0.30 示例假设）","cvr":"预计点击转化率（可选，0.01–0.5，如 0.1；空=0.10 示例假设）",
 "features":"卖点，| 分隔，至少 3 个","keywords":"关键词:搜索量:排名，| 分隔，排名可空，如 travel mug:48000:23|thermos cup:33000:",
 "comp_rank":"竞品排名（整数）","comp_asin":"竞品 ASIN","comp_brand":"竞品品牌（可选，如 Trevalo；页面显示为 品牌+品类；旧文件无此列也可上传）","comp_title":"竞品标题","comp_price":"竞品价格","comp_rating":"竞品评分 0–5","comp_reviews":"竞品评论数（整数）","comp_bullets":"竞品五点，| 分隔"}
OPTIONAL={"comp_brand","cost","fee_rate","cvr"}
class Bad(Exception): pass
ID=re.compile(r"^[A-Za-z0-9]{4,20}$")
def _s(v,f,req=True):
    s="" if v is None else str(v).strip()
    if req and not s: raise Bad(f"{f} 不能为空")
    if len(s)>MAX_STR: raise Bad(f"{f} 超过 {MAX_STR} 字符")
    return s
def _n(v,f,kind=float,lo=0,hi=1e9,allow_none=False):
    if v is None or str(v).strip()=="":
        if allow_none: return None
        raise Bad(f"{f} 不能为空")
    try: x=kind(float(str(v).strip().replace(",","")))
    except Exception: raise Bad(f"{f} 不是数字：{str(v)[:20]}")
    if not lo<=x<=hi: raise Bad(f"{f} 超出范围：{x}")
    return x
def _norm(p,where):
    try:
        if not isinstance(p,dict): raise Bad("应为对象")
        asin=_s(p.get("asin"),"asin")
        if not ID.match(asin): raise Bad(f"asin 格式不正确：{asin[:20]}")
        feats=[_s(x,"features 项") for x in (p.get("features") or []) if str(x).strip()]
        if len(feats)<3: raise Bad("features 至少 3 个")
        kws=[]
        for k in p.get("keywords") or []:
            if not isinstance(k,dict): raise Bad("keywords 项应为对象")
            kws.append({"keyword":_s(k.get("keyword"),"keyword"),"search_volume":_n(k.get("search_volume"),"search_volume",int,allow_none=True),
                        "rank":_n(k.get("rank"),"rank",int,1,1e6,allow_none=True)})
        if not kws: raise Bad("keywords 至少 1 个")
        comps=[]
        for c in p.get("competitors") or []:
            if not isinstance(c,dict): raise Bad("competitors 项应为对象")
            ca=_s(c.get("asin"),"comp_asin")
            if not ID.match(ca): raise Bad(f"comp_asin 格式不正确：{ca[:20]}")
            comps.append({"rank":_n(c.get("rank"),"comp_rank",int,1,1e6),"asin":ca,"brand":_s(c.get("brand"),"comp_brand",False),"title":_s(c.get("title"),"comp_title"),
                "bullets":[_s(b,"comp_bullets 项") for b in (c.get("bullets") or []) if str(b).strip()][:10],
                "price":_n(c.get("price"),"comp_price",float,0,1e6),"rating":_n(c.get("rating"),"comp_rating",float,0,5),"reviews":_n(c.get("reviews"),"comp_reviews",int,0,1e9)})
        if not comps: raise Bad("至少需要 1 个竞品")
        _price=_n(p.get("price"),"price",float,0,1e6); _cost=_n(p.get("cost"),"cost",float,0,5e6,allow_none=True)
        if _cost is not None and _cost>_price*5+0.01: raise Bad("cost 超出范围：不应超过售价的 5 倍")
        if len(comps)>MAX_COMPS: raise Bad(f"竞品最多 {MAX_COMPS} 个")
        comps.sort(key=lambda c:c["rank"])
        return {"asin":asin,"name":_s(p.get("name"),"name",False) or asin,"noun":_s(p.get("noun"),"noun"),"category":_s(p.get("category"),"category",False) or "General",
                "price":_n(p.get("price"),"price",float,0,1e6),
                "cost":_n(p.get("cost"),"cost",float,0,5e6,allow_none=True),"fee_rate":_n(p.get("fee_rate"),"fee_rate",float,0,0.8,allow_none=True),"cvr":_n(p.get("cvr"),"cvr",float,0.01,0.5,allow_none=True),"features":feats[:10],"keywords":kws[:30],"competitors":comps}
    except Bad as e: raise Bad(f"{where}：{e}")
def _split(v): return [x.strip() for x in str(v or "").split("|") if x.strip()]
def _rows_to_products(rows):
    if not rows: raise Bad("文件没有数据行")
    head=[str(h or "").strip().lower() for h in rows[0]]
    miss=[c for c in COLUMNS if c not in head and c not in OPTIONAL]
    if miss: raise Bad("缺少列："+", ".join(miss)+"（请下载模板对照表头）")
    idx={c:(head.index(c) if c in head else 10**6) for c in COLUMNS}; prods={}; order=[]
    for n,r in enumerate(rows[1:],start=2):
        g=lambda c:(r[idx[c]] if idx[c]<len(r) else None)
        if all(x is None or str(x).strip()=="" for x in r): continue
        a=str(g("asin") or "").strip()
        if not a: raise Bad(f"第 {n} 行：asin 不能为空")
        if a not in prods:
            if len(prods)>=MAX_PRODUCTS: raise Bad(f"商品最多 {MAX_PRODUCTS} 个")
            kws=[]
            for k in _split(g("keywords")):
                parts=k.rsplit(":",2)
                if len(parts)!=3: raise Bad(f"第 {n} 行：keywords 格式应为 关键词:搜索量:排名，收到 {k[:40]}")
                kws.append({"keyword":parts[0],"search_volume":parts[1],"rank":parts[2]})
            prods[a]={"asin":a,"name":g("name"),"noun":g("noun"),"category":g("category"),"price":g("price"),"cost":g("cost"),"fee_rate":g("fee_rate"),"cvr":g("cvr"),"features":_split(g("features")),"keywords":kws,"competitors":[],"_row":n}
            order.append(a)
        if str(g("comp_asin") or "").strip():
            if len(prods[a]["competitors"])>=MAX_COMPS: raise Bad(f"第 {n} 行：商品 {a} 竞品超过 {MAX_COMPS} 个")
            prods[a]["competitors"].append({"rank":g("comp_rank"),"asin":g("comp_asin"),"brand":g("comp_brand"),"title":g("comp_title"),"price":g("comp_price"),
                "rating":g("comp_rating"),"reviews":g("comp_reviews"),"bullets":_split(g("comp_bullets"))})
    return [_norm(prods[a],f"第 {prods[a]['_row']} 行（{a}）") for a in order]
def _xlsx_rows(b):
    try: z=zipfile.ZipFile(io.BytesIO(b))
    except zipfile.BadZipFile: raise Bad("不是有效的 .xlsx 文件")
    infos=z.infolist()
    if len(infos)>200 or sum(i.file_size for i in infos)>30*1024*1024: raise Bad("xlsx 内容过大或结构异常")
    if any(i.filename.endswith(".bin") and "vba" in i.filename.lower() for i in infos): raise Bad("不接受含宏的文件")
    import openpyxl
    try:
        wb=openpyxl.load_workbook(io.BytesIO(b),read_only=True,data_only=True)
        ws=wb.worksheets[0]; rows=[]
        for r in ws.iter_rows(values_only=True,max_col=40):
            rows.append(list(r))
            if len(rows)>MAX_PRODUCTS*MAX_COMPS+50: raise Bad("行数过多")
        wb.close(); return rows
    except Bad: raise
    except Exception: raise Bad("xlsx 解析失败，请用模板另存后重试")
def parse(filename,b):
    fn=(filename or "").strip()
    ext=fn.rsplit(".",1)[-1].lower() if "." in fn else ""
    if not b: raise Bad("文件为空")
    if len(b)>MAX_BYTES: raise Bad("文件超过 2MB")
    if ext=="json":
        try: d=json.loads(b.decode("utf-8-sig"))
        except Exception: raise Bad("JSON 格式错误或不是 UTF-8 编码")
        ps=d.get("products") if isinstance(d,dict) else d
        if not isinstance(ps,list) or not ps: raise Bad("JSON 需包含非空的 products 数组（结构同示例 mock_data.json）")
        if len(ps)>MAX_PRODUCTS: raise Bad(f"商品最多 {MAX_PRODUCTS} 个")
        out=[_norm(p,f"products[{i}]") for i,p in enumerate(ps)]
    elif ext=="csv":
        try: txt=b.decode("utf-8-sig")
        except UnicodeDecodeError:
            try: txt=b.decode("gb18030")
            except UnicodeDecodeError: raise Bad("CSV 编码无法识别，请存为 UTF-8")
        out=_rows_to_products(list(csv.reader(io.StringIO(txt))))
    elif ext=="xlsx": out=_rows_to_products(_xlsx_rows(b))
    else: raise Bad("只支持 .xlsx / .csv / .json 文件")
    if len({p["asin"] for p in out})!=len(out): raise Bad("存在重复的 asin")
    return out
def flat_rows(products):
    rows=[COLUMNS]
    for p in products:
        kw="|".join(f'{k["keyword"]}:{k["search_volume"] if k["search_volume"] is not None else ""}:{k["rank"] if k["rank"] is not None else ""}' for k in p["keywords"])
        for i,c in enumerate(p["competitors"]):
            opt=lambda k:"" if p.get(k) is None else p[k]
            base=[p["asin"],p["name"],p["noun"],p["category"],p["price"],opt("cost"),opt("fee_rate"),opt("cvr"),"|".join(p["features"]),kw] if i==0 else [p["asin"]]+[""]*9
            rows.append(base+[c["rank"],c["asin"],c.get("brand",""),c["title"],c["price"],c["rating"],c["reviews"],"|".join(c["bullets"])])
    return rows
def template(fmt,products):
    if fmt=="json": return json.dumps({"products":products},ensure_ascii=False,indent=1).encode(),"application/json; charset=utf-8"
    rows=flat_rows(products)
    if fmt=="csv":
        s=io.StringIO(); csv.writer(s).writerows(rows); return ("\ufeff"+s.getvalue()).encode(),"text/csv; charset=utf-8"
    import openpyxl
    wb=openpyxl.Workbook(); ws=wb.active; ws.title="products"
    for r in rows: ws.append(r)
    h=wb.create_sheet("说明"); h.append(["列名","说明"])
    for c in COLUMNS: h.append([c,HELP[c]])
    h.append(["",""]); h.append(["规则","同一商品多行=多个竞品；商品字段只需在该商品第一行填写；只读取第一个工作表；竞品行的 name 留空（name 只代表我方商品），竞品品牌写在 comp_brand；cost/fee_rate/cvr 可留空，留空时广告估算用示例假设并在页面标明"])
    s=io.BytesIO(); wb.save(s); return s.getvalue(),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
