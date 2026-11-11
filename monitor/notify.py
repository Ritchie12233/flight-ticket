"""推送渠道：Telegram / ntfy / Bark / Server酱 / PushPlus / 邮件。
哪个渠道的环境变量（GitHub Secret）设置了，就推哪个。"""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)
env = lambda k, d="": os.environ.get(k, d).strip()  # noqa: E731


def _telegram(title, body, url):
    tok, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return None
    text = f"<b>{title}</b>\n{body}" + (f'\n<a href="{url}">👉 查看/预订</a>' if url else "")
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                      json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True})
    r.raise_for_status()
    return "telegram"


NTFY_TOPIC_CFG = ""  # 由 main.py 从 config.yaml 读入


def _ntfy(title, body, url):
    topic = env("NTFY_TOPIC") or NTFY_TOPIC_CFG
    if not topic:
        return None
    server = env("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title.encode("utf-8"), "Priority": "high", "Tags": "airplane"}
    if url:
        headers["Click"] = url
    r = requests.post(f"{server}/{topic}", data=body.encode("utf-8"), headers=headers, timeout=20)
    r.raise_for_status()
    return "ntfy"


def _bark(title, body, url):
    key = env("BARK_KEY")
    if not key:
        return None
    server = env("BARK_SERVER", "https://api.day.app").rstrip("/")
    r = requests.post(f"{server}/{key}", timeout=20, json={
        "title": title, "body": body, "url": url or None, "group": "bug价机票",
        "level": "timeSensitive", "sound": "minuet"})
    r.raise_for_status()
    return "bark"


def _serverchan(title, body, url):
    key = env("SERVERCHAN_KEY")
    if not key:
        return None
    desp = body.replace("\n", "\n\n") + (f"\n\n[👉 查看/预订]({url})" if url else "")
    r = requests.post(f"https://sctapi.ftqq.com/{key}.send", timeout=20,
                      data={"title": title[:32], "desp": desp})
    r.raise_for_status()
    return "serverchan"


def _pushplus(title, body, url):
    tok = env("PUSHPLUS_TOKEN")
    if not tok:
        return None
    content = body.replace("\n", "<br>") + (f'<br><a href="{url}">👉 查看/预订</a>' if url else "")
    r = requests.post("https://www.pushplus.plus/send", timeout=20,
                      json={"token": tok, "title": title, "content": content, "template": "html"})
    r.raise_for_status()
    return "pushplus"


def _email(title, body, url):
    host, to = env("SMTP_HOST"), env("MAIL_TO")
    if not (host and to):
        return None
    msg = MIMEText(body + (f"\n\n{url}" if url else ""), "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = title, env("SMTP_USER"), to
    port = int(env("SMTP_PORT", "465"))
    cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
    with cls(host, port, timeout=30) as s:
        if port != 465:
            s.starttls()
        s.login(env("SMTP_USER"), env("SMTP_PASS"))
        s.send_message(msg)
    return "email"


CHANNELS = [_telegram, _ntfy, _bark, _serverchan, _pushplus, _email]


def configured() -> list[str]:
    out = ["ntfy"] if (NTFY_TOPIC_CFG and not env("NTFY_TOPIC")) else []
    names = {"_telegram": "TELEGRAM_BOT_TOKEN", "_ntfy": "NTFY_TOPIC", "_bark": "BARK_KEY",
             "_serverchan": "SERVERCHAN_KEY", "_pushplus": "PUSHPLUS_TOKEN", "_email": "SMTP_HOST"}
    return out + [k.strip("_") for k, v in names.items() if env(v)]


def send(title: str, body: str, url: str = "") -> list[str]:
    sent = []
    for ch in CHANNELS:
        try:
            name = ch(title, body, url)
            if name:
                sent.append(name)
        except Exception as e:  # noqa: BLE001
            log.warning("推送失败 %s: %s", ch.__name__, e)
    return sent


# ---------------- 文案 ----------------
ICON = {"bug": "🔥 疑似BUG价", "target": "🎯 到达目标价", "great": "💎 超值", "news": "📰 情报"}


def booking_url(f: dict) -> str:
    """Aviasales 搜索链接：KUL0112LON1 / KUL0112LON15121"""
    def ddmm(s):
        return f"{s[8:10]}{s[5:7]}" if s and len(s) >= 10 else ""
    dep, ret = ddmm(f.get("depart")), ddmm(f.get("return"))
    if not dep:
        return f"https://www.aviasales.com/search?origin_iata={f['origin']}&destination_iata={f['dest']}"
    return f"https://www.aviasales.com/search/{f['origin']}{dep}{f['dest']}{ret}1"


def google_flights_url(f: dict) -> str:
    q = f"Flights from {f['origin']} to {f['dest']} on {f.get('depart') or ''}"
    if f.get("return"):
        q += f" returning {f['return']}"
    if f.get("trip_class") == 1:
        q += " business class"
    return "https://www.google.com/travel/flights?q=" + quote(q)


def trip_url(f: dict) -> str:
    """携程国际版（Trip.com 马来西亚站）搜索链接"""
    q = (f"dcity={f['origin'].lower()}&acity={f['dest'].lower()}&ddate={f.get('depart') or ''}"
         + (f"&rdate={f['return']}&triptype=rt" if f.get("return") else "&triptype=ow")
         + f"&class={'c' if f.get('trip_class') == 1 else 'y'}&quantity=1&locale=en-MY&curr=MYR")
    return "https://my.trip.com/flights/showfarefirst?" + q


def skyscanner_url(f: dict) -> str:
    def ymd(s):
        return s[2:4] + s[5:7] + s[8:10] if s and len(s) >= 10 else ""
    path = f"{f['origin'].lower()}/{f['dest'].lower()}/{ymd(f.get('depart'))}/"
    if f.get("return"):
        path += f"{ymd(f['return'])}/"
    cabin = "business" if f.get("trip_class") == 1 else "economy"
    return f"https://www.skyscanner.com.my/transport/flights/{path}?adultsv2=1&cabinclass={cabin}"


def fare_message(f: dict, cur: str, site: str = "") -> tuple[str, str, str]:
    trip = "单程" if f["one_way"] else "往返"
    cabin = "商务舱" if f["trip_class"] == 1 else "经济舱"
    title = f'{ICON.get(f["level"], "")} 吉隆坡→{f["dest_name_zh"]} {cur.upper()} {f["price"]:.0f}'
    lines = [f'{f["origin"]}→{f["dest"]}（{f["dest_name"]}）· {trip} · {cabin}',
             f'日期：{f.get("depart") or "?"}' + (f' ～ {f["return"]}' if f.get("return") else "")]
    if f.get("baseline"):
        lines.append(f'近期常规价：{f["baseline"]:.0f}（现价为其 {f["ratio"]:.0%}）')
    if f.get("transfers") is not None:
        lines.append("直飞" if f["transfers"] == 0 else f'中转 {f["transfers"]} 次')
    if f.get("airline"):
        lines.append(f'航司：{f["airline"]}')
    if f.get("reasons"):
        lines.append("判定：" + "；".join(f["reasons"]))
    lines.append("⚠️ 缓存价，可能已失效，请尽快核实。bug 价出票后先别订酒店。")
    lines.append(f"携程查价：{trip_url(f)}")
    lines.append(f"Skyscanner 查价：{skyscanner_url(f)}")
    lines.append(f"Google Flights 查价：{google_flights_url(f)}")
    if site:
        lines.append(f"监控站：{site}")
    return title, "\n".join(lines), booking_url(f)


def news_message(n: dict, site: str = "") -> tuple[str, str, str]:
    tag = "🔥 错误票价情报" if n["level"] == "bug" else "📰 吉隆坡特价情报"
    body = (n.get("summary") or "")[:200] + f'\n来源：{n["source"]}'
    if site:
        body += f"\n监控站：{site}"
    return f'{tag}：{n["title"]}'[:120], body, n.get("link", "")
