"""商品展示图：OpenAI 生图（默认 gpt-image-1.5，quality low），保存到私有目录，按随机 id 只读访问，7 天清理。"""
import os,re,json,time,base64,secrets,threading,urllib.request
DIR=os.environ.get("IMAGE_DIR",os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"images"))
MODEL=os.environ.get("IMAGE_MODEL","gpt-image-1.5"); QUALITY=os.environ.get("IMAGE_QUALITY","low")
TIMEOUT=int(os.environ.get("IMAGE_TIMEOUT_SECONDS","150")); KEEP=7*86400
ID_RE=re.compile(r"^[A-Za-z0-9_-]{22}$")
KINDS=[("main","白底主图","Professional Amazon main product photo of {n}. Pure white background (#FFFFFF), product centered and filling about 85% of the frame, soft studio lighting, realistic, no text, no logos, no watermark, no props. Key features: {f}."),
       ("scene","场景图","Realistic lifestyle photo of {n} in use in a natural {c} setting, attractive composition, natural light, product clearly visible, no text, no logos, no watermark. Highlights: {f}.")]
def enabled(): return bool(os.environ.get("OPENAI_API_KEY"))
def _one(prompt):
    base=os.environ.get("OPENAI_BASE_URL","https://api.openai.com/v1").rstrip("/")
    body={"model":MODEL,"prompt":prompt,"size":"1024x1024","quality":QUALITY,"n":1}
    req=urllib.request.Request(base+"/images/generations",json.dumps(body).encode(),{"Content-Type":"application/json","Authorization":"Bearer "+os.environ["OPENAI_API_KEY"]})
    d=json.load(urllib.request.urlopen(req,timeout=TIMEOUT))
    b=((d.get("data") or [{}])[0]).get("b64_json")
    if not b: raise ValueError("no image")
    raw=base64.b64decode(b)
    if raw[:8]!=b"\x89PNG\r\n\x1a\n" and raw[:3]!=b"\xff\xd8\xff" and raw[:4]!=b"RIFF": raise ValueError("bad image")
    os.makedirs(DIR,mode=0o750,exist_ok=True)
    iid=secrets.token_urlsafe(16)
    with open(os.path.join(DIR,iid),"wb") as f: f.write(raw)
    return iid
def cleanup():
    try:
        now=time.time()
        for n in os.listdir(DIR):
            p=os.path.join(DIR,n)
            if ID_RE.match(n) and now-os.path.getmtime(p)>KEEP: os.remove(p)
    except FileNotFoundError: pass
    except Exception as e: print("image cleanup failed:",type(e).__name__,flush=True)
def generate(p,only=None):
    """并行生成 2 张；返回 {"images":[{id,kind,label}],"errors":[...]}"""
    feats=", ".join(str(x) for x in (p.get("features") or [])[:4]); n=str(p.get("noun") or p.get("name"))[:120]; c=str(p.get("category") or "home")[:60].lower()
    ks=[k for k in KINDS if not only or k[0]==only]; out=[None]*len(ks); errs=[]
    def w(i,k,label,tpl):
        try: out[i]={"id":_one(tpl.format(n=n,f=feats,c=c)),"kind":k,"label":label}
        except Exception as e:
            code=getattr(e,"code",None); errs.append(f"{label}:"+(f"HTTP {code}" if isinstance(code,int) else type(e).__name__))
    ts=[threading.Thread(target=w,args=(i,*k)) for i,k in enumerate(ks)]
    for t in ts: t.start()
    for t in ts: t.join()
    threading.Thread(target=cleanup,daemon=True).start()
    return {"images":[x for x in out if x],"errors":errs}
def path(iid):
    if not ID_RE.match(iid or ""): return None
    p=os.path.join(DIR,iid)
    return p if os.path.isfile(p) else None
def ctype(b): return "image/png" if b[:4]==b"\x89PNG" else "image/jpeg" if b[:3]==b"\xff\xd8\xff" else "image/webp"
