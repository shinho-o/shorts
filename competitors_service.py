"""
경쟁사 데이터 서비스 — competitors.json 로드 + 집계 유틸.

확장 계획:
- fetch_news(competitor_id)  — 뉴스 크롤링 (RSS/Bing News API)
- summarize(competitor_id)   — Claude API 요약
- update_daily()             — 일일 자동 업데이트 (크론)
"""
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parent / "data"
DATA_PATH = BASE / "competitors.json"
NEWS_DIR = BASE / "news"
SUMMARY_DIR = BASE / "summaries"

# 상태 라벨 한국어 매핑
STATUS_LABEL = {
    "growth": "성장",
    "stable": "안정",
    "profitable": "흑자",
    "pivot": "피벗",
    "restructured": "구조조정",
    "administration": "법정관리",
    "for_sale": "매각",
    "defunct": "폐업",
}

CATEGORY_LABEL = {
    "premium": "프리미엄",
    "leafy": "잎채",
    "microgreen": "마이크로그린",
    "greenhouse": "그린하우스",
    "tech_provider": "기술 공급",
}

RISK_STATUSES = {"pivot", "restructured", "administration", "for_sale", "defunct"}


def load() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def summary() -> dict:
    """대시보드 상단 지표."""
    data = load()
    comps = data["competitors"]

    by_country = Counter(c["country"] for c in comps)
    by_status = Counter(c["status"] for c in comps)
    by_category = Counter(c["category"] for c in comps)

    fundings = [c["funding_usd_m"] for c in comps if c.get("funding_usd_m")]

    return {
        "total": len(comps),
        "countries": by_country.most_common(),
        "status": by_status.most_common(),
        "category": by_category.most_common(),
        "funding_total_m": sum(fundings),
        "funding_max_m": max(fundings) if fundings else 0,
        "at_risk": sum(1 for c in comps if c["status"] in RISK_STATUSES),
        "updated": data.get("generated_at"),
    }


def by_id(cid: str) -> dict | None:
    for c in load()["competitors"]:
        if c["id"] == cid:
            return c
    return None


def filtered(country: str | None = None,
             status: str | None = None,
             category: str | None = None) -> list[dict]:
    rows = load()["competitors"]
    if country:
        rows = [r for r in rows if r["country"] == country]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if category:
        rows = [r for r in rows if r["category"] == category]
    return rows


def get_news(cid: str) -> dict:
    p = NEWS_DIR / f"{cid}.json"
    if not p.exists():
        return {"updated_at": None, "items": []}
    return json.loads(p.read_text(encoding="utf-8"))


def get_summary(cid: str) -> dict | None:
    """프론트매터 + 본문 분리해 반환."""
    p = SUMMARY_DIR / f"{cid}.md"
    if not p.exists():
        return None
    import re as _re
    txt = p.read_text(encoding="utf-8")
    m = _re.match(r"^---\n(.*?)\n---\n(.*)$", txt, _re.DOTALL)
    if not m:
        return {"frontmatter": {}, "body": txt}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return {"frontmatter": fm, "body": m.group(2)}


if __name__ == "__main__":
    # CLI: 요약 출력
    import pprint
    pprint.pprint(summary())
