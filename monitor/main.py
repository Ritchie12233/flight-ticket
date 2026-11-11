"""入口：python -m monitor.main [--demo] [--test-push] [--no-push]"""
from __future__ import annotations

import argparse
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import detect, notify, rss, travelpayouts

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
CACHE = ROOT / "data" / "cache"
SITE_DATA = ROOT / "docs" / "data" / "deals.json"
MYT = timezone(timedelta(hours=8))
log = logging.getLogger("monitor")


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save_json(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def should_alert(item_id: str, price: float | None, alerted: dict, cfg: dict, now: datetime) -> bool:
    prev = alerted.get(item_id)
    if not prev:
        return True
    if price is None:  # 新闻只推一次
        return False
    age_h = (now - datetime.fromisoformat(prev["at"])).total_seconds() / 3600
    if age_h >= cfg["detection"].get("realert_hours", 24):
        return True
    return price <= prev["price"] * (1 - cfg["detection"].get("realert_drop", 0.1))


# ---------------- 演示数据（不需要任何 token） ----------------
DEMO_CITIES = {
    "KUL": ("Kuala Lumpur", "吉隆坡", "MY", 3.14, 101.69), "LON": ("London", "伦敦", "GB", 51.5, -0.12),
    "TYO": ("Tokyo", "东京", "JP", 35.68, 139.69), "SYD": ("Sydney", "悉尼", "AU", -33.87, 151.2),
    "PAR": ("Paris", "巴黎", "FR", 48.85, 2.35), "SEL": ("Seoul", "首尔", "KR", 37.56, 126.98),
    "BKK": ("Bangkok", "曼谷", "TH", 13.75, 100.5), "CTU": ("Chengdu", "成都", "CN", 30.66, 104.06),
    "YVR": ("Vancouver", "温哥华", "CA", 49.28, -123.12), "IST": ("Istanbul", "伊斯坦布尔", "TR", 41.0, 28.97),
    "DXB": ("Dubai", "迪拜", "AE", 25.2, 55.27), "AKL": ("Auckland", "奥克兰", "NZ", -36.85, 174.76),
    "OSA": ("Osaka", "大阪", "JP", 34.69, 135.5), "MLE": ("Male", "马累", "MV", 4.17, 73.51),
}
DEMO_NORMAL = {"LON": 3200, "TYO": 1500, "SYD": 1700, "PAR": 3300, "SEL": 1100, "BKK": 320,
               "CTU": 900, "YVR": 4200, "IST": 2600, "DXB": 1900, "AKL": 2600, "OSA": 1350, "MLE": 1100}


def demo_data(today: str):
    cities = {k: {"name": a, "name_zh": b, "country": c, "lat": la, "lon": lo}
              for k, (a, b, c, la, lo) in DEMO_CITIES.items()}
    rnd = random.Random(42)
    history = {}
    t = datetime.fromisoformat(today)
    for dest, p in DEMO_NORMAL.items():
        for tc, mul in ((0, 1), (1, 3.4)):
            key = f"KUL-{dest}|RT|{tc}"
            history[key] = {(t - timedelta(days=i)).strftime("%Y-%m-%d"): round(p * mul * rnd.uniform(.9, 1.15))
                            for i in range(1, 30)}
    special = {("LON", 0): 1180, ("YVR", 1): 4900, ("TYO", 0): 840, ("MLE", 0): 690, ("SEL", 0): 760}
    fares = []
    for dest, p in DEMO_NORMAL.items():
        for tc, mul in ((0, 1), (1, 3.4)):
            price = special.get((dest, tc)) or round(p * mul * rnd.uniform(.92, 1.1))
            dep = t + timedelta(days=rnd.randint(20, 150))
            fares.append({"origin": "KUL", "dest": dest, "price": float(price),
                          "depart": dep.strftime("%Y-%m-%d"),
                          "return": (dep + timedelta(days=rnd.randint(5, 12))).strftime("%Y-%m-%d"),
                          "one_way": False, "trip_class": tc, "transfers": rnd.choice([0, 1, 1]),
                          "distance": None, "airline": rnd.choice(["MH", "TK", "QR", "EK", "SQ", "OD", "D7"]),
                          "found_at": datetime.now(timezone.utc).isoformat(), "source": "demo"})
    news = [{"id": "rss:demo1", "type": "news", "level": "bug", "is_error_fare": True,
             "title": "ERROR FARE: Kuala Lumpur, Malaysia to Male, Maldives for only $148 USD roundtrip",
             "summary": "Malaysia Airlines 往返马尔代夫，疑似燃油附加费漏算。", "link": "https://www.secretflying.com/",
             "source": "演示数据", "published": datetime.now(timezone.utc).isoformat()},
            {"id": "rss:demo2", "type": "news", "level": "news", "is_error_fare": False,
             "title": "Non-stop from Kuala Lumpur, Malaysia to Perth, Australia for only $178 USD roundtrip",
             "summary": "非错误票价，但属于明显低价。", "link": "https://www.secretflying.com/",
             "source": "演示数据", "published": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()}]
    return cities, history, fares, news


# ---------------- 主流程 ----------------

def run(args):
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text("utf-8"))
    cur = cfg.get("currency", "myr")
    site = cfg.get("notify", {}).get("site_url", "")
    notify.NTFY_TOPIC_CFG = str(cfg.get("notify", {}).get("ntfy_topic") or "")
    first_run = not STATE.exists()
    now = datetime.now(MYT)
    today = now.strftime("%Y-%m-%d")
    state = load_json(STATE, {"history": {}, "alerted": {}, "news": [], "alerts_log": []})
    sources = []

    if args.test_push:
        sent = notify.send("✈️ bug价机票监控 · 测试推送", f"推送渠道工作正常。\n时间：{now:%Y-%m-%d %H:%M} (MYT)", site)
        print("已推送到：", sent or "（没有配置任何渠道）")
        return

    if args.demo:
        cities, history, fares, news = demo_data(today)
        state = {"history": history, "alerted": {}, "news": [], "alerts_log": []}
        sources.append({"name": "演示数据", "ok": True, "count": len(fares)})
    else:
        cities = travelpayouts.load_cities(CACHE)
        airlines = travelpayouts.load_airlines(CACHE)
        fares = travelpayouts.collect(cfg, CACHE)
        for f in fares:
            if f.get("airline"):
                f["airline"] = f'{airlines.get(f["airline"], "")} ({f["airline"]})'.strip()
        sources.append({"name": "Aviasales 实时低价", "ok": bool(fares), "count": len(fares)})
        news = rss.collect(cfg)
        sources += rss.status

    results = detect.evaluate(fares, state["history"], cities, cfg, today)
    detect.update_history(state["history"], fares, today, cfg["detection"].get("history_days", 60))

    # ---------- 推送 ----------
    push_levels = set(cfg.get("notify", {}).get("push_levels", ["bug", "target"]))
    budget = cfg.get("notify", {}).get("max_per_run", 8)
    to_push = []
    for f in results:
        if f["level"] in push_levels and should_alert(f["id"], f["price"], state["alerted"], cfg, now):
            to_push.append(("fare", f))
    known_news = {n["id"] for n in state["news"]}
    fresh_news = [n for n in news if n["id"] not in known_news]
    for n in fresh_news:
        lvl = "bug" if n["level"] == "bug" else "news"
        if lvl in push_levels and should_alert(n["id"], None, state["alerted"], cfg, now):
            to_push.append(("news", n))

    pushed = []
    for kind, item in to_push[:budget]:
        title, body, url = (notify.fare_message(item, cur, site) if kind == "fare"
                            else notify.news_message(item, site))
        channels = [] if (args.no_push or args.demo) else notify.send(title, body, url)
        state["alerted"][item["id"]] = {"price": item.get("price") if kind == "fare" else None,
                                        "at": now.isoformat()}
        pushed.append({"at": now.isoformat(), "title": title, "url": url, "channels": channels})
        log.info("推送 %s → %s", title, channels or "(未发送)")
    # 清理 30 天前的推送记录
    cutoff = now - timedelta(days=30)
    state["alerted"] = {k: v for k, v in state["alerted"].items()
                        if datetime.fromisoformat(v["at"]) > cutoff}
    state["alerts_log"] = (pushed + state.get("alerts_log", []))[:200]
    state["news"] = sorted(fresh_news + state["news"], key=lambda n: n["published"], reverse=True)[:150]

    # ---------- 网站数据 ----------
    hot = [r for r in results if r["level"] != "normal"]
    cheapest_by_dest = {}
    for r in sorted(results, key=lambda r: r["price"]):
        if r["trip_class"] == 0 and not r["one_way"]:
            cheapest_by_dest.setdefault(r["dest"], r)
    trend = {}
    for r in hot[:80]:
        h = state["history"].get(r["id"], {})
        trend[r["id"]] = [[d, p] for d, p in sorted(h.items())]
    site_data = {
        "updated_at": now.isoformat(),
        "origin": cfg["origin"], "currency": cur.upper(),
        "stats": {"fares_scanned": len(fares), "routes": len(results),
                  "bug": sum(r["level"] == "bug" for r in results),
                  "great": sum(r["level"] == "great" for r in results),
                  "target": sum(r["level"] == "target" for r in results)},
        "channels": notify.configured(),
        "sources": sources,
        "hot": hot[:120],
        "all_routes": sorted(cheapest_by_dest.values(), key=lambda r: r["price"])[:300],
        "trend": trend,
        "news": state["news"][:80],
        "alerts": state["alerts_log"][:50],
        "targets": cfg["detection"].get("targets", {}),
        "rules": {k: cfg["detection"].get(k) for k in (
            "bug_ratio", "great_ratio", "min_history_days", "min_distance_km",
            "economy_bug_per_km", "economy_great_per_km", "business_bug_per_km", "business_great_per_km")},
        "history_days": len({d for h in state["history"].values() for d in h}),
        "demo": bool(args.demo),
    }
    save_json(SITE_DATA, site_data)
    if not args.demo:
        save_json(STATE, state)
        if first_run and not args.no_push:
            notify.send("✈️ bug价机票监控已启动",
                        f"KUL 出发全球监控已开始运行，每 15 分钟扫描一次。\n"
                        f"本轮扫描 {len(fares)} 条票价，发现异常 {len(hot)} 条。", site)
    print(f"完成：扫描 {len(fares)} 条票价 / {len(results)} 条航线，"
          f"异常 {len(hot)} 条，推送 {len(pushed)} 条，情报新增 {len(fresh_news)} 条")


def cli():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="用模拟数据生成网页（不推送、不改状态）")
    ap.add_argument("--test-push", action="store_true", help="发一条测试推送")
    ap.add_argument("--no-push", action="store_true", help="只更新数据不推送")
    run(ap.parse_args())


if __name__ == "__main__":
    cli()
