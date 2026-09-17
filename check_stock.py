#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iPhone 18 Pro Max 512GB 冰川蓝色 — 北京门店到店取货监控
在 GitHub Actions 上运行，每 10 分钟一次。

产出：
  docs/data/status.json   —— 网页面板读的数据
  docs/data/state.json    —— 上次状态（用于判断变化）
  docs/data/feed.json     —— 变化历史

有变化时通过 WxPusher / PushPlus 推送微信通知（webhook 存 repo secrets）。

退出码永远是 0（除非真出错），避免 Actions 因状态字面值判失败。
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))

# ── 监控对象 ──────────────────────────────────────────────
PART_NUMBER = "MJYE4CH/A"
PRODUCT_NAME = "iPhone 18 Pro Max 512GB 冰川蓝色"
PRICE = "¥12,999"
BUY_URL = ("https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro/"
           "6.9%E8%8B%B1%E5%AF%B8%E5%B1%8F%E5%B9%95512gb%E5%86%B0%E5%B7%9D%E8%93%9D%E8%89%B2")

API_URL = ("https://www.apple.com.cn/shop/retail/pickup-message"
           "?parts.0=" + PART_NUMBER + "&searchNearby=true&store=R320")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json",
    "Referer": "https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro",
}

# 北京 6 家 Apple Store
BEIJING_STORES = {
    "R320": {"name": "三里屯",     "address": "北京市朝阳区三里屯路 19 号院\n三里屯太古里南区 7 号楼"},
    "R448": {"name": "王府井",     "address": "北京市东城区王府井大街 138 号北京 apm"},
    "R479": {"name": "华贸购物中心", "address": "北京市朝阳区建国路 81 号华贸购物中心"},
    "R388": {"name": "西单大悦城",  "address": "北京市西城区西单北大街 131 号大悦城"},
    "R645": {"name": "朝阳大悦城",  "address": "北京市朝阳区朝阳北路 101 号"},
    "R792": {"name": "北京荟聚",   "address": "北京市大兴区欣宁街 15 号\n北京荟聚 1 层"},
}

DATA_DIR = os.path.join("docs", "data")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
FEED_FILE = os.path.join(DATA_DIR, "feed.json")

FEED_MAX = 60


def now_iso():
    return datetime.now(CST).replace(microsecond=0).isoformat()


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def fetch():
    """-> (ok, {store_id: status}, err)"""
    req = urllib.request.Request(API_URL, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return False, {}, "{}: {}".format(type(e).__name__, e)

    stores = (data.get("body") or {}).get("stores") or []
    if not stores:
        return False, {}, "响应中无 stores 字段"

    out = {}
    for s in stores:
        sid = s.get("storeNumber")
        if sid not in BEIJING_STORES:
            continue
        pa = (s.get("partsAvailability") or {}).get(PART_NUMBER) or {}
        disp = pa.get("pickupDisplay")
        if disp not in ("available", "unavailable", "ineligible"):
            disp = "unknown"
        out[sid] = disp

    if not out:
        return False, {}, "未匹配到任何北京门店"
    return True, out, None


def send_push(title, body):
    """有 webhook 才推；没有就静默跳过。"""
    pushes = []

    spt = os.environ.get("WXPUSHER_SPT", "").strip()
    if spt:
        pushes.append(("WxPusher", "https://wxpusher.zjiecode.com/api/send/message/simple-push",
                       {"spt": spt, "content": body, "summary": title, "contentType": 3}))

    pp_token = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    if pp_token:
        pushes.append(("PushPlus", "https://www.pushplus.plus/send",
                       {"token": pp_token, "title": title, "content": body, "template": "markdown"}))

    sc_key = os.environ.get("SERVERCHAN_KEY", "").strip()
    if sc_key:
        # Server酱用 form 编码
        import urllib.parse
        pushes.append(("ServerChan",
                       "https://sctapi.ftqq.com/{}.send".format(sc_key),
                       urllib.parse.urlencode({"title": title, "desp": body}).encode()))

    if not pushes:
        print("[push] 未配置任何推送渠道，跳过（仅更新网页）")
        return

    for name, url, payload in pushes:
        try:
            if isinstance(payload, bytes):
                req = urllib.request.Request(url, data=payload, headers={
                    "Content-Type": "application/x-www-form-urlencoded"})
            else:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                resp = r.read().decode("utf-8", "replace")[:200]
            print("[push] {} -> {}".format(name, resp))
        except Exception as e:
            # 推送失败不影响库存记录
            print("[push] {} 失败: {}: {}".format(name, type(e).__name__, e))


def main():
    prev_state = read_json(STATE_FILE, {})
    prev_ok = bool(prev_state.get("ok"))
    prev_stores = prev_state.get("stores") or {}
    feed = read_json(FEED_FILE, [])

    ok, cur_map, err = fetch()
    stamp = now_iso()

    if not ok:
        # 查询失败：保留上一次的有效数据，页面上标注错误
        print("[fetch] 失败: {}".format(err))
        status = read_json(STATUS_FILE, None)
        if status is None:
            status = {
                "updated_at": None,
                "last_error": err,
                "product": {"name": PRODUCT_NAME, "price": PRICE, "buy_url": BUY_URL},
                "stores": [
                    {"id": sid, "name": v["name"], "address": v["address"], "status": "unknown"}
                    for sid, v in BEIJING_STORES.items()
                ],
                "summary": {"available": 0, "total": len(BEIJING_STORES),
                            "headline": "数据读取失败", "level": "unknown", "unknown": True},
            }
        else:
            status["last_error"] = err
        write_json(STATUS_FILE, status)
        write_json(STATE_FILE, {"ok": False, "last_attempt": stamp,
                                "stores": prev_stores, "last_error": err})
        return

    cur_avail = {sid for sid, st in cur_map.items() if st == "available"}
    prev_avail = {sid for sid, st in prev_stores.items() if st == "available"}

    newly_in = cur_avail - prev_avail
    newly_out = prev_avail - cur_avail

    # 记录变化历史
    if newly_in:
        feed.insert(0, {"at": stamp, "type": "in_stock",
                        "stores": [BEIJING_STORES[s]["name"] for s in sorted(newly_in)]})
    if newly_out:
        feed.insert(0, {"at": stamp, "type": "out_of_stock",
                        "stores": [BEIJING_STORES[s]["name"] for s in sorted(newly_out)]})
    feed = feed[:FEED_MAX]

    # 首轮运行不推播（没有基线）
    is_first = not prev_ok

    # 组装网页数据
    stores_out = []
    for sid, meta in BEIJING_STORES.items():
        st = cur_map.get(sid, "unknown")
        stores_out.append({
            "id": sid,
            "name": meta["name"],
            "address": meta["address"],
            "status": st,
            "is_new": sid in newly_in,
            "is_lost": sid in newly_out,
        })

    n_avail = len(cur_avail)
    n_total = len(BEIJING_STORES)
    n_ineligible = sum(1 for v in cur_map.values() if v == "ineligible")

    if n_avail > 0:
        headline = "🎉 {} 家有货".format(n_avail)
        level = "some"
    elif n_ineligible == n_total:
        headline = "暂未开放取货"
        level = "none"
    else:
        headline = "{} 家均无货".format(n_total)
        level = "none"

    status = {
        "updated_at": stamp,
        "last_error": None,
        "product": {"name": PRODUCT_NAME, "price": PRICE, "buy_url": BUY_URL,
                    "part_number": PART_NUMBER},
        "stores": stores_out,
        "summary": {"available": n_avail, "total": n_total,
                    "headline": headline, "level": level,
                    "ineligible": n_ineligible, "unknown": False},
        "changes": feed[:10],
    }
    write_json(STATUS_FILE, status)
    write_json(FEED_FILE, feed)
    write_json(STATE_FILE, {"ok": True, "last_attempt": stamp,
                            "stores": cur_map, "last_error": None})

    print("[fetch] OK — {}/{} 家有货, {} 家暂未开放".format(n_avail, n_total, n_ineligible))

    # ── 推送 ──
    if is_first:
        print("[push] 首次运行，建立基线，不推送")
        return

    if not newly_in and not newly_out:
        print("[push] 无变化，静默")
        return

    lines = []
    if newly_in:
        nm = "、".join(BEIJING_STORES[s]["name"] for s in sorted(newly_in))
        lines.append("🎉 **iPhone 18 Pro Max 512GB 冰川蓝色 到货了！**")
        lines.append("")
        lines.append("📍 可门店取货：{}".format(nm))
        lines.append("💰 售价 {}".format(PRICE))
        if cur_avail:
            allnm = "、".join(BEIJING_STORES[s]["name"] for s in sorted(cur_avail))
            lines.append("（当前共 {}/{} 家有货：{}）".format(n_avail, n_total, allnm))
        lines.append("")
        lines.append("🛒 [立刻下单]({})".format(BUY_URL))

    if newly_out:
        nm = "、".join(BEIJING_STORES[s]["name"] for s in sorted(newly_out))
        if lines:
            lines.append("")
        lines.append("⚠️ 已售罄：{}".format(nm))

    lines.append("")
    lines.append("---")
    lines.append("⏱ {} · [查看监控面板](https://jz-xiong.github.io/iphone-stock-probe/)".format(
        datetime.now(CST).strftime("%m-%d %H:%M")))

    body = "\n".join(lines)
    title = ("iPhone 18PM 到货：{}".format("、".join(BEIJING_STORES[s]["name"] for s in sorted(newly_in)))
             if newly_in else "iPhone 18PM 售罄")
    send_push(title, body)


if __name__ == "__main__":
    main()
