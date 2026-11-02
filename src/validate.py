import re
LIMITS={"title":200,"bullet":250,"backend_bytes":250,"ad_groups":15}
BANNED=["best","#1","guaranteed","100%","cheapest","free shipping"]
def _banned(t): return [b for b in BANNED if re.search(r"(?<!\w)"+re.escape(b)+r"(?!\w)",t.lower())]
def validate(g):
    res=[]
    def add(field,length,limit,unit,extra=None):
        errs=list(extra or [])
        if length>limit: errs.append(f"超出 {length-limit} {unit}")
        res.append({"field":field,"length":length,"limit":limit,"unit":unit,"ok":not errs,"errors":errs})
    t=g.get("title","")
    add("标题",len(t),LIMITS["title"],"字符",[f"违禁词 {w}" for w in _banned(t)])
    for i,b in enumerate(g.get("bullets",[])[:5],1):
        add(f"五点 {i}",len(b),LIMITS["bullet"],"字符",[f"违禁词 {w}" for w in _banned(b)])
    if len(g.get("bullets",[]))!=5: res.append({"field":"五点数量","length":len(g.get("bullets",[])),"limit":5,"unit":"条","ok":False,"errors":["必须正好 5 条"]})
    bt=g.get("backend_terms","")
    tw=set(re.findall(r"\w+",t.lower()))
    rep=sorted(set(w for w in re.findall(r"\w+",bt.lower()) if w in tw))
    add("后台搜索词",len(bt.encode()),LIMITS["backend_bytes"],"字节",([f"与标题重复：{', '.join(rep)}"] if rep else [])+[f"违禁词 {w}" for w in _banned(bt)])
    add("广告组数量",len(g.get("ad_groups",[])),LIMITS["ad_groups"],"个")
    return {"items":res,"passed":sum(r["ok"] for r in res),"failed":sum(not r["ok"] for r in res),"ok":all(r["ok"] for r in res)}
def feedback(v): return "; ".join(f"{r['field']}: {', '.join(r['errors'])}" for r in v["items"] if not r["ok"])
