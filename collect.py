"""
자동 수집 스크립트 — GitHub Actions 또는 수동 실행용
활성 키워드로 YouTube Shorts 수집 → Supabase에 저장
"""
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / ".env")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def run():
    if not YOUTUBE_API_KEY:
        print("[ERROR] YOUTUBE_API_KEY missing")
        sys.exit(1)
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] SUPABASE_URL/KEY missing")
        sys.exit(1)

    from supabase import create_client
    from googleapiclient.discovery import build

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = datetime.now().replace(day=max(1, datetime.now().day - 7)).strftime("%Y-%m-%dT00:00:00Z")

    # 활성 키워드 가져오기
    queries = sb.table("search_queries").select("*").eq("enabled", True).execute().data
    if not queries:
        print("[SKIP] No active queries")
        return

    print(f"[START] {len(queries)} queries, date={today}")
    total = 0

    for q in queries:
        try:
            response = youtube.search().list(
                q=q["query"], part="snippet", type="video",
                order="viewCount", maxResults=10,
                publishedAfter=from_date,
                videoDuration="short", regionCode="US",
            ).execute()

            video_ids = [item["id"]["videoId"] for item in response.get("items", [])]
            if not video_ids:
                print(f"  [{q['query']}] 0 videos")
                continue

            # 최신순으로도 추가 수집
            recent = youtube.search().list(
                q=q["query"], part="snippet", type="video",
                order="date", maxResults=5,
                publishedAfter=from_date,
                videoDuration="short", regionCode="US",
            ).execute()
            for item in recent.get("items", []):
                vid = item["id"]["videoId"]
                if vid not in video_ids:
                    video_ids.append(vid)

            # 통계 가져오기
            stats_resp = youtube.videos().list(
                part="statistics", id=",".join(video_ids)
            ).execute()
            stats = {}
            for v in stats_resp.get("items", []):
                st = v["statistics"]
                stats[v["id"]] = {
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0)),
                }

            rows = []
            for item in response.get("items", []) + recent.get("items", []):
                vid = item["id"]["videoId"]
                if vid not in stats:
                    continue
                st = stats[vid]
                rows.append({
                    "video_id": vid,
                    "title": item["snippet"]["title"],
                    "channel": item["snippet"]["channelTitle"],
                    "views": st["views"],
                    "likes": st["likes"],
                    "comments": st["comments"],
                    "query": q["query"],
                    "published": item["snippet"]["publishedAt"][:10],
                    "date_collected": today,
                    "concept": q.get("concept", "Etc"),
                    "hidden": False,
                })

            # 중복 제거
            seen = set()
            unique_rows = []
            for r in rows:
                if r["video_id"] not in seen:
                    seen.add(r["video_id"])
                    unique_rows.append(r)

            if unique_rows:
                sb.table("videos").upsert(unique_rows, on_conflict="video_id").execute()
                total += len(unique_rows)

            print(f"  [{q['query']}] {len(unique_rows)} videos")

        except Exception as e:
            print(f"  [{q['query']}] ERROR: {e}")

    # 수집 기록 저장
    sb.table("runs").insert({
        "date": today,
        "videos_collected": total,
        "ideas_generated": 0,
        "summary": f"Auto-collect: {total} videos from {len(queries)} queries",
        "reference_videos": [],
        "recommended_channels": [],
    }).execute()

    print(f"[DONE] {total} videos collected")


if __name__ == "__main__":
    run()
