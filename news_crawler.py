"""
경쟁사 최근 뉴스 자동 수집기 (Google News RSS, API 키 불필요).

출력:
    data/news/{competitor_id}.json   — 최근 뉴스 항목 리스트
    data/summaries/{competitor_id}.md — Claude 기반 Farmetry 관점 요약

사용:
    python news_crawler.py              # 전체 경쟁사 업데이트
    python news_crawler.py --id oishii  # 특정 회사만
    python news_crawler.py --skip-claude # 뉴스만 (요약 생략)
"""
import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
from dotenv import load_dotenv

import competitors_service as competitors

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

NEWS_DIR = SCRIPT_DIR / "data" / "news"
SUMMARY_DIR = SCRIPT_DIR / "data" / "summaries"
NEWS_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl_short}"
)


def locale_for(country: str) -> tuple[str, str, str]:
    """country 코드 → (hl, gl, hl_short) for Google News RSS."""
    m = {
        "US": ("en-US", "US", "en"),
        "KR": ("ko", "KR", "ko"),
        "JP": ("ja", "JP", "ja"),
        "DE": ("de", "DE", "de"),
        "NL": ("nl", "NL", "nl"),
        "UK": ("en-GB", "UK", "en"),
        "IT": ("it", "IT", "it"),
        "DK": ("da", "DK", "da"),
        "FI": ("fi", "FI", "fi"),
        "AE": ("en", "AE", "en"),
        "AU": ("en-AU", "AU", "en"),
        "SG": ("en", "SG", "en"),
        "IN": ("en-IN", "IN", "en"),
    }
    return m.get(country, ("en-US", "US", "en"))


def fetch_news(comp: dict, limit: int = 10) -> list[dict]:
    hl, gl, hl_short = locale_for(comp["country"])
    # 회사명 따옴표로 감싸 정확도↑
    query = f'"{comp["name"]}"'
    url = GOOGLE_NEWS_RSS.format(q=quote_plus(query), hl=hl, gl=gl, hl_short=hl_short)
    feed = feedparser.parse(url)

    items = []
    for e in feed.entries[:limit]:
        items.append({
            "title": e.get("title", ""),
            "link": e.get("link", ""),
            "source": e.get("source", {}).get("title", "") if isinstance(e.get("source"), dict) else "",
            "published": e.get("published", ""),
            "summary": re.sub(r"<[^>]+>", "", e.get("summary", ""))[:400],
        })
    return items


def save_news(comp_id: str, items: list[dict]):
    out = NEWS_DIR / f"{comp_id}.json"
    out.write_text(json.dumps({
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_news(comp_id: str) -> dict:
    p = NEWS_DIR / f"{comp_id}.json"
    if not p.exists():
        return {"updated_at": None, "items": []}
    return json.loads(p.read_text(encoding="utf-8"))


def claude_summarize(comp: dict, items: list[dict]) -> str | None:
    if not items:
        return None
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=key)

    headlines = "\n".join(f"- [{it['published'][:16]}] {it['title']}" for it in items[:8])
    prompt = f"""다음은 {comp['name']} ({comp['country']}, {comp.get('crop','')})에 대한 최근 뉴스 헤드라인입니다.

{headlines}

FARMETRY(한국 프리미엄 시소 수직농장, 서울 미쉐린 일식당 B2B 공급 지향)가 이 회사를 어떻게 봐야 할지 작성하세요.

## 요약
(최근 동향 3문장 이내)

## Farmetry 시사점
(벤치마크 포인트 / 위협 / 교훈 중 해당되는 걸 2~3 bullet)

## 위협 등급
(low / medium / high 중 하나 — 직접 시장 경쟁이거나 우리 모델에 영향을 주는 정도)
"""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def save_summary(comp: dict, summary_text: str, items: list[dict]):
    out = SUMMARY_DIR / f"{comp['id']}.md"
    threat = "unknown"
    m = re.search(r"위협 등급[^\w]*(low|medium|high)", summary_text, re.IGNORECASE)
    if m:
        threat = m.group(1).lower()

    fm = f"""---
id: {comp['id']}
name: {comp['name']}
generated_at: {datetime.now().isoformat(timespec='seconds')}
news_count: {len(items)}
threat: {threat}
---

"""
    out.write_text(fm + summary_text, encoding="utf-8")


def load_summary(comp_id: str) -> dict | None:
    p = SUMMARY_DIR / f"{comp_id}.md"
    if not p.exists():
        return None
    txt = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", txt, re.DOTALL)
    if not m:
        return {"frontmatter": {}, "body": txt}
    fm_raw = m.group(1)
    body = m.group(2)
    fm = {}
    for line in fm_raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return {"frontmatter": fm, "body": body}


def update_one(comp: dict, skip_claude: bool = False):
    print(f"[{comp['id']}] {comp['name']} ...", end=" ", flush=True)
    try:
        items = fetch_news(comp)
        save_news(comp["id"], items)
        print(f"{len(items)} items", end="")
        if items and not skip_claude:
            summary = claude_summarize(comp, items)
            if summary:
                save_summary(comp, summary, items)
                print(" + summary", end="")
        print()
    except Exception as e:
        print(f"ERROR: {e}")


def update_all(skip_claude: bool = False, delay: float = 1.0):
    data = competitors.load()
    for comp in data["competitors"]:
        update_one(comp, skip_claude=skip_claude)
        time.sleep(delay)  # rate-limit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", help="특정 경쟁사 ID 만 업데이트")
    ap.add_argument("--skip-claude", action="store_true", help="뉴스만, Claude 요약 생략")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    if args.id:
        comp = competitors.by_id(args.id)
        if not comp:
            print(f"[ERROR] no competitor with id={args.id}")
            return
        update_one(comp, skip_claude=args.skip_claude)
    else:
        update_all(skip_claude=args.skip_claude, delay=args.delay)


if __name__ == "__main__":
    main()
