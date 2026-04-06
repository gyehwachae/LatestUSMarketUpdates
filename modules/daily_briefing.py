"""
매일 오전 데일리 마켓 브리핑 영상 생성
- 주요 증시 현황 (S&P 500, 나스닥, 다우, 러셀)
- TOP 5 거래 종목 (상승/하락)
- 오늘의 주요 이벤트
"""
import os
from datetime import datetime, timedelta

import exchange_calendars as xcals
import pytz
import yfinance as yf
import requests

from config import GROQ_API_KEY, TWELVEDATA_API_KEY


# Twelve Data용 지수 매핑 (ETF 사용 - 더 안정적)
TWELVEDATA_INDICES = {
    "SPY": {"name": "S&P 500", "tts_name": "에스앤피 500", "yf_ticker": "^GSPC"},
    "QQQ": {"name": "나스닥", "tts_name": "나스닥", "yf_ticker": "^IXIC"},
    "DIA": {"name": "다우존스", "tts_name": "다우존스", "yf_ticker": "^DJI"},
    "IWM": {"name": "러셀 2000", "tts_name": "러셀 2000", "yf_ticker": "^RUT"},
    "VXX": {"name": "VIX 지수", "tts_name": "빅스 지수", "yf_ticker": "^VIX"},
}

# 주요 지수 티커 (TTS용 한글 발음 포함) - yfinance fallback용
INDICES = {
    "^GSPC": {"name": "S&P 500", "tts_name": "에스앤피 500"},
    "^IXIC": {"name": "나스닥", "tts_name": "나스닥"},
    "^DJI": {"name": "다우존스", "tts_name": "다우존스"},
    "^RUT": {"name": "러셀 2000", "tts_name": "러셀 2000"},
    "^VIX": {"name": "VIX 지수", "tts_name": "빅스 지수"},
}

# 주요 종목 회사명 매핑 (TTS용)
COMPANY_NAMES = {
    "AAPL": "애플", "MSFT": "마이크로소프트", "GOOGL": "구글", "AMZN": "아마존",
    "NVDA": "엔비디아", "META": "메타", "TSLA": "테슬라", "BRK-B": "버크셔해서웨이",
    "JPM": "제이피모건", "V": "비자", "JNJ": "존슨앤존슨", "WMT": "월마트",
    "MA": "마스터카드", "PG": "피앤지", "HD": "홈디포", "CVX": "셰브론",
    "MRK": "머크", "ABBV": "애브비", "KO": "코카콜라", "PEP": "펩시코",
    "COST": "코스트코", "TMO": "써모피셔", "AVGO": "브로드컴", "MCD": "맥도날드",
    "CSCO": "시스코", "ACN": "액센츄어", "ABT": "애보트", "NKE": "나이키",
    "CRM": "세일즈포스", "AMD": "에이엠디", "INTC": "인텔", "NFLX": "넷플릭스",
    "ADBE": "어도비", "ORCL": "오라클", "BA": "보잉", "GE": "제너럴일렉트릭",
    "XOM": "엑슨모빌", "COP": "코노코필립스", "DIS": "디즈니", "PYPL": "페이팔",
}

# 주요 대형주 (거래량 체크용)
MAJOR_STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
    "JPM", "V", "JNJ", "WMT", "MA", "PG", "HD", "CVX", "MRK", "ABBV",
    "KO", "PEP", "COST", "TMO", "AVGO", "MCD", "CSCO", "ACN", "ABT",
    "NKE", "CRM", "AMD", "INTC", "NFLX", "ADBE", "ORCL", "BA", "GE"
]

# NYSE 캘린더 (exchange_calendars)
_nyse_calendar = None


def _get_nyse_calendar():
    """NYSE 캘린더 싱글톤"""
    global _nyse_calendar
    if _nyse_calendar is None:
        _nyse_calendar = xcals.get_calendar("XNYS")
    return _nyse_calendar


def was_us_market_open_yesterday() -> bool:
    """어제 미국 장이 열렸는지 확인 (KST 기준 오늘 아침 → 미국 전날)"""
    # 미국 동부 시간 기준 어제 날짜
    et = pytz.timezone("America/New_York")
    now_et = datetime.now(et)
    yesterday_et = (now_et - timedelta(days=1)).date()

    # exchange_calendars로 거래일 여부 확인
    nyse = _get_nyse_calendar()
    is_trading_day = nyse.is_session(yesterday_et)

    if not is_trading_day:
        print(f"  [--] 어제({yesterday_et})는 NYSE 휴장일")
        return False

    print(f"  [OK] 어제({yesterday_et})는 NYSE 거래일")
    return True


# ============ Twelve Data API 함수 ============

def fetch_index_data_twelvedata() -> list[dict]:
    """Twelve Data API로 주요 지수 데이터 수집 (배치 요청)"""
    if not TWELVEDATA_API_KEY:
        print("  [!!] TWELVEDATA_API_KEY 미설정")
        return []

    results = []
    symbols = ",".join(TWELVEDATA_INDICES.keys())

    try:
        url = "https://api.twelvedata.com/quote"
        params = {
            "symbol": symbols,
            "apikey": TWELVEDATA_API_KEY,
        }
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        for ticker, info in TWELVEDATA_INDICES.items():
            try:
                quote = data.get(ticker, {})
                if quote and "percent_change" in quote:
                    change_pct = float(quote["percent_change"])
                    price = float(quote["close"])
                    change = float(quote.get("change", 0))

                    results.append({
                        "ticker": info["yf_ticker"],
                        "name": info["name"],
                        "tts_name": info["tts_name"],
                        "price": price,
                        "change": change,
                        "change_pct": change_pct,
                    })
            except (KeyError, ValueError, TypeError) as e:
                print(f"  [!!] 지수 파싱 실패 ({ticker}): {e}")
                continue

    except Exception as e:
        print(f"  [!!] Twelve Data API 실패: {e}")

    return results


def fetch_top_movers_twelvedata() -> tuple[list[dict], list[dict]]:
    """Twelve Data API로 상승/하락 종목 수집 (무료 플랜: 분당 8크레딧)"""
    import time as time_module

    if not TWELVEDATA_API_KEY:
        print("  [!!] TWELVEDATA_API_KEY 미설정")
        return [], []

    movers = []
    # 상위 16개 종목만 사용 (2배치 = 약 1분, 분당 8크레딧 제한)
    stocks_to_fetch = MAJOR_STOCKS[:16]
    batch_size = 8
    batches = [stocks_to_fetch[i:i+batch_size] for i in range(0, len(stocks_to_fetch), batch_size)]

    for idx, batch in enumerate(batches):
        symbols = ",".join(batch)

        try:
            url = "https://api.twelvedata.com/quote"
            params = {
                "symbol": symbols,
                "apikey": TWELVEDATA_API_KEY,
            }
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            # API 에러 체크 (Rate limit)
            if "code" in data and data.get("code") == 429:
                print(f"  [..] Rate limit - 61초 대기 후 재시도...")
                time_module.sleep(61)
                r = requests.get(url, params=params, timeout=30)
                data = r.json()

            for ticker in batch:
                try:
                    quote = data.get(ticker, {})
                    if quote and "percent_change" in quote:
                        change_pct = float(quote["percent_change"])
                        price = float(quote["close"])
                        tts_name = COMPANY_NAMES.get(ticker, ticker)

                        movers.append({
                            "ticker": ticker,
                            "name": ticker,
                            "tts_name": tts_name,
                            "price": price,
                            "change_pct": change_pct,
                        })
                except (KeyError, ValueError, TypeError):
                    continue

        except Exception as e:
            print(f"  [!!] Twelve Data 종목 배치 실패: {e}")
            continue

        # 다음 배치 전 대기 (분당 8크레딧 제한 준수)
        if idx < len(batches) - 1:
            time_module.sleep(61)

    # 상승/하락 정렬
    sorted_movers = sorted(movers, key=lambda x: x["change_pct"], reverse=True)
    top_gainers = sorted_movers[:5]
    top_losers = sorted_movers[-5:][::-1]

    return top_gainers, top_losers


# ============ yfinance fallback 함수 ============

def fetch_index_data_yfinance() -> list[dict]:
    """yfinance로 주요 지수 데이터 수집 (fallback)"""
    import time as time_module
    results = []

    for ticker, info in INDICES.items():
        for attempt in range(3):  # 최대 3회 재시도
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="2d")

                if len(hist) >= 2:
                    prev_close = hist["Close"].iloc[-2]
                    current = hist["Close"].iloc[-1]
                    change = current - prev_close
                    change_pct = (change / prev_close) * 100

                    results.append({
                        "ticker": ticker,
                        "name": info["name"],
                        "tts_name": info["tts_name"],
                        "price": current,
                        "change": change,
                        "change_pct": change_pct,
                    })
                break  # 성공 시 루프 탈출
            except Exception as e:
                if "Too Many Requests" in str(e) or "Rate" in str(e):
                    if attempt < 2:
                        print(f"  [..] 지수 {ticker} 재시도 ({attempt+1}/3)...")
                        time_module.sleep(10 + attempt * 5)  # 10초, 15초, 20초 대기
                        continue
                print(f"  [!!] 지수 데이터 실패 ({ticker}): {e}")
                break

        time_module.sleep(3)  # 요청 간 딜레이 (3초)

    return results


def fetch_top_movers_yfinance() -> tuple[list[dict], list[dict]]:
    """yfinance로 상승/하락 TOP 5 종목 수집 (fallback)"""
    import time as time_module
    movers = []

    # 배치로 한 번에 다운로드 (Rate Limit 방지)
    try:
        tickers_str = " ".join(MAJOR_STOCKS)
        data = yf.download(tickers_str, period="2d", group_by="ticker", progress=False, threads=False)

        for ticker in MAJOR_STOCKS:
            try:
                if ticker in data.columns.get_level_values(0):
                    ticker_data = data[ticker]
                    if len(ticker_data) >= 2 and not ticker_data["Close"].isna().all():
                        prev_close = ticker_data["Close"].iloc[-2]
                        current = ticker_data["Close"].iloc[-1]
                        if prev_close > 0:
                            change_pct = ((current - prev_close) / prev_close) * 100
                            tts_name = COMPANY_NAMES.get(ticker, ticker)

                            movers.append({
                                "ticker": ticker,
                                "name": ticker,
                                "tts_name": tts_name,
                                "price": current,
                                "change_pct": change_pct,
                            })
            except Exception:
                continue
    except Exception as e:
        print(f"  [!!] 종목 배치 다운로드 실패: {e}")
        # Fallback: 개별 다운로드
        for ticker in MAJOR_STOCKS[:10]:  # Rate limit 방지 위해 10개만
            for attempt in range(2):
                try:
                    stock = yf.Ticker(ticker)
                    hist = stock.history(period="2d")

                    if len(hist) >= 2:
                        prev_close = hist["Close"].iloc[-2]
                        current = hist["Close"].iloc[-1]
                        change_pct = ((current - prev_close) / prev_close) * 100
                        tts_name = COMPANY_NAMES.get(ticker, ticker)

                        movers.append({
                            "ticker": ticker,
                            "name": ticker,
                            "tts_name": tts_name,
                            "price": current,
                            "change_pct": change_pct,
                        })
                    break
                except Exception:
                    if attempt == 0:
                        time_module.sleep(10)  # 재시도 시 10초 대기
                    continue
            time_module.sleep(3)  # 요청 간 3초 대기

    # 상승/하락 정렬
    sorted_movers = sorted(movers, key=lambda x: x["change_pct"], reverse=True)
    top_gainers = sorted_movers[:5]
    top_losers = sorted_movers[-5:][::-1]  # 하락폭 큰 순

    return top_gainers, top_losers


# ============ 메인 함수 (Twelve Data 우선, yfinance fallback) ============

def fetch_index_data() -> list[dict]:
    """주요 지수 데이터 수집 (Twelve Data 우선, yfinance fallback)"""
    # Twelve Data 시도
    if TWELVEDATA_API_KEY:
        results = fetch_index_data_twelvedata()
        if len(results) >= 2:
            print(f"  [OK] Twelve Data: 지수 {len(results)}개 수집")
            return results
        print("  [..] Twelve Data 실패, yfinance fallback...")

    # yfinance fallback
    return fetch_index_data_yfinance()


def fetch_top_movers() -> tuple[list[dict], list[dict]]:
    """상승/하락 TOP 5 종목 수집 (Twelve Data 우선, yfinance fallback)"""
    # Twelve Data 시도
    if TWELVEDATA_API_KEY:
        gainers, losers = fetch_top_movers_twelvedata()
        if len(gainers) >= 3 or len(losers) >= 3:
            print(f"  [OK] Twelve Data: 상승 {len(gainers)}개, 하락 {len(losers)}개")
            return gainers, losers
        print("  [..] Twelve Data 실패, yfinance fallback...")

    # yfinance fallback
    return fetch_top_movers_yfinance()


def fetch_economic_events() -> list[dict]:
    """오늘의 경제 이벤트 (Finnhub economic calendar)"""
    from config import FINNHUB_API_KEY

    events = []
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        url = f"https://finnhub.io/api/v1/calendar/economic"
        params = {"from": today, "to": today, "token": FINNHUB_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        for event in data.get("economicCalendar", [])[:5]:
            events.append({
                "time": event.get("time", ""),
                "event": event.get("event", ""),
                "country": event.get("country", ""),
                "impact": event.get("impact", ""),
            })
    except Exception as e:
        print(f"  [!!] 경제 이벤트 수집 실패: {e}")

    return events


def fetch_earnings_today() -> list[dict]:
    """오늘 실적 발표 예정 기업"""
    from config import FINNHUB_API_KEY

    earnings = []
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        url = f"https://finnhub.io/api/v1/calendar/earnings"
        params = {"from": today, "to": today, "token": FINNHUB_API_KEY}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        for item in data.get("earningsCalendar", [])[:5]:
            earnings.append({
                "ticker": item.get("symbol", ""),
                "time": item.get("hour", ""),  # bmo (before market open) / amc (after market close)
            })
    except Exception as e:
        print(f"  [!!] 실적 일정 수집 실패: {e}")

    return earnings


def generate_briefing_script(indices: list, gainers: list, losers: list,
                             events: list, earnings: list) -> str:
    """Groq로 데일리 브리핑 나레이션 생성"""

    # 데이터 요약 텍스트 생성 (TTS용 한글 이름 사용)
    index_summary = ""
    for idx in indices:
        direction = "상승" if idx["change_pct"] > 0 else "하락"
        tts_name = idx.get("tts_name", idx["name"])
        index_summary += f"- {tts_name}: {idx['price']:,.0f}포인트 ({idx['change_pct']:+.2f}% {direction})\n"

    # 회사명으로 표시 (티커 대신)
    gainer_summary = ""
    for g in gainers[:3]:
        company = g.get("tts_name", g["ticker"])
        gainer_summary += f"- {company}: {g['change_pct']:+.2f}%\n"

    loser_summary = ""
    for l in losers[:3]:
        company = l.get("tts_name", l["ticker"])
        loser_summary += f"- {company}: {l['change_pct']:+.2f}%\n"

    event_summary = ""
    for e in events[:3]:
        event_summary += f"- {e['event']} ({e['country']})\n"

    # 실적 발표도 회사명으로
    earning_summary = ""
    for er in earnings[:3]:
        time_str = "장전" if er["time"] == "bmo" else "장후"
        company = COMPANY_NAMES.get(er["ticker"], er["ticker"])
        earning_summary += f"- {company} ({time_str})\n"

    prompt = f"""당신은 한국 뉴스 앵커입니다. 미국 증시 데일리 브리핑을 전달합니다.
아래 데이터를 바탕으로 60초 분량의 나레이션을 작성하세요.

[어제 미국 증시 마감]
{index_summary}

[상승 TOP 3]
{gainer_summary}

[하락 TOP 3]
{loser_summary}

[오늘 주요 경제 이벤트]
{event_summary if event_summary else "주요 이벤트 없음"}

[오늘 실적 발표]
{earning_summary if earning_summary else "주요 실적 발표 없음"}

규칙:
1. 280~320자로 작성
2. 구성: 인사 → 증시 핵심 요약 → 주목 종목 → 마무리
3. 뉴스 앵커처럼 격식체 높임말 사용 (~습니다, ~입니다, ~했습니다)
4. 차분하고 신뢰감 있는 어조로 전달
5. 숫자는 핵심만, 퍼센트는 소수점 한 자리까지
6. 마무리: "내일 또 전해드리겠습니다" 또는 "좋은 하루 되십시오"
7. 나레이션 텍스트만 출력
"""

    import time as time_module
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    for attempt in range(3):
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        elif r.status_code == 429:
            time_module.sleep(30)
        else:
            break

    # Fallback 스크립트
    return f"안녕하세요, 미국 증시 데일리 브리핑입니다. 어제 미국 증시는 혼조세로 마감했습니다. 오늘도 성공적인 투자 되세요."


def collect_daily_data() -> dict:
    """데일리 브리핑용 데이터 수집"""
    import time as time_module

    print("  [>>] 증시 데이터 수집 중...")
    indices = fetch_index_data()
    print(f"  [OK] 지수 {len(indices)}개 수집")

    # Twelve Data 분당 8크레딧 제한 - 지수(5) 후 종목(8) 요청 전 대기
    if TWELVEDATA_API_KEY and len(indices) > 0:
        print("  [..] API 크레딧 리셋 대기 (61초)...")
        time_module.sleep(61)

    print("  [>>] 상승/하락 종목 수집 중...")
    gainers, losers = fetch_top_movers()
    print(f"  [OK] 상승 {len(gainers)}개, 하락 {len(losers)}개")

    print("  [>>] 경제 이벤트 수집 중...")
    events = fetch_economic_events()
    earnings = fetch_earnings_today()
    print(f"  [OK] 이벤트 {len(events)}개, 실적 {len(earnings)}개")

    # 전체 시장 방향 판단
    if indices:
        sp500 = next((i for i in indices if i["ticker"] == "^GSPC"), None)
        if sp500:
            if sp500["change_pct"] > 0.5:
                impact = "긍정"
            elif sp500["change_pct"] < -0.5:
                impact = "부정"
            else:
                impact = "중립"
        else:
            impact = "중립"
    else:
        impact = "중립"

    return {
        "indices": indices,
        "gainers": gainers,
        "losers": losers,
        "events": events,
        "earnings": earnings,
        "impact": impact,
    }


def create_daily_briefing() -> str | None:
    """데일리 브리핑 영상 생성 및 업로드"""
    from modules.video_maker_briefing import create_briefing_video
    from modules.uploader import upload_video

    print("\n[Daily Briefing] 데일리 마켓 브리핑 생성 시작")

    # 전날 미국 장이 열렸는지 확인
    if not was_us_market_open_yesterday():
        print("[Daily Briefing] 어제 미국 장 휴장 - 브리핑 스킵")
        return None

    # 1. 데이터 수집
    data = collect_daily_data()

    # 데이터 검증: 최소 지수 2개 또는 종목 3개 필요
    min_indices = len(data["indices"]) >= 2
    min_stocks = len(data["gainers"]) >= 3 or len(data["losers"]) >= 3
    if not min_indices and not min_stocks:
        print("  [!!] 데이터 부족 - 지수 또는 종목 데이터가 충분하지 않습니다")
        print(f"      지수: {len(data['indices'])}개, 상승: {len(data['gainers'])}개, 하락: {len(data['losers'])}개")
        print("  [--] 브리핑 생성 건너뜀")
        return None

    # 2. 나레이션 생성
    print("  [>>] 나레이션 생성 중...")
    narration = generate_briefing_script(
        data["indices"], data["gainers"], data["losers"],
        data["events"], data["earnings"]
    )
    print(f"  [OK] 나레이션: {len(narration)}자")

    # 나레이션 길이 검증 (최소 150자 필요)
    if len(narration) < 150:
        print("  [!!] 나레이션이 너무 짧습니다 (150자 미만)")
        print("  [--] 브리핑 생성 건너뜀")
        return None

    # 3. 영상 생성
    print("  [>>] 영상 생성 중...")
    video_path = create_briefing_video(data, narration)
    print(f"  [OK] 영상: {video_path}")

    # 4. 업로드
    today = datetime.now().strftime("%m월 %d일")
    title = f"📊 {today} 미국 증시 브리핑 | S&P500 나스닥 다우 마감 정리"
    description = f"""매일 아침 미국 증시 마감 현황을 정리해드립니다.

📈 주요 지수 마감
📊 상승/하락 TOP 5 종목
📅 오늘의 주요 이벤트

#미국주식 #증시브리핑 #S&P500 #나스닥 #주식투자

🤖 Generated with Claude Code
"""
    tags = ["미국주식", "증시", "S&P500", "나스닥", "다우존스", "주식투자", "데일리브리핑"]

    print("  [>>] YouTube 업로드 중...")
    video_id = upload_video(video_path, title, description, tags)

    if video_id:
        url = f"https://youtu.be/{video_id}"
        print(f"  [OK] 업로드 완료: {url}")
        return url
    else:
        print("  [--] 업로드 실패 또는 한도 초과")
        return None


if __name__ == "__main__":
    create_daily_briefing()
