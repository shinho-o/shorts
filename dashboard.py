"""
Farmetry Dashboard — JSON DB 기반 웹 대시보드
"""
import os
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
DB_PATH = SCRIPT_DIR / "data" / "db.json"

app = Flask(__name__)

CONCEPT_MAP = {
    "kale chips recipe": "Kale Chips",
    "smart farm IoT": "Smart Farm",
    "healthy snack meme": "Health Meme",
    "looksmaxxing food": "Looksmaxxing",
    "superfood routine": "Superfood",
    "Korean health food": "K-Food",
    "hydroponics harvest": "Hydroponics",
}


def load_db():
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text(encoding="utf-8"))
    return {"videos": [], "ideas": [], "runs": []}


def save_db(db):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


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
    """YouTube 채널 URL, @handle, 또는 채널명 → channel_id + 채널 정보"""
    if not YOUTUBE_API_KEY:
        return None
    youtube = _yt()

    channel_id = None

    # @handle or URL with @
    m = re.search(r"@([\w.-]+)", input_str)
    if m:
        handle = m.group(1)
        resp = youtube.search().list(part="snippet", q=f"@{handle}", type="channel", maxResults=1).execute()
        items = resp.get("items", [])
        if items:
            channel_id = items[0]["snippet"]["channelId"]

    # /channel/UCxxxx URL
    if not channel_id:
        m = re.search(r"channel/(UC[\w-]+)", input_str)
        if m:
            channel_id = m.group(1)

    # /c/name or plain search
    if not channel_id:
        resp = youtube.search().list(part="snippet", q=input_str, type="channel", maxResults=1).execute()
        items = resp.get("items", [])
        if items:
            channel_id = items[0]["snippet"]["channelId"]

    if not channel_id:
        return None

    # 채널 상세 정보
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
    """채널의 최근 영상 가져오기 (통계 포함)"""
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
    db = load_db()
    videos = [v for v in db["videos"] if not v.get("hidden")]
    hidden_count = sum(1 for v in db["videos"] if v.get("hidden"))
    ideas = [i for i in db["ideas"] if not i.get("hidden")]
    hidden_ideas = sum(1 for i in db["ideas"] if i.get("hidden"))
    runs = db.get("runs", [])

    # channel stats
    channel_stats = {}
    for v in db["videos"]:
        if v.get("hidden"):
            continue
        ch = v["channel"]
        if ch not in channel_stats:
            channel_stats[ch] = {"count": 0, "total_views": 0, "total_likes": 0, "topics": set()}
        channel_stats[ch]["count"] += 1
        channel_stats[ch]["total_views"] += v.get("views", 0)
        channel_stats[ch]["total_likes"] += v.get("likes", 0)
        channel_stats[ch]["topics"].add(v.get("concept", ""))
    for s in channel_stats.values():
        s["engagement"] = (s["total_likes"] / s["total_views"] * 100) if s["total_views"] > 0 else 0
        s["topics"] = list(s["topics"])
    channel_stats = dict(sorted(channel_stats.items(), key=lambda x: x[1]["total_views"], reverse=True)[:20])

    concepts = list(CONCEPT_MAP.values())
    total_views = sum(v.get("views", 0) for v in videos)

    # latest recommendations
    latest_run = runs[-1] if runs else {}

    saved_channels = db.get("channels", [])

    return render_template("index.html",
        videos=sorted(videos, key=lambda x: x.get("views", 0), reverse=True),
        ideas=list(reversed(ideas)),
        concepts=concepts,
        channel_stats=channel_stats,
        total_views=total_views,
        hidden_count=hidden_count,
        hidden_ideas=hidden_ideas,
        latest_run=latest_run,
        runs=runs,
        saved_channels=saved_channels,
    )


@app.route("/api/videos")
def api_videos():
    db = load_db()
    show_hidden = request.args.get("hidden", "false") == "true"
    videos = db["videos"] if show_hidden else [v for v in db["videos"] if not v.get("hidden")]
    return jsonify(videos)


@app.route("/add_video", methods=["POST"])
def add_video():
    url = request.form.get("url", "").strip()
    concept = request.form.get("concept", "Etc")
    if not url:
        return redirect("/")
    info = fetch_youtube_info(url)
    if not info:
        return redirect("/")
    db = load_db()
    existing_ids = {v["video_id"] for v in db["videos"]}
    if info["video_id"] not in existing_ids:
        db["videos"].append({
            "video_id": info["video_id"],
            "title": info["title"],
            "channel": info["channel"],
            "views": info["views"],
            "likes": info["likes"],
            "comments": info["comments"],
            "query": "manual",
            "published": info["published"],
            "date_collected": datetime.now().strftime("%Y-%m-%d"),
            "concept": concept,
            "hidden": False,
        })
        save_db(db)
    return redirect("/")


@app.route("/toggle_video", methods=["POST"])
def toggle_video():
    data = request.json
    vid = data.get("video_id")
    db = load_db()
    for v in db["videos"]:
        if v["video_id"] == vid:
            v["hidden"] = not v.get("hidden", False)
            break
    save_db(db)
    return jsonify({"ok": True})


@app.route("/toggle_idea", methods=["POST"])
def toggle_idea():
    data = request.json
    idx = data.get("index")
    db = load_db()
    if 0 <= idx < len(db["ideas"]):
        db["ideas"][idx]["hidden"] = not db["ideas"][idx].get("hidden", False)
    save_db(db)
    return jsonify({"ok": True})


@app.route("/add_channel", methods=["POST"])
def add_channel():
    """YouTube 채널 추가 — URL, @handle, 채널명 모두 가능"""
    data = request.form if request.form else request.json or {}
    channel_input = data.get("channel", "").strip()
    category = data.get("category", "").strip()
    note = data.get("note", "").strip()
    if not channel_input:
        return redirect("/")

    db = load_db()
    if "channels" not in db:
        db["channels"] = []

    # YouTube API로 채널 정보 가져오기
    ch_info = resolve_channel_id(channel_input)
    if ch_info:
        existing = {c.get("channel_id", "").lower() for c in db["channels"]}
        if ch_info["channel_id"].lower() not in existing:
            db["channels"].append({
                "channel_id": ch_info["channel_id"],
                "name": ch_info["name"],
                "thumbnail": ch_info["thumbnail"],
                "subscribers": ch_info["subscribers"],
                "total_videos": ch_info["total_videos"],
                "total_views": ch_info["total_views"],
                "description": ch_info["description"],
                "category": category or "Uncategorized",
                "note": note,
                "date_added": datetime.now().strftime("%Y-%m-%d"),
            })
            save_db(db)
    else:
        # API 실패 시 이름만 저장
        existing = {c["name"].lower() for c in db["channels"]}
        if channel_input.lower() not in existing:
            db["channels"].append({
                "channel_id": "",
                "name": channel_input,
                "thumbnail": "",
                "subscribers": 0,
                "total_videos": 0,
                "total_views": 0,
                "description": "",
                "category": category or "Uncategorized",
                "note": note,
                "date_added": datetime.now().strftime("%Y-%m-%d"),
            })
            save_db(db)
    return redirect("/")


@app.route("/remove_channel", methods=["POST"])
def remove_channel():
    data = request.json
    name = data.get("name", "")
    db = load_db()
    db["channels"] = [c for c in db.get("channels", []) if c["name"] != name]
    save_db(db)
    return jsonify({"ok": True})


@app.route("/add_idea", methods=["POST"])
def add_idea():
    """아이디어 수동 추가"""
    data = request.form if request.form else request.json or {}
    title = data.get("title", "").strip()
    fmt = data.get("format", "").strip()
    slides = data.get("slides", "").strip()
    hashtags = data.get("hashtags", "").strip()
    bgm = data.get("bgm", "").strip()
    reason = data.get("reason", "").strip()
    if not title:
        return redirect("/")
    db = load_db()
    db["ideas"].append({
        "rank": 0,
        "viral_potential": data.get("viral_potential", "Medium"),
        "format": fmt,
        "source_trend": "manual",
        "title": title,
        "slides": [s.strip() for s in slides.split("\n") if s.strip()] if slides else [],
        "bgm": bgm,
        "hashtags": [h.strip() for h in hashtags.split() if h.strip()],
        "reason": reason,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "hidden": False,
    })
    save_db(db)
    return redirect("/")


@app.route("/channel/<channel_id>")
def channel_detail(channel_id):
    """채널 상세 — 최근 영상 목록"""
    db = load_db()
    ch = None
    for c in db.get("channels", []):
        if c.get("channel_id") == channel_id:
            ch = c
            break
    if not ch:
        return redirect("/")

    videos = fetch_channel_videos(channel_id, max_results=15)
    existing_ids = {v["video_id"] for v in db["videos"]}
    for v in videos:
        v["already_added"] = v["video_id"] in existing_ids

    concepts = list(CONCEPT_MAP.values())
    return render_template("channel.html", ch=ch, videos=videos, concepts=concepts)


@app.route("/import_video", methods=["POST"])
def import_video():
    """채널 상세에서 영상 가져오기"""
    data = request.json or {}
    video_id = data.get("video_id", "")
    concept = data.get("concept", "Etc")
    if not video_id:
        return jsonify({"error": "no video_id"}), 400

    info = fetch_youtube_info(f"https://youtube.com/watch?v={video_id}")
    if not info:
        return jsonify({"error": "fetch failed"}), 400

    db = load_db()
    existing_ids = {v["video_id"] for v in db["videos"]}
    if info["video_id"] not in existing_ids:
        db["videos"].append({
            "video_id": info["video_id"],
            "title": info["title"],
            "channel": info["channel"],
            "views": info["views"],
            "likes": info["likes"],
            "comments": info["comments"],
            "query": "channel_import",
            "published": info["published"],
            "date_collected": datetime.now().strftime("%Y-%m-%d"),
            "concept": concept,
            "hidden": False,
        })
        save_db(db)
    return jsonify({"ok": True})


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
