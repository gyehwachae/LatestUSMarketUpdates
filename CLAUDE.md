# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

자동화된 미국 주식 시장 뉴스 → 한국어 X(트위터) + YouTube Shorts 동시 발행 파이프라인.
Finnhub에서 최신 뉴스 수집 → DeepL 번역 → Gemini가 종목 추출·중요도 점수·X 트윗 문구 생성 → 모든 뉴스를 X에 발행, 중요도 7 이상만 영상 제작 후 YouTube 업로드.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# .env에 API 키 입력 (아래 Key Constraints 참고)
```

YouTube 첫 실행 시 브라우저 OAuth 인증 → `token.json` 자동 저장됨.

## Commands

```bash
python main.py         # 1회 실행
python main.py --loop  # 5분마다 자동 반복
```

## Architecture

```
main.py                  # 오케스트레이터: 모든 뉴스→X 발행, 고중요도→YouTube
config.py                # 환경변수 및 상수
modules/
  news_collector.py      # Finnhub market-news 폴링, 중복 제거 (data/processed_news.json)
  translator.py          # DeepL Free API
  analyzer.py            # Gemini 1.5 Flash → {tickers, companies, summary, impact, reason,
                         #   importance_score(1~10), script, x_post}
  video_maker.py         # gTTS + MoviePy + Pillow → 1080x1920 mp4
  uploader.py            # YouTube Data API v3, 일일 카운터 (data/upload_count.json)
  x_publisher.py         # Tweepy v2 → X(트위터) 발행, YouTube URL 첨부 가능
output/videos/           # 생성된 영상
data/                    # processed_news.json, upload_count.json
assets/                  # 임시 이미지/오디오 (처리 후 자동 삭제)
```

## Key Constraints

| 서비스 | 한도 | 설정값 |
|--------|------|--------|
| YouTube API | 하루 10,000 유닛 (업로드 1건 ≈ 1,600유닛 → 최대 6건) | `MAX_YOUTUBE_UPLOADS_PER_DAY=6` |
| YouTube 업로드 조건 | Gemini `importance_score` ≥ 기준값 | `YOUTUBE_MIN_IMPORTANCE=7` (기본) |
| X Free Tier | 월 1,500 트윗 (하루 약 50건) | 트윗 280자 이내 자동 truncate |
| DeepL Free | 월 50만 자 | — |
| Gemini 응답 | 반드시 JSON | `analyzer.py`에서 ```json 블록 파싱 처리 포함 |
| 뉴스 수집 | 한 번에 최대 5건 | API 쿼터 보호 |

## importance_score 기준 (Gemini 판단)

- 9~10: Fed/금리/CPI 등 매크로 지표
- 8~9: 어닝서프라이즈 / 가이던스 상·하향
- 7~8: M&A / 대형 계약
- 6~7: 경영진 교체 / 소송
- 1~5: 일반 분석 / 의견 기사

## News Category

`.env`의 `NEWS_CATEGORY`: `general` | `forex` | `crypto` | `merger`
