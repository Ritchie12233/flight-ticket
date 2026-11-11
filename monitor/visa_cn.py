"""中国普通护照入境政策（整理于 2026-11-11）。

来源：外交部《中外互免签证协定一览表》（更新至 2026-05-29）及多家签证机构 2026 年汇总
（世和签证 2026-08、寰球签证 2026-01、5iucn 2026-11）。政策变化很快，出行前以目的地官方为准。

分档：
  free          免签（含互免、单方面免签）
  free_partial  仅部分地区免签（如济州岛、富国岛）
  easy          落地签 / 电子签 / ETA，抢到票后通常几天内能办好
  conditional   持有效美/加/英/申根/日/澳等签证可免签（取决于 config 里的 held_visas）
  visa          需提前办签证
"""

FREE = {
    # 互免签证协定（普通护照）
    "AL": "免签 90 天", "AG": "免签", "AM": "免签 90 天", "AZ": "免签 30 天", "BS": "免签", "BB": "免签",
    "BY": "免签 30 天", "BA": "免签", "DM": "免签", "EC": "免签 90 天", "FJ": "免签", "GD": "免签",
    "KZ": "免签 30 天", "MV": "免签 30 天（行前 96 小时填 IMUGA）", "MU": "免签 90 天", "QA": "免签 30 天",
    "SM": "免签（需经意大利入境）", "RS": "免签 30 天", "SC": "免签 30 天", "SR": "免签 30 天",
    "TH": "免签 60 天", "TO": "免签", "AE": "免签 30 天", "UZ": "免签 30 天", "SG": "免签 30 天",
    "MY": "免签 30 天", "WS": "免签", "SB": "免签",
    # 单方面免签
    "GE": "免签 90 天", "TR": "免签（180 天内累计 90 天，2026-01 起）", "OM": "免签 14 天",
    "IR": "免签 21 天", "BN": "免签 14 天", "MA": "免签 90 天", "MZ": "免签", "TN": "免签 90 天",
    "ZM": "免签", "AO": "免签", "BJ": "免签", "HT": "免签", "KN": "免签（需 ETA）", "LC": "免签",
    "JM": "免签", "CU": "免签 90 天", "FM": "免签", "NU": "免签", "KI": "免签", "CK": "免签",
    "TC": "免签", "VG": "免签",
    "RU": "免签 30 天（据报道延至 2027 年底）",
    "BR": "免签 30 天（2026-05 起，试行至 2026 年底）",
    "PH": "免签 14 天（试行，限指定机场入境）",
}
FREE_PARTIAL = {
    "KR": "仅济州岛免签 30 天，其他地区需签证",
    "VN": "仅富国岛免签 30 天，其他地区需电子签",
}
EASY = {
    "ID": "落地签 30 天", "LA": "落地签 30 天", "KH": "落地签 30 天", "NP": "落地签", "BD": "落地签",
    "JO": "落地签", "EG": "落地签", "LB": "落地签", "BH": "落地签 / 电子签", "SA": "落地签 / 电子签",
    "TL": "落地签", "TM": "落地签（需邀请函）", "MM": "电子签", "LK": "免费 ETA（2026-05 起）",
    "TZ": "落地签 / 电子签", "MG": "落地签", "CV": "落地签", "ZW": "落地签", "RW": "落地签",
    "KM": "落地签", "ST": "落地签", "BW": "落地签", "BI": "落地签", "KE": "电子旅行授权 eTA",
    "UY": "已宣布免签，生效细节待官方公布",
}
CONDITIONAL = {
    "MX": "持有效美/加/日/英/申根签证可免签", "CL": "持有效美/加签证可免签",
    "PE": "持有效美/加/英/澳/申根签证可免签", "AR": "持有效美/申根签证可申请电子签",
    "PA": "持有效美/加/英/澳签证可免签", "CR": "持有效美/加/申根签证可免签",
}
# 目的国本身的签证（持有即视为可去）
VISA_COUNTRIES = {
    "US": ["US"], "CA": ["CA"], "GB": ["GB"], "JP": ["JP"], "AU": ["AU"], "NZ": ["NZ"], "KR": ["KR"],
    "SCHENGEN": ["AT", "BE", "BG", "HR", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IS", "IT", "LV",
                 "LI", "LT", "LU", "MT", "NL", "NO", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "CH"],
}

LABEL = {"free": "免签", "free_partial": "部分免签", "easy": "落地签/电子签", "conditional": "有条件免签", "visa": "需签证"}
EASY_LEVELS = {"free", "free_partial", "easy"}


def info(country: str | None, held_visas: list[str] | None = None) -> dict:
    held = {h.upper() for h in (held_visas or [])}
    c = (country or "").upper()
    if c == "CN":
        return {"status": "free", "label": "国内", "note": "回国，不需要签证"}
    if c in ("HK", "MO"):
        return {"status": "easy", "label": "通行证", "note": "凭港澳通行证及有效签注入境"}
    if c in FREE:
        return {"status": "free", "label": "免签", "note": FREE[c]}
    for h in held:
        if c in VISA_COUNTRIES.get(h, []):
            return {"status": "free", "label": "已有签证", "note": f"你持有 {h} 签证"}
    if c in FREE_PARTIAL:
        return {"status": "free_partial", "label": LABEL["free_partial"], "note": FREE_PARTIAL[c]}
    if c in EASY:
        return {"status": "easy", "label": LABEL["easy"], "note": EASY[c]}
    if c in CONDITIONAL:
        ok = held & {"US", "CA", "GB", "JP", "AU", "SCHENGEN"}
        if ok:
            return {"status": "free", "label": "免签（凭你的签证）", "note": CONDITIONAL[c]}
        return {"status": "conditional", "label": LABEL["conditional"], "note": CONDITIONAL[c]}
    return {"status": "visa", "label": "需签证", "note": "需提前办签证，抢到特价票也可能来不及"}


def quick(status: str) -> bool:
    """不用提前办签证就能成行"""
    return status in EASY_LEVELS
