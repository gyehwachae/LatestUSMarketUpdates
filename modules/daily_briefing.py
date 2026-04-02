"""
매일 오전 데일리 마켓 브리핑 영상 생성
- 주요 증시 현황 (S&P 500, 나스닥, 다우, 러셀)
- TOP 5 거래 종목 (상승/하락)
- 오늘의 주요 이벤트
"""
import os
from datetime import datetime, timedelta

import yfinance as yf
import requests

from config import GROQ_API_KEY


# 주요 지수 티커 (TTS용 한글 발음 포함)
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


def fetch_index_data() -> list[dict]:
    """주요 지수 데이터 수집"""
    results = []

    for ticker, info in INDICES.items():
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
        except Exception as e:
            print(f"  [!!] 지수 데이터 실패 ({ticker}): {e}")

    return results


def fetch_top_movers() -> tuple[list[dict], list[dict]]:
    """상승/하락 TOP 5 종목 수집"""
    movers = []

    for ticker in MAJOR_STOCKS:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")

            if len(hist) >= 2:
                prev_close = hist["Close"].iloc[-2]
                current = hist["Close"].iloc[-1]
                change_pct = ((current - prev_close) / prev_close) * 100

                info = stock.info
                name = info.get("shortName", ticker)
                # TTS용 한글 회사명 (없으면 영문 shortName 사용)
                tts_name = COMPANY_NAMES.get(ticker, name[:15])

                movers.append({
                    "ticker": ticker,
                    "name": name[:20],
                    "tts_name": tts_name,
                    "price": current,
                    "change_pct": change_pct,
                })
        except Exception:
            continue

    # 상승/하락 정렬
    sorted_movers = sorted(movers, key=lambda x: x["change_pct"], reverse=True)
    top_gainers = sorted_movers[:5]
    top_losers = sorted_movers[-5:][::-1]  # 하락폭 큰 순

    return top_gainers, top_losers


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

    prompt = f"""당신은 한국 주식 투자자를 위한 유튜브 Shorts 나레이터입니다.
아래 미국 증시 데이터를 바탕으로 60초 분량의 데일리 브리핑 나레이션을 작성하세요.

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
2. 구성: 활기찬 인사 → 증시 핵심 요약 → 주목 종목 언급 → 마무리
3. 활기차고 에너지 넘치는 말투! 친근하게 말하기
4. 숫자는 핵심만 언급, 퍼센트는 소수점 한 자리까지만
5. 마지막은 "안녕히 계세요" 대신 "그럼 내일 또 알려드릴게요!" 또는 "내일 또 만나요!"로 마무리
6. 나레이션 텍스트만 출력
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
    print("  [>>] 증시 데이터 수집 중...")
    indices = fetch_index_data()
    print(f"  [OK] 지수 {len(indices)}개 수집")

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

    # 1. 데이터 수집
    data = collect_daily_data()

    # 2. 나레이션 생성
    print("  [>>] 나레이션 생성 중...")
    narration = generate_briefing_script(
        data["indices"], data["gainers"], data["losers"],
        data["events"], data["earnings"]
    )
    print(f"  [OK] 나레이션: {len(narration)}자")

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
