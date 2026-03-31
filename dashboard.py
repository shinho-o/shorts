"""
Farmetry Dashboard — Supabase DB 기반 웹 대시보드
"""
import os
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv
from supabase import create_client

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

app = Flask(__name__)

PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "gemini-2.5-flash": {"input": 0.0, "output": 0.0},
}

def log_usage(service, model, endpoint, tokens_in=0, tokens_out=0, project="shorts"):
    cost = 0
    if model in PRICING:
        cost = (tokens_in * PRICING[model]["input"] + tokens_out * PRICING[model]["output"]) / 1_000_000
    try:
        sb().table("api_usage").insert({
            "service": service, "model": model, "endpoint": endpoint,
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "cost_usd": round(cost, 6), "project": project,
        }).execute()
    except Exception:
        pass

CONCEPT_MAP = {
    "kale chips recipe": "Kale Chips",
    "smart farm IoT": "Smart Farm",
    "healthy snack meme": "Health Meme",
    "looksmaxxing food": "Looksmaxxing",
    "superfood routine": "Superfood",
    "Korean health food": "K-Food",
    "hydroponics harvest": "Hydroponics",
}


def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── YouTube helpers ──

def _yt():
    from googleapiclient.discovery import build
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def fetch_youtube_info(url):
    if not YOUTUBE_API_KEY:
        return None
    video_id = None
    for pattern in [r"v=([^&]+)", r"youtu\.be/([^?]+)", r"shorts/([^?]+)"]:
        m = re.search(pattern, url)
        if m:
            video_id = m.group(1)
            break
    if not video_id:
        return None
    youtube = _yt()
    resp = youtube.videos().list(part="snippet,statistics", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        return None
    item = items[0]
    s = item["statistics"]
    return {
        "video_id": video_id,
        "title": item["snippet"]["title"],
        "channel": item["snippet"]["channelTitle"],
        "views": int(s.get("viewCount", 0)),
        "likes": int(s.get("likeCount", 0)),
        "comments": int(s.get("commentCount", 0)),
        "published": item["snippet"]["publishedAt"][:10],
    }


def resolve_channel_id(input_str):
    if not YOUTUBE_API_KEY:
        return None
    youtube = _yt()
    channel_id = None

    m = re.search(r"@([\w.-]+)", input_str)
    if m:
        resp = youtube.search().list(part="snippet", q=f"@{m.group(1)}", type="channel", maxResults=1).execute()
        items = resp.get("items", [])
        if items:
            channel_id = items[0]["snippet"]["channelId"]

    if not channel_id:
        m = re.search(r"channel/(UC[\w-]+)", input_str)
        if m:
            channel_id = m.group(1)

    if not channel_id:
        resp = youtube.search().list(part="snippet", q=input_str, type="channel", maxResults=1).execute()
        items = resp.get("items", [])
        if items:
            channel_id = items[0]["snippet"]["channelId"]

    if not channel_id:
        return None

    ch_resp = youtube.channels().list(part="snippet,statistics", id=channel_id).execute()
    ch_items = ch_resp.get("items", [])
    if not ch_items:
        return None
    ch = ch_items[0]
    return {
        "channel_id": channel_id,
        "name": ch["snippet"]["title"],
        "description": ch["snippet"].get("description", "")[:200],
        "thumbnail": ch["snippet"]["thumbnails"].get("medium", {}).get("url", ""),
        "subscribers": int(ch["statistics"].get("subscriberCount", 0)),
        "total_videos": int(ch["statistics"].get("videoCount", 0)),
        "total_views": int(ch["statistics"].get("viewCount", 0)),
    }


def fetch_channel_videos(channel_id, max_results=12):
    if not YOUTUBE_API_KEY:
        return []
    youtube = _yt()
    resp = youtube.search().list(
        part="snippet", channelId=channel_id, type="video",
        order="date", maxResults=max_results,
    ).execute()
    video_ids = [item["id"]["videoId"] for item in resp.get("items", [])]
    if not video_ids:
        return []
    stats_resp = youtube.videos().list(part="statistics,snippet", id=",".join(video_ids)).execute()
    videos = []
    for item in stats_resp.get("items", []):
        s = item["statistics"]
        videos.append({
            "video_id": item["id"],
            "title": item["snippet"]["title"],
            "channel": item["snippet"]["channelTitle"],
            "views": int(s.get("viewCount", 0)),
            "likes": int(s.get("likeCount", 0)),
            "comments": int(s.get("commentCount", 0)),
            "published": item["snippet"]["publishedAt"][:10],
            "thumbnail": item["snippet"]["thumbnails"].get("medium", {}).get("url", ""),
        })
    videos.sort(key=lambda x: x["views"], reverse=True)
    return videos


# ── Routes ──

@app.route("/")
def index():
    s = sb()
    all_videos = s.table("videos").select("*").execute().data
    all_ideas = s.table("ideas").select("*").execute().data
    runs = s.table("runs").select("*").order("id", desc=True).execute().data
    saved_channels = s.table("channels").select("*").execute().data
    search_queries = s.table("search_queries").select("*").order("id").execute().data

    videos = [v for v in all_videos if not v.get("hidden")]
    hidden_count = sum(1 for v in all_videos if v.get("hidden"))
    ideas = [i for i in all_ideas if not i.get("hidden")]
    hidden_ideas = sum(1 for i in all_ideas if i.get("hidden"))

    channel_stats = {}
    for v in videos:
        ch = v["channel"]
        if ch not in channel_stats:
            channel_stats[ch] = {"count": 0, "total_views": 0, "total_likes": 0, "topics": set()}
        channel_stats[ch]["count"] += 1
        channel_stats[ch]["total_views"] += v.get("views", 0)
        channel_stats[ch]["total_likes"] += v.get("likes", 0)
        channel_stats[ch]["topics"].add(v.get("concept", ""))
    for cs in channel_stats.values():
        cs["engagement"] = (cs["total_likes"] / cs["total_views"] * 100) if cs["total_views"] > 0 else 0
        cs["topics"] = list(cs["topics"])
    channel_stats = dict(sorted(channel_stats.items(), key=lambda x: x[1]["total_views"], reverse=True)[:20])

    concepts = list(CONCEPT_MAP.values())
    total_views = sum(v.get("views", 0) for v in videos)
    latest_run = runs[0] if runs else {}
    usage = s.table("api_usage").select("*").order("id", desc=True).limit(50).execute().data

    return render_template("index.html",
        videos=sorted(videos, key=lambda x: x.get("views", 0), reverse=True),
        ideas=sorted(ideas, key=lambda x: x.get("id", 0), reverse=True),
        concepts=concepts,
        channel_stats=channel_stats,
        total_views=total_views,
        hidden_count=hidden_count,
        hidden_ideas=hidden_ideas,
        latest_run=latest_run,
        runs=runs,
        saved_channels=saved_channels,
        search_queries=search_queries,
        usage=usage,
        total_cost=round(sum(u.get("cost_usd", 0) or 0 for u in usage), 4),
        total_calls=len(usage),
    )


@app.route("/add_video", methods=["POST"])
def add_video():
    url = request.form.get("url", "").strip()
    concept = request.form.get("concept", "Etc")
    if not url:
        return redirect("/")
    info = fetch_youtube_info(url)
    if not info:
        return redirect("/")
    s = sb()
    s.table("videos").upsert({
        "video_id": info["video_id"], "title": info["title"], "channel": info["channel"],
        "views": info["views"], "likes": info["likes"], "comments": info["comments"],
        "query": "manual", "published": info["published"],
        "date_collected": datetime.now().strftime("%Y-%m-%d"),
        "concept": concept, "hidden": False,
    }, on_conflict="video_id").execute()
    return redirect("/")


@app.route("/toggle_video", methods=["POST"])
def toggle_video():
    data = request.json
    vid = data.get("video_id")
    s = sb()
    row = s.table("videos").select("hidden").eq("video_id", vid).execute().data
    if row:
        s.table("videos").update({"hidden": not row[0]["hidden"]}).eq("video_id", vid).execute()
    return jsonify({"ok": True})


@app.route("/toggle_idea", methods=["POST"])
def toggle_idea():
    data = request.json
    idea_id = data.get("id")
    s = sb()
    row = s.table("ideas").select("hidden").eq("id", idea_id).execute().data
    if row:
        s.table("ideas").update({"hidden": not row[0]["hidden"]}).eq("id", idea_id).execute()
    return jsonify({"ok": True})


@app.route("/add_channel", methods=["POST"])
def add_channel():
    data = request.form if request.form else request.json or {}
    channel_input = data.get("channel", "").strip()
    category = data.get("category", "").strip()
    note = data.get("note", "").strip()
    if not channel_input:
        return redirect("/")

    s = sb()
    ch_info = resolve_channel_id(channel_input)
    if ch_info:
        s.table("channels").upsert({
            "channel_id": ch_info["channel_id"], "name": ch_info["name"],
            "thumbnail": ch_info["thumbnail"], "subscribers": ch_info["subscribers"],
            "total_videos": ch_info["total_videos"], "total_views": ch_info["total_views"],
            "description": ch_info["description"],
            "category": category or "Uncategorized", "note": note,
            "date_added": datetime.now().strftime("%Y-%m-%d"),
        }, on_conflict="channel_id").execute()
    else:
        s.table("channels").insert({
            "channel_id": "", "name": channel_input, "thumbnail": "",
            "subscribers": 0, "total_videos": 0, "total_views": 0, "description": "",
            "category": category or "Uncategorized", "note": note,
            "date_added": datetime.now().strftime("%Y-%m-%d"),
        }).execute()
    return redirect("/")


@app.route("/remove_channel", methods=["POST"])
def remove_channel():
    data = request.json
    name = data.get("name", "")
    sb().table("channels").delete().eq("name", name).execute()
    return jsonify({"ok": True})


@app.route("/add_idea", methods=["POST"])
def add_idea():
    data = request.form if request.form else request.json or {}
    title = data.get("title", "").strip()
    if not title:
        return redirect("/")
    slides = data.get("slides", "").strip()
    hashtags = data.get("hashtags", "").strip()
    sb().table("ideas").insert({
        "rank": 0,
        "viral_potential": data.get("viral_potential", "Medium"),
        "format": data.get("format", "").strip(),
        "source_trend": "manual",
        "title": title,
        "slides": [s.strip() for s in slides.split("\n") if s.strip()] if slides else [],
        "bgm": data.get("bgm", "").strip(),
        "hashtags": [h.strip() for h in hashtags.split() if h.strip()] if hashtags else [],
        "reason": data.get("reason", "").strip(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "hidden": False,
    }).execute()
    return redirect("/")


@app.route("/channel/<channel_id>")
def channel_detail(channel_id):
    s = sb()
    rows = s.table("channels").select("*").eq("channel_id", channel_id).execute().data
    if not rows:
        return redirect("/")
    ch = rows[0]
    videos = fetch_channel_videos(channel_id, max_results=15)
    existing_ids = {v["video_id"] for v in s.table("videos").select("video_id").execute().data}
    for v in videos:
        v["already_added"] = v["video_id"] in existing_ids
    concepts = list(CONCEPT_MAP.values())
    return render_template("channel.html", ch=ch, videos=videos, concepts=concepts)


@app.route("/import_video", methods=["POST"])
def import_video():
    data = request.json or {}
    video_id = data.get("video_id", "")
    concept = data.get("concept", "Etc")
    if not video_id:
        return jsonify({"error": "no video_id"}), 400
    info = fetch_youtube_info(f"https://youtube.com/watch?v={video_id}")
    if not info:
        return jsonify({"error": "fetch failed"}), 400
    sb().table("videos").upsert({
        "video_id": info["video_id"], "title": info["title"], "channel": info["channel"],
        "views": info["views"], "likes": info["likes"], "comments": info["comments"],
        "query": "channel_import", "published": info["published"],
        "date_collected": datetime.now().strftime("%Y-%m-%d"),
        "concept": concept, "hidden": False,
    }, on_conflict="video_id").execute()
    return jsonify({"ok": True})


@app.route("/add_query", methods=["POST"])
def add_query():
    """수집 키워드 추가"""
    data = request.form if request.form else request.json or {}
    query = data.get("query", "").strip()
    concept = data.get("concept", "Etc").strip()
    if not query:
        return redirect("/")
    sb().table("search_queries").upsert(
        {"query": query, "concept": concept, "enabled": True},
        on_conflict="query"
    ).execute()
    return redirect("/")


@app.route("/toggle_query", methods=["POST"])
def toggle_query():
    """수집 키워드 활성/비활성"""
    data = request.json
    qid = data.get("id")
    s = sb()
    row = s.table("search_queries").select("enabled").eq("id", qid).execute().data
    if row:
        s.table("search_queries").update({"enabled": not row[0]["enabled"]}).eq("id", qid).execute()
    return jsonify({"ok": True})


@app.route("/delete_query", methods=["POST"])
def delete_query():
    data = request.json
    qid = data.get("id")
    sb().table("search_queries").delete().eq("id", qid).execute()
    return jsonify({"ok": True})


@app.route("/collect_videos", methods=["POST"])
def collect_videos():
    """활성 키워드로 YouTube 영상 일괄 수집"""
    if not YOUTUBE_API_KEY:
        return jsonify({"message": "YouTube API key missing"}), 400

    s = sb()
    queries = s.table("search_queries").select("*").eq("enabled", True).execute().data
    if not queries:
        return jsonify({"message": "No active queries", "collected": 0})

    youtube = _yt()
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now().replace(day=max(1, datetime.now().day - 7))).strftime("%Y-%m-%dT00:00:00Z")

    total_collected = 0
    results_by_query = []

    for q in queries:
        try:
            response = youtube.search().list(
                q=q["query"], part="snippet", type="video",
                order="viewCount", maxResults=5,
                publishedAfter=from_date,
                videoDuration="short", regionCode="US",
            ).execute()

            video_ids = [item["id"]["videoId"] for item in response.get("items", [])]
            if not video_ids:
                results_by_query.append({"query": q["query"], "count": 0})
                continue

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
            for item in response.get("items", []):
                vid = item["id"]["videoId"]
                st = stats.get(vid, {"views": 0, "likes": 0, "comments": 0})
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

            if rows:
                s.table("videos").upsert(rows, on_conflict="video_id").execute()
                total_collected += len(rows)

            results_by_query.append({"query": q["query"], "count": len(rows)})

        except Exception as e:
            results_by_query.append({"query": q["query"], "count": 0, "error": str(e)[:100]})

    summary = ", ".join([f"{r['query']}: {r['count']}" for r in results_by_query])
    return jsonify({
        "message": f"{total_collected}개 영상 수집 완료!\n{summary}",
        "collected": total_collected,
        "details": results_by_query,
    })


@app.route("/predict", methods=["POST"])
def predict_views():
    """제목으로 조회수 예측"""
    data = request.json or {}
    title = data.get("title", "").strip()
    concept = data.get("concept", "Etc")
    subscriber_count = data.get("subscriber_count", 0)
    if not title:
        return jsonify({"error": "title required"}), 400
    from predictor import predict
    result = predict(title, concept, subscriber_count=subscriber_count)
    return jsonify(result)


@app.route("/retrain", methods=["POST"])
def retrain_model():
    """모델 재학습"""
    from predictor import train_model
    try:
        result = train_model()
        if result:
            return jsonify({"message": "Model retrained!"})
        return jsonify({"message": "Not enough data"})
    except Exception as e:
        return jsonify({"message": str(e)})


@app.route("/run_agent", methods=["POST"])
def run_agent_route():
    try:
        result = subprocess.run(
            ["python", str(SCRIPT_DIR / "agent.py")],
            capture_output=True, text=True, timeout=300,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            return jsonify({"message": "Done! Refresh page."})
        else:
            return jsonify({"message": f"Error: {result.stderr[-300:]}"})
    except Exception as e:
        return jsonify({"message": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print("=" * 50)
    print(f"Farmetry Dashboard: http://localhost:{port}")
    print("=" * 50)
    from waitress import serve
    if port == 5001:
        import webbrowser
        webbrowser.open(f"http://localhost:{port}")
    serve(app, host="0.0.0.0", port=port)
