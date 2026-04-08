# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

자동화된 미국 주식 시장 뉴스 → 한국어 YouTube Shorts 발행 파이프라인.
Finnhub에서 최신 뉴스 수집 → 기사 본문 스크래핑 → DeepL 헤드라인 번역 → Groq(Llama 3.3 70B)가 종목 추출·중요도 점수·60초 Shorts용 나레이션 생성 → 중요도 7 이상만 영상 제작 후 YouTube 업로드.

## Commands

```bash
# 개발/테스트
python main.py              # 1회 실행 (최대 5건 처리)
python test_pipeline.py     # 파이프라인 전체 테스트 (영상 제작 + 업로드 포함)

# 종목 모멘텀 분석
python analyze_stock.py AAPL                # 단일 종목 분석 + 업로드
python analyze_stock.py AAPL --no-upload    # 영상만 생성 (테스트용)
python analyze_stock.py AAPL NVDA TSLA      # 여러 종목 일괄 분석

# 프로덕션 (백그라운드 데몬)
./start.sh                  # 루프 모드 시작 (KST 시간대별 자동 폴링 간격)
./stop.sh                   # 중지
./restart.sh                # 재시작

# 크론 1회 실행 (crontab용)
./cron_run.sh               # venv 활성화 + 로그 기록
```

## Architecture

파이프라인 흐름:
```
Finnhub API → article_scraper(본문추출) → translator(DeepL) → analyzer(Groq)
                                                                    ↓
                                           ← video_maker ← generate_narration
                                                    ↓
                                               uploader(YouTube)
```

핵심 모듈:
- `main.py`: 오케스트레이터. KST 시간대별 폴링 간격 자동 조절 (아침 1분, 정규장 10분, 낮 30분)
- `modules/analyzer.py`: Groq REST API 직접 호출. 분석 JSON + 60초 Shorts용 나레이션(300~350자) 1회 호출로 생성
- `modules/video_maker.py`: edge-tts 문장별 TTS → 자막 타이밍 추출 → Pillow 프레임 렌더링 → ffmpeg 인코딩
- `modules/chart_maker.py`: yfinance로 5일 1시간봉 → Pillow로 차트 애니메이션 프레임 생성
- `modules/article_scraper.py`: trafilatura(1차) → BeautifulSoup(fallback)으로 기사 본문 추출
- `modules/daily_briefing.py`: 매일 아침 증시 브리핑 생성. Twelve Data(우선) → yfinance(fallback)로 지수/종목 수집
- `modules/stock_analyzer.py`: 개별 종목 모멘텀 분석 (기술적 지표 + 펀더멘털 + AI 분석)
- `modules/video_maker_stock.py`: 종목 분석 전용 영상 레이아웃

데이터 파일:
- `data/processed_news.json`: 처리 완료된 기사 ID 목록 (중복 방지)
- `data/upload_count.json`: 일일 YouTube 업로드 카운터
- `token.json`: YouTube OAuth 토큰 (첫 실행 시 브라우저 인증 필요)

## Key Constraints

| 서비스 | 한도 | 설정값 |
|--------|------|--------|
| Groq API | 하루 14,400회 (무료) | 429 시 30초씩 대기 후 최대 3회 재시도 |
| YouTube API | 하루 10,000 유닛 (업로드 1건 ≈ 1,600유닛) | `MAX_YOUTUBE_UPLOADS_PER_DAY=6` |
| YouTube 업로드 조건 | `importance_score` ≥ 기준값 | `YOUTUBE_MIN_IMPORTANCE=7` (기본) |
| DeepL Free | 월 50만 자 | 헤드라인만 번역 (본문은 Groq가 직접 처리) |
| Twelve Data | 하루 800회 (무료) | 기술적 데이터 수집 (가격, MA, RSI) |
| FMP (Financial Modeling Prep) | 하루 250회 (무료) | 펀더멘털 데이터 (PE, PEG, 마진, FCF) |
| 뉴스 수집 | 한 번에 최대 5건 | API 쿼터 보호 |
| 기사 본문 | 최대 4,000자 | `article_scraper.py`에서 truncate |

## importance_score 기준

- 9~10: Fed/금리/CPI 등 매크로 지표
- 8~9: 어닝서프라이즈 / 가이던스 상·하향
- 7~8: M&A / 대형 계약
- 6~7: 경영진 교체 / 소송
- 1~5: 일반 분석 / 의견 기사

## 종목 모멘텀 분석 (`analyze_stock.py`)

핵심 원칙: **"예측이 아닌 대응"** - 거래대금이 센 곳에서 실적 우량주를 기술적 추세에 맞춰 분석

### 기술적 지표
| 지표 | 기준 | 설명 |
|------|------|------|
| MA 정배열 | 주가 > 50일선 > 200일선 | 상승 추세 확인 |
| RSI | 50~70: 강세, 70~80: 과열 주의 | 과매수 구간 진입 자제 |
| 이격도 | 50일선 대비 ±15% 이상 주의 | 급등 후 조정 가능성 |
| 베타 | >1.5 고위험, <0.5 방어적 | 하락장 변동성 위험 |

### 펀더멘털 지표
| 지표 | 기준 | 설명 |
|------|------|------|
| PEG | <1.0 저평가, >2.0 고평가 | 성장률 대비 밸류에이션 |
| Rule of 40 | 매출성장률 + 영업이익률 ≥ 40% | 플랫폼/SaaS 기업 건전성 |
| FCF | 양수이며 증가 추세 | 실질 현금 창출력 |
| ROIC | >15% 양호 | 경제적 해자 가능성 |

### 시장 환경
| 지표 | 기준 | 설명 |
|------|------|------|
| VIX | <20 정상, >30 공포 | 급등 후 꺾임 = 매수 기회 |
| Fear & Greed | ≥75 탐욕 (리스크 관리) | ≤25 공포 (매수 기회) |

### 리스크 관리 규칙
- **손절 라인**: 50일선 이탈 시 기계적 대응
- **비중 조절**: 시장 과열 시 현금 비중 확대

## Environment Variables

`.env` 필수 키: `FINNHUB_API_KEY`, `DEEPL_API_KEY`, `GROQ_API_KEY`
YouTube: `client_secrets.json` 파일 필요 (Google Cloud Console에서 OAuth 2.0 클라이언트 생성)
선택: `NEWS_CATEGORY` (`general` | `forex` | `crypto` | `merger`), `YOUTUBE_MIN_IMPORTANCE`

### 데일리 브리핑용 (권장)
- `TWELVEDATA_API_KEY`: 지수/종목 데이터 수집 (twelvedata.com, 무료 800회/일)
  - 미설정 시 yfinance fallback (Rate Limit 발생 가능)
