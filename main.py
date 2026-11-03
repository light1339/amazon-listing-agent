"""启动：python3 main.py [--port N]  （仅绑定 127.0.0.1，公网经 nginx /amazon-agent/ 反代）"""
import json,os,socket,sys,time,threading,urllib.parse
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from src.analyze import analyze
from src.generate import generate,chain
from src.export import export
from src.validate import validate
from src import db,upload,images,adcalc
import secrets,uuid,re,unicodedata
Q_MAX=80
NO_COMP="无竞品数据，请上传文件获得竞品分析"
def brief(p): return {"asin":p["asin"],"name":p["name"],"noun":str(p.get("noun") or "")[:120],"keywords":[str(k.get("keyword",""))[:60] for k in (p.get("keywords") or [])[:12] if isinstance(k,dict)]}
def clean_q(x):
    if not isinstance(x,str): return None
    x="".join(c for c in x if not unicodedata.category(c).startswith("C"))
    return re.sub(r"\s+"," ",x).strip()
ROOT=os.path.dirname(os.path.abspath(__file__))
MAX_BODY=16384
GEN_LIMIT=int(os.environ.get("DAILY_GEN_LIMIT","100")); IMG_LIMIT=int(os.environ.get("DAILY_IMAGE_LIMIT","100")); IMG_PER=2
SLOTS=threading.BoundedSemaphore(int(os.environ.get("MAX_CONCURRENT","4")))
def data(): return json.load(open(os.path.join(ROOT,"data","mock_data.json"),encoding="utf-8"))
def prod(asin): return next(p for p in data()["products"] if p["asin"]==asin)
UPLOADS={}; UP_LOCK=threading.Lock(); UP_TTL=7200; UP_MAX=300
MODEL_CHOICES={"auto":"自动（DeepSeek→Grok→OpenAI）","deepseek":"DeepSeek","xai":"Grok","openai":"OpenAI"}
def up_put(fn,ps):
    uid=secrets.token_urlsafe(16); now=time.time()
    with UP_LOCK:
        for k in [k for k,v in UPLOADS.items() if now-v[0]>UP_TTL]: UPLOADS.pop(k,None)
        while len(UPLOADS)>=UP_MAX: UPLOADS.pop(min(UPLOADS,key=lambda k:UPLOADS[k][0]))
        UPLOADS[uid]=(now,fn,ps)
    return uid
def up_get(uid):
    with UP_LOCK:
        v=UPLOADS.get(uid)
        return v if v and time.time()-v[0]<=UP_TTL else None
class Srv(ThreadingHTTPServer):
    daemon_threads=True; request_queue_size=32
class H(BaseHTTPRequestHandler):
    timeout=30  # 慢连接读超时
    def _send(self,code,body,ctype="application/json; charset=utf-8",extra=None):
        if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False,default=str).encode()
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(body)))
        self.send_header("X-Content-Type-Options","nosniff")
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def _ip(self):
        ip=(self.headers.get("X-Real-IP") or self.client_address[0]).strip()
        return ip if len(ip)<=45 and all(c in "0123456789abcdefABCDEF.:" for c in ip) else None
    def _body(self):
        try: n=int(self.headers.get("Content-Length",""))
        except ValueError: return None,(411,{"error":"需要 Content-Length"})
        if n<0 or n>MAX_BODY: return None,(413,{"error":"请求体过大"})
        try:
            req=json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(req,dict): raise ValueError
            return req,None
        except Exception: return None,(400,{"error":"非法 JSON"})
    def do_GET(self):
        u=urllib.parse.urlparse(self.path); path=u.path.rstrip("/").split("/")[-1] if u.path not in("/","") else ""
        if path in("","index.html"): return self._send(200,open(os.path.join(ROOT,"static","index.html"),"rb").read(),"text/html; charset=utf-8")
        if path=="products":
            d=data(); return self._send(200,{"note":d["_note"],"datasets":d["datasets"],"products":[brief(p) for p in d["products"]]})
        if path=="models":
            av={x["name"] for x in chain()}
            return self._send(200,{"choices":[{"value":k,"label":v,"available":k=="auto" or k in av} for k,v in MODEL_CHOICES.items()]})
        if path=="template":
            fmt=urllib.parse.parse_qs(u.query).get("fmt",["xlsx"])[0]
            if fmt not in("xlsx","csv","json"): return self._send(400,{"error":"fmt 只能是 xlsx/csv/json"})
            b,ct=upload.template(fmt,data()["products"])
            return self._send(200,b,ct,{"Content-Disposition":f'attachment; filename="amazon_agent_template.{fmt}"'})
        if path=="quota":
            return self._send(200,{"gen_limit":GEN_LIMIT,"gen_used":db.used("gen"),"image_limit":IMG_LIMIT,"image_used":db.used("image"),"images_available":images.enabled()})
        if u.path.rstrip("/").split("/")[-2:-1]==["image"]:
            fp=images.path(path)
            if not fp: return self._send(404,{"error":"图片不存在或已过期"})
            b=open(fp,"rb").read()
            return self._send(200,b,images.ctype(b),{"Cache-Control":"private, max-age=86400","Content-Security-Policy":"default-src 'none'"})
        if path=="columns": return self._send(200,{"columns":[{"name":c,"desc":upload.HELP[c]} for c in upload.COLUMNS]})
        if path=="export":
            q=urllib.parse.parse_qs(u.query)
            try: gid=int(q.get("generation_id",[""])[0]); rec=db.get_generation(gid)
            except Exception: rec=None
            if not rec: return self._send(404,{"error":"请先生成"})
            p=rec.get("product") or prod(rec["asin"]); a=analyze(p); a["ad_calc"]=(rec["result"] or {}).get("ad_calc") or adcalc.calc(p,a)
            return self._send(200,export(p,a,rec["result"],rec["validation"]),"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",{"Content-Disposition":f'attachment; filename="listing_{p["asin"]}_{gid}.xlsx"'})
        self._send(404,{"error":"not found"})
    def do_POST(self):
        path=self.path.split("?")[0].rstrip("/").split("/")[-1]
        if path=="upload": return self._upload()
        if path=="regen_image": return self._regen_image()
        if path not in("generate","review"): return self._send(404,{"error":"not found"})
        req,err=self._body()
        if err: return self._send(*err)
        if path=="generate":
            mc=req.get("model") or "auto"
            if mc not in MODEL_CHOICES: return self._send(400,{"error":"不支持的模型选项"})
            if req.get("upload_id"):
                up=up_get(str(req["upload_id"]))
                if not up: return self._send(400,{"error":"上传的文件已过期，请重新上传"})
                ps=up[2]; src="upload:"+up[1]
            else: ps=data()["products"]; src="sample:mock_data.json"
            raw=req.get("query",req.get("asin"))
            q=clean_q(raw)
            if not q: return self._send(400,{"error":"请输入 ASIN 或关键词，或从文档中选择"})
            if len(q)>Q_MAX: return self._send(400,{"error":f"输入过长（最多 {Q_MAX} 个字符）"})
            p=next((x for x in ps if x["asin"].upper()==q.upper() or q=="%s · %s"%(x["asin"],x["name"])),None)
            if not p: return self._send(400,{"error":NO_COMP,"code":"no_match","products":[brief(x) for x in ps]})
            if not SLOTS.acquire(timeout=5): return self._send(503,{"error":"当前生成人数较多，请稍后再试"})
            try:
                t0=time.time(); forced=bool(req.get("force_fail")); a=analyze(p)
                want_img=bool(req.get("images")); img=None; img_th=None; img_note=None
                if want_img and not forced:
                    if not images.enabled(): img_note="未配置生图 key"
                    elif not db.reserve("image",IMG_PER,IMG_LIMIT): img_note="今日商品图额度已用完"
                    else:
                        box={}
                        img_th=threading.Thread(target=lambda:box.update(images.generate(p))); img_th.start()
                elif want_img: img_note="演示模式不生成商品图"
                counted=False; quota_out=False
                if not forced and chain():
                    counted=db.reserve("gen",1,GEN_LIMIT); quota_out=not counted
                r=generate(p,a,use_model=counted,prefer=None if mc=="auto" else mc,demo_reason="今日真实模型额度已用完" if quota_out else None); g,v=r["g"],r["v"]
                ac=adcalc.calc(p,a); [(x.pop("suggested_bid",None),x.pop("budget_share",None)) for x in g["ad_groups"]]; g["ad_calc"]=ac; a={**a,"ad_calc":ac}  # 出价/预算只由代码估算（ad_calc），广告组不再带这两项
                if img_th:
                    img_th.join(); img={"images":box.get("images",[]),"errors":box.get("errors",["未知错误"])}
                    if not img["images"]: img_note="商品图生成失败，可重试"
                    elif img["errors"]: img_note="部分商品图生成失败，可重试"
                if forced:  # 演示：故意让五点 2 超长（不调用模型）
                    g["bullets"][1]=g["bullets"][1]+" Extra filler text to demonstrate the over-limit check."*5; v=validate(g)
                gid=db.save_generation({"asin":p["asin"],"mode":r["mode"],"model_used":r["model_used"],"chain":r["chain"],"validation":v,"retries":r["retries"],
                    "fallback_reason":r["err"],"forced_fail":forced,"result":g,"client_ip":self._ip(),"duration_ms":int((time.time()-t0)*1000),
                    "tokens_in":r["tokens"][0],"tokens_out":r["tokens"][1],"model_choice":mc,"data_source":src,"product":p,
                    "image_requested":want_img,"image_count":len(img["images"]) if img else 0,"image_ok":(bool(img["images"]) and not img["errors"]) if img else None,
                    "images":(img["images"] if img else [])+([{"error":e} for e in img["errors"]] if img else []),"quota_counted":counted})
            finally: SLOTS.release()
            return self._send(200,{"generation_id":gid,"product":{k:p[k] for k in("asin","name","noun","price")},"competitors":p["competitors"],"analysis":a,"result":g,
                "validation":v,"mode":r["mode"],"model_used":r["model_used"],"fallback_chain":r["chain"],"retries":r["retries"],"fallback_reason":r["err"],"model_choice":mc,"data_source":src,
                "quota_exhausted":quota_out,"images_requested":want_img,"images":[{"url":"api/image/"+x["id"],"kind":x["kind"],"label":x["label"]} for x in (img["images"] if img else [])],"image_note":img_note})
        try: gid=int(req.get("generation_id"))
        except Exception: return self._send(400,{"error":"缺少 generation_id"})
        try:
            rec=db.get_generation(gid)
            if not rec: return self._send(404,{"error":"生成记录不存在"})
            rid=db.save_review(gid,rec["asin"],rec["result"],self._ip())
        except Exception as e:
            print("db review failed:",type(e).__name__,flush=True); return self._send(500,{"error":"记录失败，请稍后再试"})
        return self._send(200,{"status":"已提交审核","review_id":rid,"generation_id":gid,"asin":rec["asin"]})
    def _regen_image(self):
        req,err=self._body()
        if err: return self._send(*err)
        kind=req.get("kind")
        if kind not in [k[0] for k in images.KINDS]: return self._send(400,{"error":"不支持的图片类型"})
        try: rec=db.get_generation(int(req.get("generation_id")))
        except Exception: rec=None
        if not rec or not rec.get("product"): return self._send(404,{"error":"请先生成"})
        if not images.enabled(): return self._send(400,{"error":"未配置生图 key"})
        if not db.reserve("image",1,IMG_LIMIT): return self._send(429,{"error":"今日商品图额度已用完"})
        if not SLOTS.acquire(timeout=5): return self._send(503,{"error":"当前生成人数较多，请稍后再试"})
        try: r=images.generate(rec["product"],only=kind)
        finally: SLOTS.release()
        if not r["images"]: return self._send(502,{"error":"商品图生成失败，可重试"})
        x=r["images"][0]; print("image regen gen=%s kind=%s ok"%(req.get("generation_id"),kind),flush=True)
        return self._send(200,{"url":"api/image/"+x["id"],"kind":x["kind"],"label":x["label"]})
    def _upload(self):
        try: n=int(self.headers.get("Content-Length",""))
        except ValueError: return self._send(411,{"error":"需要 Content-Length"})
        if n<=0: return self._send(400,{"error":"文件为空"})
        if n>upload.MAX_BYTES: return self._send(413,{"error":"文件超过 2MB"})
        fn=urllib.parse.unquote(self.headers.get("X-Filename",""))
        fn=os.path.basename(fn.replace("\\","/"))[:120]
        if not fn or any(ord(c)<32 for c in fn): return self._send(400,{"error":"缺少文件名"})
        b=self.rfile.read(n)
        try: ps=upload.parse(fn,b)
        except upload.Bad as e: return self._send(400,{"error":str(e)})
        except Exception as e:
            print("upload parse failed:",type(e).__name__,flush=True); return self._send(400,{"error":"文件解析失败，请对照模板检查"})
        uid=up_put(fn,ps)
        return self._send(200,{"upload_id":uid,"filename":fn,"count":len(ps),"products":[brief(p) for p in ps]})
    def log_message(self,*a): pass
def free_port():
    s=socket.socket(); s.bind(("127.0.0.1",0)); p=s.getsockname()[1]; s.close(); return p
if __name__=="__main__":
    port=int(sys.argv[sys.argv.index("--port")+1]) if "--port" in sys.argv else int(os.environ.get("PORT",0)) or free_port()
    c=chain()
    print(f"http://127.0.0.1:{port}/  模型链路：{' → '.join(x['name']+':'+x['model'] for x in c) or '无'} → 演示模式  记录：{'PostgreSQL' if db.enabled() else '内存'}",flush=True)
    Srv(("127.0.0.1",port),H).serve_forever()
