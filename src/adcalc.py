"""广告出价与预算估算：纯代码计算，不调用大模型。

公式（全部基于售价、成本、费用率、转化率；不是真实广告数据）：
  单件利润      = 售价 − 成本 − 售价 × fee_rate（佣金+配送）
  利润率        = 单件利润 / 售价
  盈亏平衡 ACoS = 利润率（广告花费占销售额超过它就亏）
  目标 ACoS     = 盈亏平衡 ACoS × 70%（留 30% 利润空间，不超过盈亏平衡）
  建议最高出价  = 售价 × 目标 ACoS × 转化率（每次点击最多能花多少）
  建议起步出价  = 最高出价 × 0.7
  建议日预算    = 最高出价 × 预计每日点击数；预计日订单 = 点击数 × 转化率
利润率 ≤ 0 时不给出价。
"""
TARGET_RATIO=0.70; START_RATIO=0.70
DEFAULTS={"cost_ratio":0.30,"fee_rate":0.30,"cvr":0.10,"daily_clicks":30}
SRC_FILE="表格提供"; SRC_ASSUME="示例假设"
def _m(x): return round(x+1e-9,2)          # 美分
def _pct(x): return round(x*100)            # 百分比整数
def _median(xs):
    s=sorted(xs); n=len(s)
    return None if not n else (s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2)
def calc(p,a=None):
    """p: 商品（price 必填；cost/fee_rate/cvr 可选）；a: analyze() 结果（复用 my_price_pct）。返回 dict。"""
    price=float(p.get("price") or 0)
    def pick(k,default):
        v=p.get(k)
        return (float(v),SRC_FILE) if v is not None and v!="" else (default,SRC_ASSUME)
    cost,cs=pick("cost",price*DEFAULTS["cost_ratio"])
    fee,fs=pick("fee_rate",DEFAULTS["fee_rate"])
    cvr,vs=pick("cvr",DEFAULTS["cvr"])
    clicks=DEFAULTS["daily_clicks"]
    inputs=[
        {"key":"price","label":"我方售价","value":_m(price),"unit":"$","source":SRC_FILE},
        {"key":"cost","label":"进货成本","value":_m(cost),"unit":"$","source":cs,"note":"" if cs==SRC_FILE else "按售价 30% 假设"},
        {"key":"fee_rate","label":"佣金+配送费率","value":_pct(fee),"unit":"%","source":fs},
        {"key":"cvr","label":"点击转化率","value":round(cvr*100,1),"unit":"%","source":vs},
        {"key":"daily_clicks","label":"预计每日点击","value":clicks,"unit":"次","source":SRC_ASSUME}]
    comp=[c["price"] for c in p.get("competitors") or [] if c.get("price") is not None]
    med=_median(comp)
    price_pos=None
    if med:
        diff=(price-med)/med
        price_pos={"comp_median":_m(med),"diff_pct":_pct(diff),"my_price_pct":(a or {}).get("my_price_pct"),
                   "text":f"我方 ${price:.2f}，竞品中位价 ${med:.2f}，"+("持平" if abs(diff)<0.03 else f"{'高' if diff>0 else '低'} {abs(_pct(diff))}%")}
    unit_fee=price*fee; profit=price-cost-unit_fee
    margin=profit/price if price>0 else 0
    base={"inputs":inputs,"unit_profit":_m(profit),"unit_fee":_m(unit_fee),"margin_pct":_pct(margin),"price_position":price_pos,
          "estimate":True,"note":"按售价、成本、转化率假设推算，不是真实广告数据，上线后用实际 ACoS 校准"}
    if margin<=0:
        return {**base,"profitable":False,"message":"该售价下不盈利，不建议投广告",
                "reason":f"单件利润 ${profit:.2f}（售价 ${price:.2f} − 成本 ${cost:.2f} − 佣金配送 ${unit_fee:.2f}）≤ 0，任何广告花费都会扩大亏损"}
    be=margin; tgt=min(be*TARGET_RATIO,be)
    max_bid=price*tgt*cvr; start=max_bid*START_RATIO
    return {**base,"profitable":True,"breakeven_acos_pct":_pct(be),"target_acos_pct":_pct(tgt),
            "max_bid":_m(max_bid),"start_bid":_m(start),"daily_clicks":clicks,
            "daily_budget":_m(max_bid*clicks),"daily_orders":round(clicks*cvr,1)}
def apply_to_groups(groups,c):
    """广告组的出价/预算以代码估算为准，避免与模型文字出现两套数字。"""
    n=len(groups) or 1
    for x in groups:
        if c["profitable"]:
            x["suggested_bid"]=f"${c['start_bid']:.2f}–${c['max_bid']:.2f}（估算）"
            x["budget_share"]=f"约 {round(100/n)}%（均分，估算）"
        else:
            x["suggested_bid"]="不建议投放"; x["budget_share"]="不建议投放"
    return groups
