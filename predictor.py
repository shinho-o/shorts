"""
조회수 예측 모델
수집된 YouTube 영상 데이터를 기반으로 제목/컨셉에서 조회수 등급을 예측
"""
import os
import re
import json
import math
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

CHANNEL_CACHE_PATH = Path(__file__).parent / "data" / "channel_cache.json"


def _load_channel_cache() -> dict:
    """채널 구독자 수 캐시 로드"""
    if CHANNEL_CACHE_PATH.exists():
        with open(CHANNEL_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_channel_cache(cache: dict):
    """채널 구독자 수 캐시 저장"""
    CHANNEL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHANNEL_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def fetch_subscriber_counts(channel_names: list[str]) -> dict[str, int]:
    """YouTube API로 채널 구독자 수 조회 (캐시 활용)

    Args:
        channel_names: 채널명 리스트

    Returns:
        {channel_name: subscriber_count} 딕셔너리
    """
    cache = _load_channel_cache()
    missing = [ch for ch in channel_names if ch not in cache]

    if missing and YOUTUBE_API_KEY:
        try:
            from googleapiclient.discovery import build
            youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

            # 채널명으로 검색 후 구독자 수 가져오기 (배치로 처리)
            for ch_name in missing:
                try:
                    search_resp = youtube.search().list(
                        part="snippet",
                        q=ch_name,
                        type="channel",
                        maxResults=1,
                    ).execute()

                    if not search_resp.get("items"):
                        cache[ch_name] = 0
                        continue

                    channel_id = search_resp["items"][0]["snippet"]["channelId"]
                    ch_resp = youtube.channels().list(
                        part="statistics",
                        id=channel_id,
                    ).execute()

                    if ch_resp.get("items"):
                        sub_count = int(ch_resp["items"][0]["statistics"].get("subscriberCount", 0))
                        cache[ch_name] = sub_count
                    else:
                        cache[ch_name] = 0
                except Exception as e:
                    print(f"[WARN] Failed to fetch subs for '{ch_name}': {e}")
                    cache[ch_name] = 0

            _save_channel_cache(cache)
        except ImportError:
            print("[WARN] googleapiclient not installed, skipping subscriber fetch")
        except Exception as e:
            print(f"[WARN] YouTube API error: {e}")

    elif missing and not YOUTUBE_API_KEY:
        print(f"[WARN] YOUTUBE_API_KEY not set, {len(missing)} channels have no subscriber data")

    return {ch: cache.get(ch, 0) for ch in channel_names}


def extract_features(video: dict, subscriber_count: int = 0) -> dict:
    """영상 메타데이터에서 예측용 피처 추출

    Args:
        video: 영상 메타데이터 딕셔너리
        subscriber_count: 채널 구독자 수 (0이면 미제공)
    """
    title = video.get("title", "")

    # 제목 피처
    title_len = len(title)
    word_count = len(title.split())
    has_emoji = 1 if re.search(r'[\U0001F300-\U0001F9FF]', title) else 0
    has_number = 1 if re.search(r'\d', title) else 0
    caps_ratio = sum(1 for c in title if c.isupper()) / max(len(title), 1)
    has_question = 1 if '?' in title else 0
    has_exclaim = 1 if '!' in title else 0
    has_hashtag = 1 if '#' in title else 0

    # 키워드 피처
    title_lower = title.lower()
    has_korean = 1 if re.search(r'[\uac00-\ud7a3]', title) else 0
    has_how_to = 1 if any(kw in title_lower for kw in ['how to', 'how i', 'tutorial', 'guide', 'recipe']) else 0
    has_challenge = 1 if any(kw in title_lower for kw in ['challenge', 'vs', 'battle', 'test']) else 0
    has_emotional = 1 if any(kw in title_lower for kw in ['amazing', 'insane', 'crazy', 'best', 'worst', 'shocking', 'secret']) else 0
    has_pov = 1 if 'pov' in title_lower else 0
    has_asmr = 1 if 'asmr' in title_lower else 0

    # 컨셉 (one-hot)
    concept = video.get("concept", "Etc")
    concepts = ["Kale Chips", "Smart Farm", "Health Meme", "Looksmaxxing", "Superfood", "K-Food", "Hydroponics"]
    concept_features = {f"concept_{c.lower().replace(' ', '_')}": 1 if concept == c else 0 for c in concepts}

    # 구독자 수 피처 (log scale로 변환, 0이면 0)
    log_subscribers = round(math.log10(subscriber_count + 1), 3)

    features = {
        "title_len": title_len,
        "word_count": word_count,
        "has_emoji": has_emoji,
        "has_number": has_number,
        "caps_ratio": round(caps_ratio, 3),
        "has_question": has_question,
        "has_exclaim": has_exclaim,
        "has_hashtag": has_hashtag,
        "has_korean": has_korean,
        "has_how_to": has_how_to,
        "has_challenge": has_challenge,
        "has_emotional": has_emotional,
        "has_pov": has_pov,
        "has_asmr": has_asmr,
        "log_subscribers": log_subscribers,
        **concept_features,
    }
    return features


def views_to_tier(views: int) -> str:
    """조회수를 등급으로 변환"""
    if views >= 1_000_000:
        return "viral"     # 100만+
    elif views >= 100_000:
        return "high"      # 10만~100만
    elif views >= 10_000:
        return "medium"    # 1만~10만
    else:
        return "low"       # 1만 미만


def tier_to_label(tier: str) -> int:
    return {"low": 0, "medium": 1, "high": 2, "viral": 3}[tier]


def label_to_tier(label: int) -> str:
    return {0: "low", 1: "medium", 2: "high", 3: "viral"}[label]


def train_model():
    """Supabase에서 데이터 가져와서 모델 학습"""
    from supabase import create_client
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score
    import pickle

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    videos = sb.table("videos").select("*").execute().data

    if len(videos) < 20:
        print(f"[SKIP] Not enough data ({len(videos)} videos, need 20+)")
        return None

    # 채널별 구독자 수 조회
    unique_channels = list({v.get("channel", "") for v in videos if v.get("channel")})
    print(f"[SUBS] Fetching subscriber counts for {len(unique_channels)} channels...")
    sub_counts = fetch_subscriber_counts(unique_channels)
    cached_count = sum(1 for c in unique_channels if sub_counts.get(c, 0) > 0)
    print(f"[SUBS] {cached_count}/{len(unique_channels)} channels have subscriber data")

    # 피처 추출
    feature_names = None
    X_list = []
    y_list = []

    for v in videos:
        if v.get("views", 0) == 0:
            continue
        channel = v.get("channel", "")
        subs = sub_counts.get(channel, 0)
        feats = extract_features(v, subscriber_count=subs)
        if feature_names is None:
            feature_names = sorted(feats.keys())
        X_list.append([feats[f] for f in feature_names])
        y_list.append(tier_to_label(views_to_tier(v["views"])))

    X = np.array(X_list)
    y = np.array(y_list)

    print(f"[DATA] {len(X)} videos")
    for tier_name in ["low", "medium", "high", "viral"]:
        count = sum(1 for label in y if label == tier_to_label(tier_name))
        print(f"  {tier_name}: {count}")

    # 학습
    model = GradientBoostingClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42
    )

    # 교차 검증
    if len(X) >= 10:
        scores = cross_val_score(model, X, y, cv=min(5, len(X)//2), scoring="accuracy")
        print(f"[CV] Accuracy: {scores.mean():.2f} (+/- {scores.std():.2f})")

    # 전체 데이터로 학습
    model.fit(X, y)

    # 피처 중요도
    importances = sorted(zip(feature_names, model.feature_importances_), key=lambda x: x[1], reverse=True)
    print("\n[FEATURES] Top 10:")
    for name, imp in importances[:10]:
        print(f"  {name}: {imp:.3f}")

    # 모델 저장
    model_path = Path(__file__).parent / "data" / "model.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_names": feature_names}, f)
    print(f"\n[OK] Model saved: {model_path}")

    return model, feature_names


def predict(title: str, concept: str = "Etc", subscriber_count: int = 0) -> dict:
    """제목과 컨셉으로 조회수 등급 예측

    Args:
        title: 영상 제목
        concept: 컨셉 카테고리
        subscriber_count: 채널 구독자 수 (0이면 모델이 구독자 정보 없이 예측)
    """
    import pickle

    model_path = Path(__file__).parent / "data" / "model.pkl"
    if not model_path.exists():
        return {"error": "Model not trained yet. Run train_model() first."}

    with open(model_path, "rb") as f:
        data = pickle.load(f)

    model = data["model"]
    feature_names = data["feature_names"]

    video = {"title": title, "concept": concept}
    feats = extract_features(video, subscriber_count=subscriber_count)
    X = np.array([[feats[f] for f in feature_names]])

    # 예측
    pred_label = model.predict(X)[0]
    pred_tier = label_to_tier(pred_label)

    # 확률
    proba = model.predict_proba(X)[0]
    tier_proba = {}
    for i, cls in enumerate(model.classes_):
        tier_proba[label_to_tier(cls)] = round(float(proba[i]) * 100, 1)

    # 예상 조회수 범위
    ranges = {
        "low": "~10K",
        "medium": "10K~100K",
        "high": "100K~1M",
        "viral": "1M+",
    }

    return {
        "tier": pred_tier,
        "confidence": round(float(max(proba)) * 100, 1),
        "probabilities": tier_proba,
        "estimated_range": ranges[pred_tier],
    }


if __name__ == "__main__":
    print("=" * 50)
    print("Training view prediction model...")
    print("=" * 50)

    result = train_model()
    if result:
        model, feature_names = result

        # 테스트 예측
        print("\n" + "=" * 50)
        print("Test predictions:")
        print("=" * 50)

        tests = [
            ("How to make crispy kale chips at home", "Kale Chips", 5000),
            ("POV: Your kale is monitored by IoT sensors 24/7", "Smart Farm", 1200),
            ("Average grocery kale vs IoT-grown kale enjoyer", "Looksmaxxing", 50000),
            ("Korean superfood that changed my skin forever", "K-Food", 200000),
            ("Hydroponic farm tour - growing 1000 plants", "Hydroponics", 0),
        ]

        for title, concept, subs in tests:
            result = predict(title, concept, subscriber_count=subs)
            print(f"\n  \"{title}\" (subs: {subs:,})")
            print(f"  Tier: {result['tier']} ({result['confidence']}%)")
            print(f"  Range: {result['estimated_range']}")
            print(f"  Proba: {result['probabilities']}")
