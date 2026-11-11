"""异常低价判定：历史中位数对比 + 每公里单价 + 目标价。"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

from .travelpayouts import haversine_km

LEVEL_RANK = {"bug": 3, "target": 2, "great": 1, "normal": 0}


def route_key(f: dict) -> str:
    trip = "OW" if f["one_way"] else "RT"
    return f'{f["origin"]}-{f["dest"]}|{trip}|{f["trip_class"]}'


def update_history(history: dict, fares: list[dict], today: str, keep_days: int):
    """每条航线每天只记一个最低价。"""
    for f in fares:
        if f["price"] <= 0:
            continue
        h = history.setdefault(route_key(f), {})
        h[today] = min(h.get(today, f["price"]), f["price"])
    cutoff = (date.fromisoformat(today) - timedelta(days=keep_days)).isoformat()
    for k in list(history):
        history[k] = {d: p for d, p in history[k].items() if d >= cutoff}
        if not history[k]:
            del history[k]


def baseline(history: dict, key: str, today: str, min_days: int):
    days = {d: p for d, p in history.get(key, {}).items() if d != today}
    if len(days) < min_days:
        return None
    return statistics.median(days.values())


def evaluate(fares: list[dict], history: dict, cities: dict, cfg: dict, today: str) -> list[dict]:
    dc = cfg["detection"]
    targets = {k.upper(): v for k, v in (dc.get("targets") or {}).items()}
    best: dict[str, dict] = {}

    for f in fares:
        if f["price"] <= 0 or not f.get("dest"):
            continue
        key = route_key(f)
        # 同一航线只保留最便宜那张
        if key in best and best[key]["price"] <= f["price"]:
            # 把航司信息补上
            if not best[key].get("airline") and f.get("airline") and best[key]["price"] == f["price"]:
                best[key]["airline"] = f["airline"]
            continue
        best[key] = dict(f)

    results = []
    for key, f in best.items():
        o, d = cities.get(f["origin"], {}), cities.get(f["dest"], {})
        dist = f.get("distance") or haversine_km(o, d)
        flown = (dist or 0) * (1 if f["one_way"] else 2)
        per_km = f["price"] / flown if flown else None
        base = baseline(history, key, today, dc.get("min_history_days", 5))
        ratio = f["price"] / base if base else None

        reasons, level = [], "normal"
        biz = f["trip_class"] >= 1
        bug_km = dc["business_bug_per_km"] if biz else dc["economy_bug_per_km"]
        great_km = dc["business_great_per_km"] if biz else dc["economy_great_per_km"]

        def bump(lv, why):
            nonlocal level
            reasons.append(why)
            if LEVEL_RANK[lv] > LEVEL_RANK[level]:
                level = lv

        if ratio is not None:
            if ratio <= dc["bug_ratio"]:
                bump("bug", f"仅为近期常规价的 {ratio:.0%}")
            elif ratio <= dc["great_ratio"]:
                bump("great", f"比近期常规价低 {1 - ratio:.0%}")
        if per_km is not None and dist and dist >= dc.get("min_distance_km", 1800):
            if per_km <= bug_km:
                bump("bug", f"每公里仅 {per_km:.3f}，远低于正常水平")
            elif per_km <= great_km:
                bump("great", f"每公里 {per_km:.3f}，很划算")
        tgt = targets.get(f["dest"])
        if tgt and not f["one_way"] and not biz and f["price"] <= tgt:
            bump("target", f"低于你设的目标价 {tgt}")

        city = cities.get(f["dest"], {})
        results.append({
            **f,
            "id": key,
            "type": "fare",
            "level": level,
            "reasons": reasons,
            "baseline": round(base, 0) if base else None,
            "ratio": round(ratio, 3) if ratio else None,
            "per_km": round(per_km, 4) if per_km else None,
            "distance": round(dist) if dist else None,
            "dest_name": city.get("name", f["dest"]),
            "dest_name_zh": city.get("name_zh", f["dest"]),
            "country": city.get("country"),
        })
    results.sort(key=lambda r: (-LEVEL_RANK[r["level"]], r["ratio"] or 9, r["per_km"] or 9))
    return results
