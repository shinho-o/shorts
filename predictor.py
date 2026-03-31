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


def extract_features(video: dict) -> dict:
    """영상 메타데이터에서 예측용 피처 추출"""
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

    # 피처 추출
    feature_names = None
    X_list = []
    y_list = []

    for v in videos:
        if v.get("views", 0) == 0:
            continue
        feats = extract_features(v)
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


def predict(title: str, concept: str = "Etc") -> dict:
    """제목과 컨셉으로 조회수 등급 예측"""
    import pickle

    model_path = Path(__file__).parent / "data" / "model.pkl"
    if not model_path.exists():
        return {"error": "Model not trained yet. Run train_model() first."}

    with open(model_path, "rb") as f:
        data = pickle.load(f)

    model = data["model"]
    feature_names = data["feature_names"]

    video = {"title": title, "concept": concept}
    feats = extract_features(video)
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
            ("How to make crispy kale chips at home", "Kale Chips"),
            ("POV: Your kale is monitored by IoT sensors 24/7", "Smart Farm"),
            ("Average grocery kale vs IoT-grown kale enjoyer", "Looksmaxxing"),
            ("Korean superfood that changed my skin forever", "K-Food"),
            ("Hydroponic farm tour - growing 1000 plants", "Hydroponics"),
        ]

        for title, concept in tests:
            result = predict(title, concept)
            print(f"\n  \"{title}\"")
            print(f"  Tier: {result['tier']} ({result['confidence']}%)")
            print(f"  Range: {result['estimated_range']}")
            print(f"  Proba: {result['probabilities']}")
