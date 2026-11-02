"""纯代码分析，不调用模型。"""
import re
def _words(t): return set(re.findall(r"[a-z0-9&]+(?:[- ][a-z0-9&]+)?",t.lower()))
STOP={"daily","use","what","you","get","x","1","designed","user","guide","for","with","and","the","a","&","aurora","vela","kino","mira","pluto","zest","orca","lumi"}
def analyze(p):
    comps=p["competitors"]; top3=[c["reviews"] for c in comps[:3]]
    if all(r<100 for r in top3): level="低"
    elif all(r<1000 for r in top3): level="中"
    else: level="高"
    mine=(" ".join(p["features"])+" "+p["noun"]).lower()
    text=[(c["title"]+" "+" ".join(c["bullets"])).lower() for c in comps]
    cands={}
    for k in p["keywords"]: cands[k["keyword"]]=1
    for t in text:
        w=re.findall(r"[a-z0-9&][a-z0-9&\-]*",t)
        for n in (2,3):
            for i in range(len(w)-n+1):
                if w[i] not in("for","with","and","the","a") and w[i+n-1] not in("for","with","and","the","a","x","1"): cands[" ".join(w[i:i+n])]=1
    gaps=[]
    for ph in cands:
        n=sum(re.search(r'(?<![a-z])'+re.escape(ph)+r'(?![a-z])',t) is not None for t in text)
        if n>=3 and not (set(ph.split())&(STOP-{'&'})) and not ph.split()[0]=='&' and ph.split()[-1]!='&' and ph not in mine and ph not in ("for","with","designed for daily use","user guide","what you get"):
            gaps.append((ph,n))
    gaps=[g for g,_ in sorted(gaps,key=lambda x:-x[1]) if len(g)>3]
    gaps=[g for g in gaps if not any(g!=o and g in o for o in gaps) or g=="hot & cold"]
    gaps=[g for g in gaps if not g.startswith("&") and not g.endswith("&")][:8]
    return {"competition":level,"top3_reviews":top3,"avg_price":round(sum(c["price"] for c in comps)/len(comps),2),
            "avg_rating":round(sum(c["rating"] for c in comps)/len(comps),2),"keyword_gaps":gaps,
            "unranked_keywords":[k["keyword"] for k in p["keywords"] if k["rank"] is None]}
