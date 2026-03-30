# Farmetry Shorts 자동화 로드맵

## 최종 목표
**트렌드 수집 → 조회수 예측 → 스크립트 생성 → 쇼츠 영상 자동 생성**

---

## Phase 1: 데이터 축적 + 패턴 분석 (현재~2주)

### 1-1. 수집 데이터 확대
- [x] YouTube Shorts 수집 (제목, 조회수, 좋아요, 댓글, 채널, 게시일)
- [x] Google Trends 키워드 수집
- [x] 수집 키워드 관리 (대시보드에서 추가/삭제/토글)
- [ ] 수집 자동화 — 매일 1회 자동 수집 (Render Cron Job 또는 GitHub Actions)
- [ ] 수집 범위 확대 — 키워드당 10~20개, 조회수순 + 최신순 동시 수집
- [ ] 영상 설명(description), 태그, 영상 길이 추가 수집
- [ ] 시간에 따른 조회수 변화 추적 (같은 영상 반복 수집 → 성장률 계산)

### 1-2. 데이터 라벨링
- [ ] 대시보드에서 영상 평가 기능 추가 (1~5점 또는 "바이럴 가능성" 태그)
- [ ] 참고할 만한 영상 북마크 기능
- [ ] 영상별 메모/분석 노트 추가

**목표: 500+ 영상 데이터 축적**

---

## Phase 2: 조회수 예측 모델 (2~4주)

### 2-1. Feature Engineering
- 제목 길이, 이모지 수, 대문자 비율
- 해시태그 수, 인기 해시태그 포함 여부
- 채널 구독자 수, 평균 조회수
- 게시 요일/시간대
- 컨셉 카테고리 (Kale Chips, Looksmaxxing 등)
- 제목 키워드 임베딩 (sentence-transformers)

### 2-2. 모델 학습
- 기본: XGBoost/LightGBM으로 조회수 구간 예측 (Low/Mid/High/Viral)
- 고급: 제목 텍스트 → 조회수 예측 regression
- 검증: 새로 수집된 영상으로 정확도 측정

### 2-3. 대시보드 연동
- 아이디어 생성 시 예측 점수 자동 표시
- "이 제목으로 올리면 예상 조회수 XX만" 표시
- 제목 수정 → 실시간 예측 점수 변화

---

## Phase 3: 스크립트 자동 생성 (4~6주)

### 3-1. 스크립트 구조
```
{
  "title": "릴스 제목",
  "hook": "0-2초 후킹 텍스트",
  "slides": [
    {"text": "자막 텍스트", "duration": 3, "visual": "설명"},
    ...
  ],
  "cta": "마무리 CTA",
  "bgm": "추천 BGM",
  "total_duration": 15,
  "predicted_views": 50000
}
```

### 3-2. 구현
- Claude API로 트렌드 + 예측 모델 기반 최적 스크립트 생성
- 포맷별 템플릿 (POV, Average enjoyer, Before/After 등)
- 예측 점수가 높은 조합을 자동 선택

---

## Phase 4: 쇼츠 영상 자동 생성 (6~10주)

### 4-1. 에셋 파이프라인
- 텍스트 → 이미지 생성 (DALL-E 3 / Flux)
- TTS 음성 생성 (ElevenLabs / Google TTS)
- BGM 라이브러리 (저작권 무료)
- 자막 스타일 템플릿

### 4-2. 영상 렌더링
- **Option A**: ffmpeg + Python (가볍고 빠름)
- **Option B**: Remotion (React 기반, 디자인 자유도 높음)
- **Option C**: Creatomate API (클라우드 렌더링, 비용 발생)

### 4-3. 워크플로우
```
트렌드 수집
    ↓
예측 모델로 최적 콘텐츠 선택
    ↓
스크립트 자동 생성
    ↓
이미지/TTS/자막 생성
    ↓
영상 렌더링 (9:16, 15~30초)
    ↓
대시보드에서 미리보기 + 승인
    ↓
(Phase 5) 자동 업로드
```

---

## Phase 5: 배포 + 최적화 (10주~)

### 5-1. 자동 업로드
- YouTube Shorts API로 자동 업로드
- TikTok / Instagram Reels API 연동
- 업로드 스케줄링 (최적 시간대)

### 5-2. 성과 추적 + 피드백 루프
- 업로드한 영상의 실제 조회수/좋아요 수집
- 예측 vs 실제 비교 → 모델 재학습
- A/B 테스트: 같은 콘텐츠 다른 제목/썸네일

### 5-3. 자동화 완성
```
매일 자동:
09:00  트렌드 수집
09:05  예측 모델 분석
09:10  스크립트 3개 생성
09:15  영상 렌더링
09:20  대시보드에서 알림 → 승인 대기
승인 후  → 자동 업로드 + 성과 추적
```

---

## 기술 스택 요약

| 역할 | 도구 |
|---|---|
| 데이터 수집 | YouTube API, Google Trends (pytrends) |
| DB | Supabase (PostgreSQL) |
| AI 분석 | Claude API (Anthropic) |
| 예측 모델 | scikit-learn / XGBoost + sentence-transformers |
| 이미지 생성 | DALL-E 3 / Flux |
| TTS | ElevenLabs / Google Cloud TTS |
| 영상 렌더링 | ffmpeg (Python) |
| 대시보드 | Flask + Render |
| 스케줄링 | GitHub Actions / Render Cron |
| 업로드 | YouTube Data API / TikTok API |

---

## 현재 진행 상황

- **Phase 1**: 80% (수집 + 대시보드 완성, 자동화/확대 필요)
- **Phase 2**: 0% (데이터 축적 후 시작)
- **Phase 3**: 0%
- **Phase 4**: 0%
- **Phase 5**: 0%

## 다음 할 일
1. 수집 자동화 (매일 1회)
2. 영상 데이터 500개 이상 축적
3. 조회수 예측 모델 v1 구현
