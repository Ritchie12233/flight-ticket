"""错误票价情报 RSS：Secret Flying / Google 新闻 / Fly4free 等。"""
from __future__ import annotations

import hashlib
import html
import logging
import re
from datetime import datetime, timezone

import feedparser
import requests

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (compatible; kul-fare-watch/1.0; +https://github.com)"}
TAG = re.compile(r"<[^>]+>")
status: list[dict] = []  # 每个 feed 的抓取结果，供网页显示


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", s or ""))).strip()


def _has(text: str, words: list[str]) -> bool:
    t = text.lower()
    for w in words:
        wl = w.lower()
        # 3 个字母以内的代码（KUL）要整词匹配，避免误伤
        if len(wl) <= 3 and wl.isascii():
            if re.search(rf"\b{re.escape(wl)}\b", t):
                return True
        elif wl in t:
            return True
    return False


def collect(cfg: dict) -> list[dict]:
    rc = cfg.get("rss", {})
    if not rc.get("enabled", True):
        return []
    items = []
    status.clear()
    for feed in rc.get("feeds", []):
        try:
            r = requests.get(feed["url"], headers=UA, timeout=25)
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
        except Exception as e:  # noqa: BLE001
            log.warning("RSS 失败 [%s]: %s", feed["name"], e)
            status.append({"name": feed["name"], "ok": False, "count": 0})
            continue
        status.append({"name": feed["name"], "ok": True, "count": len(parsed.entries)})
        for e in parsed.entries[:40]:
            title = _clean(e.get("title", ""))
            summary = _clean(e.get("summary", ""))[:400]
            text = f"{title} {summary}"
            from_kl = _has(text, rc.get("origin_keywords", []))
            is_err = _has(text, rc.get("error_keywords", []))
            if is_err and from_kl:
                level = "bug"
            elif from_kl:
                level = "news"
            elif is_err and rc.get("push_global_errors"):
                level = "bug"
            elif is_err:
                level = "global"
            else:
                continue
            ts = e.get("published_parsed") or e.get("updated_parsed")
            published = (datetime(*ts[:6], tzinfo=timezone.utc).isoformat()
                         if ts else datetime.now(timezone.utc).isoformat())
            link = e.get("link", "")
            items.append({
                "id": "rss:" + hashlib.sha1((link or title).encode()).hexdigest()[:16],
                "type": "news",
                "level": level,
                "title": title,
                "summary": summary,
                "link": link,
                "source": feed["name"],
                "published": published,
                "is_error_fare": is_err,
            })
    log.info("RSS 共匹配 %d 条", len(items))
    return items
