# Farmetry Meme Agent

## 개요
Reddit에서 밈 트렌드를 자동 수집하고 AI로 분석해서 Farmetry 릴스 콘텐츠 아이디어를 매일 자동 생성하는 에이전트.

## 목표
- 미국 헬스/밈 커뮤니티 트렌드 자동 수집
- Farmetry 브랜드 메시지와 연결 가능한 콘텐츠 아이디어 자동 생성
- 크라우드펀딩 트래픽 유도용 숏폼 콘텐츠 기획 자동화

---

## 파이프라인

```
매일 오전 9시 (크론잡)
        ↓
Reddit 크롤링 (7개 서브레딧, 상위 30개 포스트)
        ↓
Gemini Flash API로 관련성 분석
        ↓
Farmetry 콘텐츠 아이디어 3개 생성 (JSON)
        ↓
results_YYYYMMDD.json 저장
        ↓
(선택) Notion DB 저장
(선택) 카카오톡 알림
```

---

## 기술 스택

| 역할 | 도구 |
|---|---|
| 크롤링 | PRAW (Reddit API) |
| AI 분석 | Gemini 1.5 Flash (무료 tier) |
| 자동화 | crontab (라즈베리파이) |
| 저장 | JSON 파일 + Notion (선택) |
| 알림 | 카카오톡 API (선택) |

---

## 수집 서브레딧

- r/memes
- r/gymmemes
- r/HealthyFood
- r/looksmaxxing
- r/hydroponics
- r/veganfitness
- r/kpop

---

## 타겟 밈 포맷

- Average X enjoyer vs Average Y enjoyer
- Looksmaxxing 루틴 카드
- POV 시리즈
- Expectation vs Reality
- Before/After

---

## Farmetry 연결 키워드

- IoT 센서가 케일을 24/7 모니터링
- pH · 온도 · 습도 · 조도 · EC 센서
- 무농약, 최적화된 영양소
- Korean tech + superfood
- 케일칩 = 과자처럼 맛있음
- "Korean IoT tech meets superfood culture"

---

## 콘텐츠 아이디어 예시

### 1. Average kale eater vs Average Farmetry eater
- 포맷: Average X enjoyer vs Y enjoyer
- BGM: Gigachad Theme
- 슬라이드:
  1. Average kale eater — 마트 케일 억지로 씹음 / 영양소 모름 / 맛없어서 포기
  2. Average Farmetry eater — IoT 센서가 키운 케일칩 / 실시간 모니터링 / 과자처럼 뜯음
  3. "5 sensors. 0 pesticides. 1 glow up." + 크라우드펀딩 CTA
- 해시태그: #looksmaxxing #kale #averageenjoyervs #koreantech #healthtok #fyp #smartfarm

### 2. The looksmaxxing routine nobody talks about
- 포맷: Looksmaxxing 루틴 카드
- BGM: Phonk TRUCK
- 슬라이드:
  1. ✅ 8시간 수면 ✅ 턱 운동 ✅ 수분 섭취 ✅ IoT-grown kale chips 🇰🇷
  2. "Korean tech did what the gym couldn't / 5 sensors monitor every leaf 24/7"
  3. "bro trusted the farm science" + Farmetry CTA
- 해시태그: #looksmaxxing #glowup #kale #koreantech #iotfarm #fitfood #fyp

### 3. POV: 너 케일임. 센서 5개가 24시간 감시 중
- 포맷: POV 시리즈
- BGM: Evil Morty Theme
- 슬라이드:
  1. "POV: you're a kale plant at a Farmetry smart farm"
  2. 센서 목록 나열 (👁 pH / 🌡 temp / 💧 humidity / ☀️ light / 📡 EC)
  3. "no pesticides. no stress. just science." + CTA
- 해시태그: #pov #smartfarm #iotfarm #kale #koreantech #hydroponics #fyp

---

## 음악 추천

| 분위기 | 곡 |
|---|---|
| Average enjoyer 밈 | Gigachad Theme |
| Looksmaxxing | Phonk TRUCK |
| 코믹/시네마틱 | Evil Morty Theme (For the Damaged Coda) |
| K-culture | NewJeans - Hype Boy (instrumental) |
| 장난스러움 | Monkeys Spinning Monkeys |

---

## 해시태그 세트

**Looksmaxxing 포맷**
```
#looksmaxxing #looksmax #glowup #kale #healthysnacks #cleaneating #smartfarm #iotfarm #koreantech #farmetry #kalechips
```

**Average enjoyer 포맷**
```
#averageenjoyervs #meme #fyp #kale #superfood #healthtok #koreanfood #kculture #startup #crowdfunding #farmetry
```

**교육/신뢰 포맷**
```
#hydroponics #verticalfarm #sustainablefood #iotfarm #smartfarming #sciencetok #healthyfood #eatclean #farmetry
```

> TikTok: 3~5개 / Instagram: 10~15개

---

## 파일 구조

```
farmetry-agent/
├── agent.py          # 메인 에이전트 (수집 + 분석 + 저장)
├── scheduler.py      # 매일 9시 자동 실행
├── requirements.txt  # 의존성
├── .env.example      # 환경변수 템플릿
└── results_YYYYMMDD.json  # 일별 결과 자동 저장
```

---

## 환경변수

```env
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=farmetry-agent/1.0
GEMINI_API_KEY=...         # aistudio.google.com 무료 발급
NOTION_TOKEN=...           # 선택
NOTION_DATABASE_ID=...     # 선택
KAKAO_TOKEN=...            # 선택
```

---

## 라즈베리파이 배포

```bash
# 파일 전송
scp -r ~/farmetry-agent pi@[라즈베리파이IP]:/home/pi/

# 설치
cd ~/farmetry-agent
pip3 install -r requirements.txt
cp .env.example .env && nano .env

# 테스트
python3 agent.py

# 크론잡 등록 (매일 오전 9시)
crontab -e
# 아래 추가:
0 9 * * * cd /home/pi/farmetry-agent && python3 agent.py
```

---

## TODO

- [ ] Reddit API 키 발급
- [ ] Gemini API 키 발급 (aistudio.google.com)
- [ ] `.env` 파일 세팅
- [ ] 라즈베리파이에 배포
- [ ] Notion DB 연동 (선택)
- [ ] 카카오톡 알림 연동 (선택)
- [ ] 결과 기반 실제 Canva 슬라이드 제작
