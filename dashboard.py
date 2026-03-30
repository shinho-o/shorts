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
    from googleapiclient.discovery import build
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
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
