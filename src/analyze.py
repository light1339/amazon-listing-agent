"""纯代码分析，不调用模型。"""
import re
def _words(t): return set(re.findall(r"[a-z0-9&]+(?:[- ][a-z0-9&]+)?",t.lower()))
STOP={"daily","use","what","you","get","x","1","designed","user","guide","for","with","and","the","a","&","aurora","vela","kino","mira","pluto","zest","orca","lumi"}
def analyze(p):
    comps=p["competitors"]; _B={c["title"].split()[0].lower() for c in comps}|{m.lower() for c in comps for m in re.findall(r"\bby (\w+)",c["title"])}
    top3=[c["reviews"] for c in comps[:3]]
    if all(r<100 for r in top3): level="低"
    elif all(r<1000 for r in top3): level="中"
    else: level="高"
    mine=(" ".join(p["features"])+" "+p["noun"]).lower()
    text=[(c["title"]+" | "+" | ".join(b.split(" – ")[0] if " – " in b else b for b in c["bullets"])).lower() for c in comps]
    cands={}
    for k in p["keywords"]: cands[k["keyword"]]=1
    for t in text:
        w=re.findall(r"[a-z0-9&][a-z0-9&\-]*",t)
        for n in (2,3):
            for i in range(len(w)-n+1):
                if w[i] not in("for","with","and","the","a") and w[i+n-1] not in("for","with","and","the","a","x","1","by") and w[i] not in("by","fits","save","moisture"): cands[" ".join(w[i:i+n])]=1
    gaps=[]
    for ph in cands:
        n=sum(re.search(r'(?<![a-z])'+re.escape(ph)+r'(?![a-z])',t) is not None for t in text)
        if n>=3 and not (set(ph.split())&((STOP|_B)-{'&'})) and not ph.split()[0]=='&' and ph.split()[-1]!='&' and ph not in mine and ph not in ("for","with","designed for daily use","user guide","what you get"):
            gaps.append((ph,n))
    gaps=[g for g,_ in sorted(gaps,key=lambda x:-x[1]) if len(g)>3]
    gaps=[g for g in gaps if not any(g!=o and g in o for o in gaps) or g=="hot & cold"]
    gaps=[g for g in gaps if not g.startswith("&") and not g.endswith("&")][:8]
    ps=sorted(c["price"] for c in comps); rv=sorted(c["reviews"] for c in comps)
    lo,hi=ps[0],ps[-1]; step=(hi-lo)/3 or 1
    bands=[{"range":f"${lo+step*i:.0f}–${lo+step*(i+1):.0f}","count":sum(1 for x in ps if (lo+step*i<=x<lo+step*(i+1)) or (i==2 and x==hi))} for i in range(3)]
    fc={}
    for c in comps:
        for b in c["bullets"]:
            h=b.split(" – ")[0].strip() if " – " in b else ""
            if h and h!="WHAT YOU GET": fc[h]=fc.get(h,0)+1
    top_feats=[{"feature":k,"count":v} for k,v in sorted(fc.items(),key=lambda x:-x[1])[:8]]
    kw_opps=sorted([{"keyword":k["keyword"],"search_volume":k["search_volume"]} for k in p["keywords"] if k["rank"] is None and k["search_volume"]],key=lambda x:-x["search_volume"])
    newc=[c for c in comps if c["reviews"]<100]
    extra={"n_competitors":len(comps),"price_min":lo,"price_max":hi,"price_bands":bands,"my_price":p.get("price"),
      "my_price_pct":round(100*sum(1 for x in ps if x<(p.get("price") or 0))/len(ps)),
      "median_reviews":rv[len(rv)//2],"review_threshold":sorted(rv,reverse=True)[min(4,len(rv)-1)],
      "new_entrants":len(newc),"top_features":top_feats,"keyword_opportunities":kw_opps}
    return {**extra,"competition":level,"top3_reviews":top3,"avg_price":round(sum(c["price"] for c in comps)/len(comps),2),
            "avg_rating":round(sum(c["rating"] for c in comps)/len(comps),2),"keyword_gaps":gaps,
            "unranked_keywords":[k["keyword"] for k in p["keywords"] if k["rank"] is None]}
