import os,json,re,urllib.request
from .validate import validate,feedback
SCHEMA={"type":"object","additionalProperties":False,"required":["title","bullets","backend_terms","ad_groups"],"properties":{
 "title":{"type":"string"},"bullets":{"type":"array","items":{"type":"string"}},"backend_terms":{"type":"string"},
 "ad_groups":{"type":"array","items":{"type":"object","additionalProperties":False,"required":["name","keywords","match_type","suggested_bid","budget_share"],
  "properties":{"name":{"type":"string"},"keywords":{"type":"array","items":{"type":"string"}},"match_type":{"type":"string"},"suggested_bid":{"type":"string"},"budget_share":{"type":"string"}}}}}}
RULES="""你是亚马逊美国站运营专家。根据给定的商品信息、关键词和竞品分析，用英文写 Listing 并给出广告方案（广告组名称可用中文）。
规则：标题≤200字符；正好5条五点，每条≤250字符；后台搜索词≤250字节、空格分隔、不得包含标题中已出现的任何单词；广告组≤15个；
禁用词：best, #1, guaranteed, 100%, cheapest, free shipping。不得编造数据中没有的数字：建议竞价和预算占比若无数据依据，填写"待验证"。"""
PROVIDERS={"deepseek":("DEEPSEEK","https://api.deepseek.com","deepseek-flash"),"xai":("XAI","https://api.x.ai/v1","grok-4.3"),"openai":("OPENAI","https://api.openai.com/v1","gpt-4.1-mini")}
EXTRA={"deepseek":'{"thinking":{"type":"disabled"}}'}  # 可用 <NAME>_EXTRA_BODY 覆盖
def chain():
    """可用链路：MODEL_CHAIN（默认 deepseek,xai）中已配置 key 的项。"""
    out=[]
    for n in os.environ.get("MODEL_CHAIN","deepseek,xai,openai").split(","):
        n=n.strip().lower()
        if n in PROVIDERS:
            pre,base,model=PROVIDERS[n]
            if os.environ.get(pre+"_API_KEY"):
                out.append({"name":n,"key":os.environ[pre+"_API_KEY"],"base":os.environ.get(pre+"_BASE_URL",base).rstrip("/"),
                            "model":os.environ.get(pre+"_MODEL",model),"timeout":int(os.environ.get(pre+"_TIMEOUT_SECONDS","60")),
                            "extra":json.loads(os.environ.get(pre+"_EXTRA_BODY",EXTRA.get(n,"{}")))})
    return out
def _call(pv,prompt):
    """OpenAI 兼容聊天接口，JSON 输出。返回 (dict,(in,out))；超时/HTTP 错误/空返回/结构不对都抛异常。"""
    body={"model":pv["model"],"messages":[{"role":"system","content":RULES+"\n只输出一个 JSON 对象，结构严格为："+json.dumps(SCHEMA,ensure_ascii=False)},{"role":"user","content":prompt}],
          "response_format":{"type":"json_object"},"temperature":0.4,"max_tokens":int(os.environ.get("MAX_TOKENS","3000")),**pv["extra"]}
    req=urllib.request.Request(pv["base"]+"/chat/completions",json.dumps(body).encode(),{"Content-Type":"application/json","Authorization":"Bearer "+pv["key"]})
    d=json.load(urllib.request.urlopen(req,timeout=pv["timeout"]))
    txt=((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ch=(d.get("choices") or [{}])[0]
    if ch.get("finish_reason")=="length": raise OverflowError("truncated")
    if not txt.strip(): raise ValueError("empty response")
    i,j=txt.find("{"),txt.rfind("}")
    g=json.loads(txt[i:j+1] if i>=0 and j>i else txt)
    if not isinstance(g,dict) or not isinstance(g.get("bullets"),list) or not isinstance(g.get("ad_groups"),list): raise ValueError("bad schema")
    g={"title":str(g.get("title","")),"bullets":[str(b) for b in g["bullets"]],"backend_terms":str(g.get("backend_terms","")),
       "ad_groups":[{"name":str(x.get("name","")),"keywords":[str(k) for k in (x.get("keywords") or [])],"match_type":str(x.get("match_type","")),
                     "suggested_bid":str(x.get("suggested_bid","待验证")),"budget_share":str(x.get("budget_share","待验证"))} for x in g["ad_groups"] if isinstance(x,dict)]}
    u=d.get("usage") or {}
    return g,(u.get("prompt_tokens") or 0,u.get("completion_tokens") or 0)
def _errname(e):
    code=getattr(e,"code",None)
    return (f"HTTP {code}" if isinstance(code,int) else f"{type(e).__name__}:{str(e)[:30]}" if isinstance(e,(ValueError,OverflowError)) else type(e).__name__)[:60]
def template(p,a):
    f=p["features"]; n=p["noun"]; gaps=a["keyword_gaps"]
    title=f"{n} {f[0]}, {f[1].title()} with {f[2].title()}, {', '.join(g.title() for g in gaps[:2])}"[:200]
    bullets=[f"{x.upper()} – Built with {x} for reliable everyday use; details from product spec." for x in f]
    bullets.append(f"WHAT YOU GET – 1 x {n}. Suitable for {p['category'].lower()} use at home, office or travel.")
    tw=set(re.findall(r"\w+",title.lower())); words=[]
    for k in [k["keyword"] for k in p["keywords"]]+gaps:
        for w in re.findall(r"\w+",k.lower()):
            if w not in tw and w not in words: words.append(w)
    bt=""
    for w in words:
        if len((bt+" "+w).strip().encode())<=250: bt=(bt+" "+w).strip()
    groups=[]
    for i,k in enumerate(p["keywords"]):
        groups.append({"name":("核心词-" if k["rank"] else "拓展词-")+k["keyword"],"keywords":[k["keyword"]],
            "match_type":"精准" if k["rank"] and k["rank"]<50 else "词组","suggested_bid":"待验证","budget_share":"待验证"})
    if gaps: groups.append({"name":"竞品缺口词","keywords":gaps[:5],"match_type":"广泛","suggested_bid":"待验证","budget_share":"待验证"})
    return {"title":title,"bullets":bullets,"backend_terms":bt,"ad_groups":groups}
PROMPT_COMPS=8  # 提示词只取前 N 个竞品标题，页面仍显示全部
def generate(p,a,use_model=True,prefer=None,demo_reason=None):
    """返回 dict: g,v,mode,retries,err,model_used,chain(失败列表),tokens"""
    prompt=json.dumps({"product":{k:p[k] for k in("asin","noun","category","price","features")},"keywords":p["keywords"],"analysis":a,
        "competitor_titles":[(f'[{c["brand"]}] ' if c.get("brand") else "")+c["title"] for c in p["competitors"][:PROMPT_COMPS]]},ensure_ascii=False)
    ti=to=0; fails=[]
    pvs=chain() if use_model else []
    if prefer: pvs=[x for x in pvs if x["name"]==prefer]+[x for x in pvs if x["name"]!=prefer]
    for pv in pvs:
        try:
            g=None;msg=prompt
            for attempt in range(3):
                g,(i,o)=_call(pv,msg); ti+=i; to+=o; v=validate(g)
                if v["ok"]: break
                msg=prompt+"\n上次输出未通过校验，请修正："+feedback(v)
            else:
                tw=set(re.findall(r"\w+",g["title"].lower()))
                g["backend_terms"]=" ".join(w for w in g["backend_terms"].split() if not set(re.findall(r"\w+",w.lower()))&tw)
                v=validate(g); attempt=2
            return {"g":g,"v":v,"mode":"model","retries":attempt,"err":None,"model_used":f"{pv['name']}:{pv['model']}","chain":fails,"tokens":(ti,to)}
        except Exception as e:
            fails.append({"model":f"{pv['name']}:{pv['model']}","error":_errname(e)})
    err=(demo_reason or "force_fail 演示（不调模型）") if not use_model else ("所有模型均失败" if pvs else "未配置模型 key")
    g=template(p,a)
    return {"g":g,"v":validate(g),"mode":"demo","retries":0,"err":err,"model_used":None,"chain":fails,"tokens":(ti,to)}
