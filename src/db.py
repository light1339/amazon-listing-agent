"""记录写入 PostgreSQL（libpq 环境变量）。未设 PGHOST 时用内存（本地自测）。生成记录写库失败不影响返回结果。"""
import os,threading,itertools
try:
    import psycopg2,psycopg2.pool
    from psycopg2.extras import Json
except Exception: psycopg2=None
_pool=None;_lock=threading.Lock();_mem={};_quota={};_rev={};_ids=itertools.count(1)
def enabled(): return bool(psycopg2 and os.environ.get("PGHOST"))
def _p():
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None: _pool=psycopg2.pool.ThreadedConnectionPool(1,4)
    return _pool
def _run(sql,args):
    pool=_p(); c=pool.getconn(); bad=False
    try:
        with c, c.cursor() as cur:
            cur.execute(sql,args); return cur.fetchone()
    except Exception: bad=True; raise
    finally: pool.putconn(c,close=bad)
def save_generation(r):
    if not enabled(): i=next(_ids); _mem[i]=dict(r); return i
    v=r["validation"]
    try:
        return _run("""INSERT INTO amazon_agent.generations(asin,mode,model,model_used,fallback_chain,validation_ok,validation_passed,validation_failed,
          validation,retries,fallback_reason,forced_fail,result,client_ip,duration_ms,tokens_in,tokens_out,model_choice,data_source,product,image_requested,image_count,image_ok,images,quota_counted)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
          (r["asin"],r["mode"],r["model_used"],r["model_used"],Json(r["chain"]),v["ok"],v["passed"],v["failed"],Json(v),r["retries"],
           r["fallback_reason"],r["forced_fail"],Json(r["result"]),r["client_ip"],r["duration_ms"],r["tokens_in"],r["tokens_out"],r.get("model_choice"),r.get("data_source"),Json(r["product"]) if r.get("product") else None,
           bool(r.get("image_requested")),r.get("image_count") or 0,r.get("image_ok"),Json(r.get("images") or []),bool(r.get("quota_counted"))))[0]
    except Exception as e: print("db save_generation failed:",type(e).__name__,flush=True); return None
def get_generation(gid):
    if not enabled(): return _mem.get(gid)
    r=_run("SELECT asin,result,validation,product FROM amazon_agent.generations WHERE id=%s",(gid,))
    return r and {"asin":r[0],"result":r[1],"validation":r[2],"product":r[3]}
def save_review(gid,asin,snap,ip):
    if not enabled(): i=next(_ids); _rev[i]=(gid,asin,snap,ip); return i
    return _run("INSERT INTO amazon_agent.reviews(generation_id,asin,result_snapshot,client_ip) VALUES(%s,%s,%s,%s) RETURNING id",(gid,asin,Json(snap),ip))[0]
import datetime
def _today():
    return (datetime.datetime.utcnow()+datetime.timedelta(hours=8)).date()
def reserve(kind,n,limit):
    """原子占用当日（Asia/Shanghai）额度；成功返回 True。DB 出错时按失败处理（保守，不调付费模型）。"""
    if n>limit: return False
    if not enabled():
        with _lock:
            k=(_today(),kind); u=_quota.get(k,0)
            if u+n>limit: return False
            _quota[k]=u+n; return True
    try:
        r=_run("""INSERT INTO amazon_agent.daily_quota(day,kind,used) VALUES((now() AT TIME ZONE 'Asia/Shanghai')::date,%s,%s)
          ON CONFLICT(day,kind) DO UPDATE SET used=amazon_agent.daily_quota.used+EXCLUDED.used
          WHERE amazon_agent.daily_quota.used+EXCLUDED.used<=%s RETURNING used""",(kind,n,limit))
        return r is not None
    except Exception as e: print("db reserve failed:",type(e).__name__,flush=True); return False
def used(kind):
    if not enabled(): return _quota.get((_today(),kind),0)
    try:
        r=_run("SELECT used FROM amazon_agent.daily_quota WHERE day=(now() AT TIME ZONE 'Asia/Shanghai')::date AND kind=%s",(kind,))
        return r[0] if r else 0
    except Exception: return None
