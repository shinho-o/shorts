"""
Farmetry Meme Agent
매일 자동으로 트렌드 수집 → Claude 분석 → 콘텐츠 아이디어 제안
소스: Google Trends + YouTube Shorts
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import os
import json
import anthropic
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from pytrends.request import TrendReq
from googleapiclient.discovery import build

# .env 파일 로드 (스크립트 위치 기준)
SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

# ─────────────────────────────────────────
# CONFIG (.env 파일에서 로드)
# ─────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")
KAKAO_TOKEN = os.getenv("KAKAO_TOKEN", "")

# Obsidian vault 경로
OBSIDIAN_VAULT = Path(os.getenv("OBSIDIAN_VAULT", r"C:\obsidian\My first remote vault"))


# ─────────────────────────────────────────
# STEP 1-A: Google Trends 수집
# ─────────────────────────────────────────
def fetch_google_trends():
    """
    Farmetry 관련 키워드의 Google Trends 데이터 수집
    """
    pytrends = TrendReq(hl="en-US", tz=360)

    keyword_groups = [
        ["kale chips", "kale recipe", "superfood", "healthy snacks", "meal prep"],
        ["smart farm", "hydroponics", "vertical farming", "IoT agriculture", "indoor garden"],
        ["looksmaxxing", "glow up", "health routine", "clean eating", "gym meme"],
    ]

    trends_data = []

    for keywords in keyword_groups:
        try:
            pytrends.build_payload(keywords, cat=0, timeframe="now 7-d", geo="US")

            # 관심도 데이터
            interest = pytrends.interest_over_time()
            if not interest.empty:
                for kw in keywords:
                    if kw in interest.columns:
                        avg_interest = int(interest[kw].mean())
                        peak_interest = int(interest[kw].max())
                        trends_data.append({
                            "source": "google_trends",
                            "keyword": kw,
                            "avg_interest": avg_interest,
                            "peak_interest": peak_interest,
                        })

            # 연관 검색어
            related = pytrends.related_queries()
            for kw in keywords:
                if kw in related and related[kw]["rising"] is not None:
                    top_rising = related[kw]["rising"].head(3)
                    for _, row in top_rising.iterrows():
                        trends_data.append({
                            "source": "google_trends_rising",
                            "keyword": kw,
                            "rising_query": row["query"],
                            "rise_value": str(row["value"]),
                        })
        except Exception as e:
            print(f"[WARN] Google Trends 수집 실패 ({keywords[0]}...): {e}")

    # 관심도 내림차순 정렬
    trends_data.sort(key=lambda x: x.get("peak_interest", 0), reverse=True)
    print(f"[✓] Google Trends 수집 완료: {len(trends_data)}개 항목")
    return trends_data


# ─────────────────────────────────────────
# STEP 1-B: YouTube Shorts 트렌드 수집
# ─────────────────────────────────────────
def fetch_youtube_shorts():
    """
    YouTube에서 관련 Shorts/영상 트렌드 수집
    """
    if not YOUTUBE_API_KEY:
        print("[SKIP] YouTube API 키 없음 — 건너뜀")
        return []

    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    search_queries = [
        "kale chips recipe",
        "smart farm IoT",
        "healthy snack meme",
        "looksmaxxing food",
        "superfood routine",
        "Korean health food",
        "hydroponics harvest",
    ]

    collected = []

    for query in search_queries:
        try:
            response = youtube.search().list(
                q=query,
                part="snippet",
                type="video",
                order="viewCount",
                maxResults=5,
                publishedAfter=(datetime.now().replace(day=max(1, datetime.now().day - 7))).strftime("%Y-%m-%dT00:00:00Z"),
                videoDuration="short",
                regionCode="US",
            ).execute()

            video_ids = [item["id"]["videoId"] for item in response.get("items", [])]

            # 조회수/좋아요 등 통계 가져오기
            stats = {}
            if video_ids:
                stats_response = youtube.videos().list(
                    part="statistics",
                    id=",".join(video_ids),
                ).execute()
                for v in stats_response.get("items", []):
                    s = v["statistics"]
                    stats[v["id"]] = {
                        "views": int(s.get("viewCount", 0)),
                        "likes": int(s.get("likeCount", 0)),
                        "comments": int(s.get("commentCount", 0)),
                    }

            for item in response.get("items", []):
                vid = item["id"]["videoId"]
                st = stats.get(vid, {"views": 0, "likes": 0, "comments": 0})
                collected.append({
                    "source": "youtube_shorts",
                    "query": query,
                    "title": item["snippet"]["title"],
                    "channel": item["snippet"]["channelTitle"],
                    "video_id": vid,
                    "published": item["snippet"]["publishedAt"],
                    "views": st["views"],
                    "likes": st["likes"],
                    "comments": st["comments"],
                })
        except Exception as e:
            print(f"[WARN] YouTube 검색 실패 ({query}): {e}")

    # 조회수 내림차순 정렬
    collected.sort(key=lambda x: x["views"], reverse=True)
    print(f"[✓] YouTube Shorts 수집 완료: {len(collected)}개 영상")
    return collected


# ─────────────────────────────────────────
# STEP 2: Claude API로 분석 + 콘텐츠 제안
# ─────────────────────────────────────────
def analyze_with_claude(trends: list, videos: list) -> dict:
    """
    수집된 트렌드를 Claude에게 보내서
    Farmetry 콘텐츠 아이디어 3개 생성
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 트렌드 요약
    trends_text = "\n".join(
        [f"- [Google Trends] '{t['keyword']}' — avg: {t['avg_interest']}, peak: {t['peak_interest']}"
         for t in trends if t["source"] == "google_trends"]
    )

    rising_text = "\n".join(
        [f"- [Rising] '{t['keyword']}' -> '{t['rising_query']}' ({t['rise_value']})"
         for t in trends if t["source"] == "google_trends_rising"]
    )

    videos_text = "\n".join(
        [f"- [YouTube] '{v['title']}' by {v['channel']} | views: {v.get('views',0):,} | likes: {v.get('likes',0):,} (query: {v['query']})"
         for v in videos[:20]]
    )

    # 채널별 통계 집계
    channel_stats = {}
    for v in videos:
        ch = v["channel"]
        if ch not in channel_stats:
            channel_stats[ch] = {"count": 0, "total_views": 0, "total_likes": 0, "queries": set()}
        channel_stats[ch]["count"] += 1
        channel_stats[ch]["total_views"] += v.get("views", 0)
        channel_stats[ch]["total_likes"] += v.get("likes", 0)
        channel_stats[ch]["queries"].add(v["query"])

    channels_text = "\n".join(
        [f"- {ch}: {s['count']} videos, {s['total_views']:,} total views, {s['total_likes']:,} likes, topics: {', '.join(s['queries'])}"
         for ch, s in sorted(channel_stats.items(), key=lambda x: x[1]["total_views"], reverse=True)[:15]]
    )

    prompt = f"""
You are an SNS marketer for Farmetry, a K-IoT smart farm startup.
Farmetry is crowdfunding IoT-grown kale chips in the US.
Core message: "Korean IoT tech meets superfood culture"

Today's trend data:

[Google Trends - US 7 days]
{trends_text}

[Rising queries]
{rising_text}

[YouTube Shorts trending - top by views]
{videos_text}

[Active channels in our niche]
{channels_text}

---

Do THREE things:

1. Create 3 Farmetry Reels content ideas
2. Pick top 5 reference videos Farmetry should study (explain WHY each is worth studying)
3. Recommend 3 channels Farmetry should follow/benchmark (explain what to learn from each)

[Suitable meme formats]
- Average X enjoyer vs Average Y enjoyer
- Looksmaxxing / glow up
- POV series
- Expectation vs Reality
- Before/After

[Farmetry connection points]
- IoT sensors monitor kale 24/7
- Pesticide-free, optimized nutrients
- Korean tech + superfood
- Kale chips = tasty like snacks

Output ONLY valid JSON, no other text:

{{
  "ideas": [
    {{
      "rank": 1,
      "viral_potential": "High/Medium/Low",
      "format": "meme format name",
      "source_trend": "referenced trend/video",
      "title": "reels title",
      "slides": ["slide 1 text", "slide 2 text", "slide 3 text"],
      "bgm": "recommended BGM",
      "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"],
      "reason": "one-line explanation why this format fits Farmetry"
    }}
  ],
  "reference_videos": [
    {{
      "title": "video title",
      "channel": "channel name",
      "why_study": "what Farmetry can learn from this video"
    }}
  ],
  "recommended_channels": [
    {{
      "channel": "channel name",
      "category": "e.g. health food / smart farm / meme marketing",
      "what_to_learn": "specific takeaway for Farmetry"
    }}
  ],
  "summary": "one-line summary of today's trends"
}}
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

    print(f"[OK] Claude 분석 완료: {len(result['ideas'])}개 아이디어 생성")
    return result


# ─────────────────────────────────────────
# STEP 3: Notion에 저장
# ─────────────────────────────────────────
def save_to_notion(analysis: dict):
    """
    분석 결과를 Notion 데이터베이스에 저장
    """
    from notion_client import Client as NotionClient
    notion = NotionClient(auth=NOTION_TOKEN)
    today = datetime.now().strftime("%Y-%m-%d")

    for idea in analysis["ideas"]:
        slides_text = "\n".join(
            [f"슬라이드 {i+1}: {s}" for i, s in enumerate(idea["slides"])]
        )
        hashtags_text = " ".join(idea["hashtags"])

        try:
            notion.pages.create(
                parent={"database_id": NOTION_DATABASE_ID},
                properties={
                    "제목": {
                        "title": [{"text": {"content": idea["title"]}}]
                    },
                    "날짜": {
                        "date": {"start": today}
                    },
                    "포맷": {
                        "rich_text": [{"text": {"content": idea["format"]}}]
                    },
                    "바이럴 가능성": {
                        "select": {"name": idea["viral_potential"]}
                    },
                    "BGM": {
                        "rich_text": [{"text": {"content": idea["bgm"]}}]
                    },
                    "해시태그": {
                        "rich_text": [{"text": {"content": hashtags_text}}]
                    },
                    "슬라이드": {
                        "rich_text": [{"text": {"content": slides_text}}]
                    },
                    "참고 트렌드": {
                        "rich_text": [{"text": {"content": idea["source_trend"]}}]
                    },
                },
            )
            print(f"[✓] Notion 저장: {idea['title']}")
        except Exception as e:
            print(f"[WARN] Notion 저장 실패: {e}")


# ─────────────────────────────────────────
# STEP 3-B: Obsidian에 마크다운 저장 (그래프 뷰 연동)
# ─────────────────────────────────────────
CONCEPT_MAP = {
    "kale chips recipe": "Kale Chips",
    "smart farm IoT": "Smart Farm",
    "healthy snack meme": "Health Meme",
    "looksmaxxing food": "Looksmaxxing",
    "superfood routine": "Superfood",
    "Korean health food": "K-Food",
    "hydroponics harvest": "Hydroponics",
}


def _safe_filename(text: str) -> str:
    """파일명에 쓸 수 없는 문자 제거"""
    for ch in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        text = text.replace(ch, '')
    return text[:80].strip()


def save_to_obsidian(analysis: dict, videos: list):
    """
    Obsidian vault에 그래프 뷰용 연결 노트 저장:
    - 컨셉 노트 (태그 허브)
    - 인기 영상 노트 (개별)
    - 데일리 아이디어 노트 (종합)
    """
    today = datetime.now().strftime("%Y-%m-%d")
    base = OBSIDIAN_VAULT / "Farmetry"
    concepts_dir = base / "Concepts"
    videos_dir = base / "Videos" / today
    ideas_dir = base / "Ideas"

    for d in [concepts_dir, videos_dir, ideas_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # ── 1. 컨셉 노트 (태그 허브) ──
    for query, concept in CONCEPT_MAP.items():
        path = concepts_dir / f"{concept}.md"
        if not path.exists():
            path.write_text(
                f"# {concept}\n\n"
                f"검색어: `{query}`\n\n"
                f"## 관련 영상\n\n"
                f"## 관련 아이디어\n",
                encoding="utf-8",
            )

    # ── 2. 인기 영상 노트 (조회수 상위 20개) ──
    top_videos = [v for v in videos if v.get("views", 0) > 0][:20]
    saved_video_names = []

    for v in top_videos:
        concept = CONCEPT_MAP.get(v["query"], "Etc")
        safe_title = _safe_filename(v["title"])
        note_name = f"{safe_title}"
        saved_video_names.append((note_name, v, concept))

        lines = [
            f"# {v['title']}",
            "",
            f"| 항목 | 내용 |",
            f"|---|---|",
            f"| 채널 | {v['channel']} |",
            f"| 조회수 | {v['views']:,} |",
            f"| 좋아요 | {v['likes']:,} |",
            f"| 댓글 | {v['comments']:,} |",
            f"| 게시일 | {v['published'][:10]} |",
            f"| 검색어 | `{v['query']}` |",
            "",
            f"[YouTube 링크](https://youtube.com/watch?v={v['video_id']})",
            "",
            f"## 연결",
            f"- 컨셉: [[{concept}]]",
            f"- 수집일: [[{today} 콘텐츠 아이디어]]",
            "",
            f"#farmetry #youtube #{concept.lower().replace(' ', '_')}",
        ]

        filepath = videos_dir / f"{safe_title}.md"
        filepath.write_text("\n".join(lines), encoding="utf-8")

    print(f"[OK] Obsidian 영상 노트 저장: {len(saved_video_names)}개")

    # ── 3. 컨셉 노트에 오늘 영상 링크 추가 ──
    for concept in CONCEPT_MAP.values():
        path = concepts_dir / f"{concept}.md"
        content = path.read_text(encoding="utf-8")

        new_links = []
        for note_name, v, c in saved_video_names:
            if c == concept:
                new_links.append(f"- [[{note_name}]] ({v['views']:,} views)")

        if new_links:
            append_text = f"\n### {today}\n" + "\n".join(new_links) + "\n"
            path.write_text(content + append_text, encoding="utf-8")

    # ── 4. 데일리 아이디어 노트 ──
    filepath = ideas_dir / f"{today} 콘텐츠 아이디어.md"

    lines = [
        f"# Farmetry 콘텐츠 아이디어 — {today}",
        "",
        f"> {analysis['summary']}",
        "",
    ]

    # 참고한 영상 링크
    if saved_video_names:
        lines.append("## 오늘의 인기 영상 Top 5")
        lines.append("")
        for note_name, v, concept in saved_video_names[:5]:
            lines.append(f"- [[{note_name}]] — {v['views']:,} views ([[{concept}]])")
        lines.extend(["", "---", ""])

    # 아이디어
    lines.append("## 콘텐츠 아이디어")
    lines.append("")

    for idea in analysis["ideas"]:
        # 해시태그를 컨셉으로 연결
        concept_links = []
        for tag in idea.get("hashtags", []):
            clean = tag.replace("#", "")
            for c_name in CONCEPT_MAP.values():
                if clean.lower() in c_name.lower() or c_name.lower() in clean.lower():
                    concept_links.append(f"[[{c_name}]]")

        lines.extend([
            f"### {idea['rank']}. {idea['title']}",
            "",
            f"| 항목 | 내용 |",
            f"|---|---|",
            f"| 포맷 | {idea['format']} |",
            f"| 바이럴 가능성 | {idea['viral_potential']} |",
            f"| 참고 트렌드 | {idea['source_trend']} |",
            f"| BGM | {idea['bgm']} |",
            "",
            "**슬라이드:**",
            "",
        ])
        for i, slide in enumerate(idea["slides"]):
            lines.append(f"{i+1}. {slide}")

        lines.append("")
        lines.append(f"**해시태그:** {' '.join(idea['hashtags'])}")
        if concept_links:
            lines.append(f"**컨셉 연결:** {' '.join(set(concept_links))}")
        lines.extend([
            "",
            f"*{idea['reason']}*",
            "",
            "---",
            "",
        ])

    # ── 참고 영상 추천 ──
    ref_videos = analysis.get("reference_videos", [])
    if ref_videos:
        lines.extend(["## 참고할 영상 Top 5", ""])
        for rv in ref_videos:
            # 수집 영상 중 매칭되는 것 찾아서 wikilink
            matched_note = None
            for note_name, v, _ in saved_video_names:
                if rv["title"].lower() in v["title"].lower() or v["title"].lower() in rv["title"].lower():
                    matched_note = note_name
                    break
            link = f"[[{matched_note}]]" if matched_note else f"**{rv['title']}**"
            lines.append(f"- {link} ({rv['channel']})")
            lines.append(f"  - {rv['why_study']}")
        lines.extend(["", "---", ""])

    # ── 추천 채널 ──
    rec_channels = analysis.get("recommended_channels", [])
    if rec_channels:
        lines.extend(["## 벤치마킹 채널", ""])
        for rc in rec_channels:
            lines.append(f"### {rc['channel']}")
            lines.append(f"- 카테고리: {rc['category']}")
            lines.append(f"- 배울 점: {rc['what_to_learn']}")
            lines.append("")
        lines.extend(["---", ""])

    # 태그
    lines.append("#farmetry #daily_ideas")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Obsidian 아이디어 노트 저장: {filepath}")


# ─────────────────────────────────────────
# STEP 4: 카카오톡 알림 (선택)
# ─────────────────────────────────────────
def send_kakao_alert(analysis: dict):
    """
    카카오톡으로 오늘의 콘텐츠 아이디어 알림
    """
    top = analysis["ideas"][0]
    message = (
        f"🌱 Farmetry 오늘의 콘텐츠 아이디어\n\n"
        f"📊 트렌드: {analysis['summary']}\n\n"
        f"🥇 TOP 아이디어\n"
        f"포맷: {top['format']}\n"
        f"제목: {top['title']}\n"
        f"바이럴 가능성: {top['viral_potential']}\n"
        f"BGM: {top['bgm']}\n\n"
        f"슬라이드:\n"
        + "\n".join([f"  {i+1}. {s}" for i, s in enumerate(top["slides"])])
        + f"\n\n해시태그: {' '.join(top['hashtags'][:5])}"
    )

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {KAKAO_TOKEN}"}
    data = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": message,
            "link": {"web_url": "https://www.notion.so"},
        })
    }

    try:
        resp = requests.post(url, headers=headers, data=data)
        if resp.status_code == 200:
            print("[✓] 카카오톡 알림 발송 완료")
        else:
            print(f"[WARN] 카카오톡 알림 실패: {resp.text}")
    except Exception as e:
        print(f"[WARN] 카카오톡 연결 실패: {e}")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────
def run():
    print("=" * 50)
    print(f"🌱 Farmetry Meme Agent 시작: {datetime.now()}")
    print("=" * 50)

    # 필수 환경변수 체크
    if not ANTHROPIC_API_KEY:
        print("[ERROR] Anthropic API 키가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return

    # 1. 트렌드 수집
    print("\n[1/4] Google Trends 수집 중...")
    trends = fetch_google_trends()

    print("\n[2/4] YouTube Shorts 수집 중...")
    videos = fetch_youtube_shorts()

    if not trends and not videos:
        print("[ERROR] 트렌드 데이터를 수집하지 못했습니다.")
        return

    # 2. Claude 분석
    print("\n[3/4] Claude 분석 중...")
    analysis = analyze_with_claude(trends, videos)

    # 3. 결과 출력
    print("\n📋 오늘의 콘텐츠 아이디어:")
    print(json.dumps(analysis, ensure_ascii=False, indent=2))

    # 4. Obsidian 저장
    print("\n[4/4] 결과 저장 중...")
    save_to_obsidian(analysis, videos)

    # 5. Notion 저장 (토큰 있을 때만)
    if NOTION_TOKEN and NOTION_DATABASE_ID:
        save_to_notion(analysis)

    # 5. 카카오톡 알림 (토큰 있을 때만)
    if KAKAO_TOKEN:
        send_kakao_alert(analysis)

    # 6. 대시보드용 JSON DB 저장
    save_to_dashboard_db(analysis, videos)

    # 7. JSON 파일로도 저장 (백업)
    filename = SCRIPT_DIR / f"results_{datetime.now().strftime('%Y%m%d')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 결과 저장: {filename}")
    print("=" * 50)


def save_to_dashboard_db(analysis: dict, videos: list):
    """대시보드에서 읽을 JSON DB 저장/업데이트"""
    db_path = SCRIPT_DIR / "data" / "db.json"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 기존 DB 로드
    if db_path.exists():
        db = json.loads(db_path.read_text(encoding="utf-8"))
    else:
        db = {"videos": [], "ideas": [], "runs": []}

    today = datetime.now().strftime("%Y-%m-%d")

    # 영상 추가 (중복 체크)
    existing_ids = {v["video_id"] for v in db["videos"]}
    for v in videos:
        if v["video_id"] not in existing_ids:
            db["videos"].append({
                "video_id": v["video_id"],
                "title": v["title"],
                "channel": v["channel"],
                "views": v.get("views", 0),
                "likes": v.get("likes", 0),
                "comments": v.get("comments", 0),
                "query": v["query"],
                "published": v.get("published", ""),
                "date_collected": today,
                "concept": CONCEPT_MAP.get(v["query"], "Etc"),
                "hidden": False,
            })

    # 아이디어 추가
    for idea in analysis["ideas"]:
        idea["date"] = today
        idea["hidden"] = False
    db["ideas"].extend(analysis["ideas"])

    # 실행 기록
    db["runs"].append({
        "date": today,
        "videos_collected": len(videos),
        "ideas_generated": len(analysis["ideas"]),
        "summary": analysis.get("summary", ""),
        "reference_videos": analysis.get("reference_videos", []),
        "recommended_channels": analysis.get("recommended_channels", []),
    })

    db_path.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Dashboard DB 저장: {db_path}")


if __name__ == "__main__":
    run()
