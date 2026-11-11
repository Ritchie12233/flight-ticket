"""Travelpayouts / Aviasales Data API 抓取。

数据来自 Aviasales 用户最近 2-7 天的真实搜索缓存，覆盖面广、免费，
适合发现"某条航线突然出现离谱低价"。
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)
API = "https://api.travelpayouts.com"
UA = {"User-Agent": "kul-fare-watch/1.0"}


def _get(path: str, token: str, **params):
    r = requests.get(f"{API}{path}", params=params,
                     headers={"X-Access-Token": token, **UA}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_latest(token: str, origin: str, currency: str, trip_class: int,
                 one_way: bool, limit: int) -> list[dict]:
    """v2/prices/latest：从 origin 出发到任意目的地，按价格排序。"""
    # v2 只支持经济舱；商务舱用 v3/get_latest_prices
    path = "/v2/prices/latest" if trip_class == 0 else "/aviasales/v3/get_latest_prices"
    js = _get(path, token, currency=currency, origin=origin,
              period_type="year", one_way=str(one_way).lower(), page=1,
              limit=limit, sorting="price", trip_class=trip_class,
              show_to_affiliates="true")
    out = []
    for d in js.get("data") or []:
        out.append({
            "origin": d.get("origin", origin),
            "dest": d.get("destination"),
            "price": float(d.get("value") or 0),
            "depart": (d.get("depart_date") or "")[:10] or None,
            "return": None if one_way else ((d.get("return_date") or "")[:10] or None),
            "one_way": one_way,
            "trip_class": trip_class,
            "transfers": d.get("number_of_changes"),
            "distance": d.get("distance"),
            "airline": None,
            "gate": d.get("gate"),
            "found_at": d.get("found_at"),
            "source": "aviasales-latest",
        })
    return out


def fetch_cheap(token: str, origin: str, currency: str) -> list[dict]:
    """v1/prices/cheap：每个目的地最便宜的几张票（带航司、航班号）。"""
    js = _get("/v1/prices/cheap", token, origin=origin, destination="-",
              currency=currency)
    out = []
    for dest, opts in (js.get("data") or {}).items():
        for _k, d in (opts or {}).items():
            out.append({
                "origin": origin,
                "dest": dest,
                "price": float(d.get("price") or 0),
                "depart": (d.get("departure_at") or "")[:10] or None,
                "return": (d.get("return_at") or "")[:10] or None,
                "one_way": not d.get("return_at"),
                "trip_class": 0,
                "transfers": None,
                "distance": None,
                "airline": d.get("airline"),
                "flight_number": d.get("flight_number"),
                "found_at": None,
                "source": "aviasales-cheap",
            })
    return out


# ---------------- 城市 / 航司字典（缓存一周） ----------------

def _cached_json(url: str, path: Path, max_age_days: int = 7):
    if path.exists() and time.time() - path.stat().st_mtime < max_age_days * 86400:
        return json.loads(path.read_text("utf-8"))
    try:
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        data = r.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        return data
    except Exception as e:  # noqa: BLE001
        log.warning("下载字典失败 %s: %s", url, e)
        if path.exists():
            return json.loads(path.read_text("utf-8"))
        return []


def load_cities(cache_dir: Path) -> dict[str, dict]:
    en = _cached_json(f"{API}/data/en/cities.json", cache_dir / "cities_en.json")
    zh = _cached_json(f"{API}/data/zh-CN/cities.json", cache_dir / "cities_zh.json")
    zh_names = {c.get("code"): c.get("name") for c in zh if isinstance(c, dict)}
    cities = {}
    for c in en:
        if not isinstance(c, dict) or not c.get("code"):
            continue
        co = c.get("coordinates") or {}
        cities[c["code"]] = {
            "name": c.get("name") or c["code"],
            "name_zh": zh_names.get(c["code"]) or c.get("name") or c["code"],
            "country": c.get("country_code"),
            "lat": co.get("lat"),
            "lon": co.get("lon"),
        }
    return cities


def load_airlines(cache_dir: Path) -> dict[str, str]:
    data = _cached_json(f"{API}/data/en/airlines.json", cache_dir / "airlines.json")
    return {a["code"]: a.get("name") or a["code"] for a in data
            if isinstance(a, dict) and a.get("code")}


def haversine_km(a: dict, b: dict) -> float | None:
    try:
        lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    except (TypeError, KeyError):
        return None
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def collect(cfg: dict, cache_dir: Path) -> list[dict]:
    token = os.environ.get("TRAVELPAYOUTS_TOKEN", "").strip()
    tp = cfg.get("travelpayouts", {})
    if not tp.get("enabled", True):
        return []
    if not token:
        log.warning("未设置 TRAVELPAYOUTS_TOKEN，跳过实时价格数据源")
        return []
    origins = [cfg["origin"], *cfg.get("extra_origins", [])]
    cur = cfg.get("currency", "myr")
    fares: list[dict] = []
    for o in origins:
        for tc in tp.get("trip_classes", [0]):
            for ow in ([False, True] if tp.get("include_one_way", True) else [False]):
                try:
                    fares += fetch_latest(token, o, cur, tc, ow, tp.get("max_results", 1000))
                except Exception as e:  # noqa: BLE001
                    log.warning("latest %s class=%s oneway=%s 失败: %s", o, tc, ow, e)
        try:
            fares += fetch_cheap(token, o, cur)
        except Exception as e:  # noqa: BLE001
            log.warning("cheap %s 失败: %s", o, e)
    log.info("Travelpayouts 共获取 %d 条票价", len(fares))
    return fares
