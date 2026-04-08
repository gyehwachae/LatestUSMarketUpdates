"""
개별 종목 모멘텀 분석 모듈
- Twelve Data(우선) / yfinance(fallback)로 가격/재무 데이터 수집
- 기술적 지표 계산 (MA 정배열, RSI, 52주 고점, 베타, 이격도)
- 펀더멘털 지표 (Rule of 40, FCF, ROIC)
- Groq AI로 모멘텀 투자 관점 분석 (경제적 해자 포함)
핵심 원칙: "예측이 아닌 대응" - 거래대금이 센 곳에서 실적 우량주를 기술적 추세에 맞춰 분석
"""
import json
import time
import requests
import yfinance as yf

from config import GROQ_API_KEY, TWELVEDATA_API_KEY, FMP_API_KEY
from modules.daily_briefing import COMPANY_NAMES

_MODEL = "llama-3.3-70b-versatile"
_URL = "https://api.groq.com/openai/v1/chat/completions"
_HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}
_MAX_RETRIES = 3

# 티커 → 한글 회사명 매핑 (나레이션 후처리용)
_TICKER_TO_KOREAN = {
    "AAPL": "애플", "Apple": "애플", "Apple Inc": "애플",
    "NVDA": "엔비디아", "NVIDIA": "엔비디아", "Nvidia": "엔비디아",
    "MSFT": "마이크로소프트", "Microsoft": "마이크로소프트",
    "GOOGL": "구글", "Google": "구글", "Alphabet": "알파벳",
    "AMZN": "아마존", "Amazon": "아마존",
    "META": "메타", "Meta": "메타", "Facebook": "메타",
    "TSLA": "테슬라", "Tesla": "테슬라",
    "AMD": "에이엠디", "Advanced Micro Devices": "에이엠디",
    "INTC": "인텔", "Intel": "인텔",
    "NFLX": "넷플릭스", "Netflix": "넷플릭스",
    "CRM": "세일즈포스", "Salesforce": "세일즈포스",
    "ADBE": "어도비", "Adobe": "어도비",
    "ORCL": "오라클", "Oracle": "오라클",
    "AVGO": "브로드컴", "Broadcom": "브로드컴",
    "CSCO": "시스코", "Cisco": "시스코",
    "QCOM": "퀄컴", "Qualcomm": "퀄컴",
    "TXN": "텍사스인스트루먼트", "Texas Instruments": "텍사스인스트루먼트",
    "IBM": "아이비엠",
    "JPM": "제이피모건", "JPMorgan": "제이피모건",
    "V": "비자", "Visa": "비자",
    "MA": "마스터카드", "Mastercard": "마스터카드",
    "BAC": "뱅크오브아메리카", "Bank of America": "뱅크오브아메리카",
    "WMT": "월마트", "Walmart": "월마트",
    "DIS": "디즈니", "Disney": "디즈니",
    "NKE": "나이키", "Nike": "나이키",
    "KO": "코카콜라", "Coca-Cola": "코카콜라",
    "PEP": "펩시코", "PepsiCo": "펩시코",
    "MCD": "맥도날드", "McDonald's": "맥도날드",
    "COST": "코스트코", "Costco": "코스트코",
    "HD": "홈디포", "Home Depot": "홈디포",
    "BA": "보잉", "Boeing": "보잉",
    "CAT": "캐터필러", "Caterpillar": "캐터필러",
    "GE": "제너럴일렉트릭", "General Electric": "제너럴일렉트릭",
    "XOM": "엑슨모빌", "Exxon": "엑슨모빌", "ExxonMobil": "엑슨모빌",
    "CVX": "셰브론", "Chevron": "셰브론",
    "JNJ": "존슨앤존슨", "Johnson & Johnson": "존슨앤존슨",
    "PFE": "화이자", "Pfizer": "화이자",
    "UNH": "유나이티드헬스", "UnitedHealth": "유나이티드헬스",
    "MRK": "머크", "Merck": "머크",
    "ABBV": "애브비", "AbbVie": "애브비",
    "LLY": "일라이릴리", "Eli Lilly": "일라이릴리",
    "TMO": "써모피셔", "Thermo Fisher": "써모피셔",
    "PYPL": "페이팔", "PayPal": "페이팔",
    "SQ": "스퀘어", "Square": "스퀘어", "Block": "블록",
    "COIN": "코인베이스", "Coinbase": "코인베이스",
    "PLTR": "팔란티어", "Palantir": "팔란티어",
    "SNOW": "스노우플레이크", "Snowflake": "스노우플레이크",
    "ZM": "줌", "Zoom": "줌",
    "UBER": "우버", "Uber": "우버",
    "LYFT": "리프트", "Lyft": "리프트",
    "ABNB": "에어비앤비", "Airbnb": "에어비앤비",
    "SHOP": "쇼피파이", "Shopify": "쇼피파이",
    "SQ": "블록", "Block Inc": "블록",
    "RIVN": "리비안", "Rivian": "리비안",
    "LCID": "루시드", "Lucid": "루시드",
    "NIO": "니오",
    "BABA": "알리바바", "Alibaba": "알리바바",
    "JD": "징동", "JD.com": "징동",
    "PDD": "핀둬둬", "Pinduoduo": "핀둬둬",
    "BIDU": "바이두", "Baidu": "바이두",
}


def _postprocess_narration(narration: str, ticker: str) -> str:
    """나레이션에서 영문 티커/회사명을 한글로 치환, 중국어 제거"""
    import re
    result = narration

    # 1. 해당 티커의 한글명으로 우선 치환
    korean_name = COMPANY_NAMES.get(ticker)
    if korean_name:
        # 티커 자체를 한글로 (대소문자 무관)
        result = re.sub(rf'\b{ticker}\b', korean_name, result, flags=re.IGNORECASE)

    # 2. 전체 매핑에서 영문 → 한글 치환
    for eng, kor in _TICKER_TO_KOREAN.items():
        if eng in result:
            result = result.replace(eng, kor)

    # 3. 중국어/일본어 문자 제거
    result = re.sub(r'[\u4e00-\u9fff]+', '', result)  # 한자
    result = re.sub(r'[\u3040-\u30ff]+', '', result)  # 히라가나/가타카나

    # 4. 흔한 오타/오류 수정
    typo_fixes = [
        (r'저평이', '저평가'),
        (r'고평이', '고평가'),
        (r'댓글으로', '댓글로'),
        (r'숫자으로', '숫자로'),
        (r'데이터으로', '데이터로'),
    ]
    for pattern, replacement in typo_fixes:
        result = re.sub(pattern, replacement, result)

    # 5. 한국어 조사 자동 교정 (받침 유무 기반)
    result = _fix_korean_particles(result)

    # 6. 연속 공백 정리
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def _has_final_consonant(char: str) -> bool:
    """한글 문자의 받침 유무 확인"""
    if not char or not ('가' <= char <= '힣'):
        return False
    # 한글 유니코드: (초성 * 21 + 중성) * 28 + 종성 + 0xAC00
    code = ord(char) - 0xAC00
    return (code % 28) != 0


def _get_final_consonant(char: str) -> int:
    """한글 문자의 받침(종성) 코드 반환 (0=받침없음, 8=ㄹ)"""
    if not char or not ('가' <= char <= '힣'):
        return 0
    code = ord(char) - 0xAC00
    return code % 28


def _fix_korean_particles(text: str) -> str:
    """받침 유무에 따라 조사를 자동 교정 (보수적 접근)"""
    import re

    def choose_particle(char, with_consonant, without_consonant):
        """받침 유무에 따라 적절한 조사 선택"""
        if _has_final_consonant(char):
            return with_consonant
        return without_consonant

    def choose_euro_ro(char):
        """으로/로 선택 (ㄹ 받침은 '로' 사용)"""
        final = _get_final_consonant(char)
        # 받침 없음(0) 또는 ㄹ(8)이면 '로', 나머지 받침은 '으로'
        if final == 0 or final == 8:
            return '로'
        return '으로'

    def needs_consonant_particle(char: str) -> bool:
        """받침용 조사가 필요한지 확인 (한글 발음 기준)"""
        if '가' <= char <= '힣':
            return _has_final_consonant(char)
        # 숫자 발음: 0영/공, 1일, 2이, 3삼, 4사, 5오, 6육, 7칠, 8팔, 9구
        # 받침 있음: 0(ㅇ), 1(ㄹ), 3(ㅁ), 6(ㄱ), 7(ㄹ), 8(ㄹ)
        # 받침 없음: 2, 4, 5, 9
        if char in '013678':
            return True
        if char in '2459':
            return False
        # 영문 약어/단어: 한글 발음 기준
        # 대부분 영문은 ~이/~트/~스 등으로 끝나서 받침 없음
        # 예: RSI→알에스아이(이), Fact→팩트(트), EPS→이피에스(스)
        # l→엘(ㄹ), m→엠(ㅁ), n→엔(ㄴ) 은 받침 있음
        if char.lower() in 'lmn':
            return True
        # 나머지 영문은 대부분 받침 없음 (~이, ~트, ~스, ~피 등)
        if char.isalpha():
            return False
        # %→퍼센트(트=받침없음), $→달러(러=받침없음)
        if char in '%$':
            return False
        return False

    # 명확한 오류만 교정 (false positive 최소화)
    corrections = [
        # 은/는: 한글/숫자/영문/% 뒤
        (r'([가-힣0-9a-zA-Z%])은(?=[\s,\.!?\)]|$|[가-힣])',
         lambda m: m.group(1) + ('은' if needs_consonant_particle(m.group(1)) else '는')),
        (r'([가-힣0-9a-zA-Z%])는(?=[\s,\.!?\)]|$|[가-힣])',
         lambda m: m.group(1) + ('은' if needs_consonant_particle(m.group(1)) else '는')),
        # 이/가: 한글만 (숫자/영문은 문맥 의존적이라 제외)
        (r'([가-힣])이(?=[\s,\.!?\)]|$)',
         lambda m: m.group(1) + '가' if not _has_final_consonant(m.group(1)) else m.group(1) + '이'),
        # 을/를
        (r'([가-힣0-9a-zA-Z%])을(?=[\s,\.!?\)]|$|[가-힣])',
         lambda m: m.group(1) + ('을' if needs_consonant_particle(m.group(1)) else '를')),
        (r'([가-힣0-9a-zA-Z%])를(?=[\s,\.!?\)]|$|[가-힣])',
         lambda m: m.group(1) + ('을' if needs_consonant_particle(m.group(1)) else '를')),
        # 과/와
        (r'([가-힣0-9a-zA-Z%])과(?=[\s,\.!?\)]|$|[가-힣])',
         lambda m: m.group(1) + ('과' if needs_consonant_particle(m.group(1)) else '와')),
        (r'([가-힣0-9a-zA-Z%])와(?=[\s,\.!?\)]|$|[가-힣])',
         lambda m: m.group(1) + ('과' if needs_consonant_particle(m.group(1)) else '와')),
        # 으로/로
        (r'([가-힣0-9a-zA-Z%])으로(?=[\s,\.!?\)]|$|[가-힣])',
         lambda m: m.group(1) + ('으로' if needs_consonant_particle(m.group(1)) else '로')),
        (r'([가-힣])로(?=[\s,\.!?\)]|$|[가-힣])',
         lambda m: m.group(1) + choose_euro_ro(m.group(1))),
    ]

    result = text
    for pattern, replacement in corrections:
        result = re.sub(pattern, replacement, result)

    return result


# ============ Twelve Data API 함수 ============

def fetch_stock_data_twelvedata(ticker: str) -> dict | None:
    """
    Twelve Data API로 종목 데이터 수집 + 기술적 지표 계산
    - /quote: 현재가, 52주 고저
    - /time_series: 6개월 OHLCV (MA, RSI 계산용)
    """
    if not TWELVEDATA_API_KEY:
        return None

    try:
        # 1. Quote 데이터 (현재가, 52주 고저)
        quote_url = "https://api.twelvedata.com/quote"
        quote_params = {
            "symbol": ticker,
            "apikey": TWELVEDATA_API_KEY,
        }
        quote_r = requests.get(quote_url, params=quote_params, timeout=30)
        quote_data = quote_r.json()

        # Rate limit 체크
        if quote_data.get("code") == 429:
            print(f"  [..] Twelve Data Rate limit - 61초 대기...")
            time.sleep(61)
            quote_r = requests.get(quote_url, params=quote_params, timeout=30)
            quote_data = quote_r.json()

        if "status" in quote_data and quote_data["status"] == "error":
            print(f"  [!!] Twelve Data quote 오류: {quote_data.get('message', 'Unknown')}")
            return None

        # 2. Time series 데이터 (6개월, 일봉)
        time.sleep(1)  # API 크레딧 보호
        ts_url = "https://api.twelvedata.com/time_series"
        ts_params = {
            "symbol": ticker,
            "interval": "1day",
            "outputsize": 200,  # 약 6개월 + 여유
            "apikey": TWELVEDATA_API_KEY,
        }
        ts_r = requests.get(ts_url, params=ts_params, timeout=30)
        ts_data = ts_r.json()

        if ts_data.get("code") == 429:
            print(f"  [..] Twelve Data Rate limit - 61초 대기...")
            time.sleep(61)
            ts_r = requests.get(ts_url, params=ts_params, timeout=30)
            ts_data = ts_r.json()

        if "status" in ts_data and ts_data["status"] == "error":
            print(f"  [!!] Twelve Data time_series 오류: {ts_data.get('message', 'Unknown')}")
            return None

        values = ts_data.get("values", [])
        if len(values) < 50:
            print(f"  [!!] {ticker}: 가격 데이터 부족 ({len(values)}개)")
            return None

        # 데이터 역순 정렬 (과거 → 현재)
        values = values[::-1]

        # 가격/볼륨 추출
        prices = [float(v["close"]) for v in values]
        volumes = [float(v["volume"]) for v in values]
        current_price = prices[-1]

        # 기본 정보
        name = quote_data.get("name", ticker)
        # Twelve Data는 sector 정보가 없으므로 기본값 사용
        sector = "Unknown"

        # 이동평균선
        ma_50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else current_price
        ma_200 = sum(prices[-200:]) / 200 if len(prices) >= 200 else ma_50

        # MA 정배열 여부
        ma_alignment = current_price > ma_50 > ma_200

        # RSI 계산
        rsi = calculate_rsi(prices)
        if rsi >= 80:
            rsi_signal = "극과열"
        elif rsi >= 70:
            rsi_signal = "과열"
        elif rsi >= 50:
            rsi_signal = "강세"
        elif rsi >= 30:
            rsi_signal = "약세"
        else:
            rsi_signal = "과매도"

        # 이격도 계산
        disparity_50 = ((current_price - ma_50) / ma_50) * 100 if ma_50 > 0 else 0

        if disparity_50 > 15:
            disparity_signal = "과열 (조정 주의)"
        elif disparity_50 > 10:
            disparity_signal = "상승 과열"
        elif disparity_50 < -15:
            disparity_signal = "과매도 (반등 가능)"
        elif disparity_50 < -10:
            disparity_signal = "하락 과열"
        else:
            disparity_signal = "정상"

        # 52주 고저 (quote에서)
        week_52_high = float(quote_data.get("fifty_two_week", {}).get("high", max(prices)))
        week_52_low = float(quote_data.get("fifty_two_week", {}).get("low", min(prices)))
        from_high_pct = ((current_price - week_52_high) / week_52_high) * 100

        # 거래량 분석
        recent_vol = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volumes[-1]
        avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else recent_vol
        volume_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "technical": {
                "price": round(current_price, 2),
                "ma_50": round(ma_50, 2),
                "ma_200": round(ma_200, 2),
                "ma_alignment": ma_alignment,
                "rsi": round(rsi, 1),
                "rsi_signal": rsi_signal,
                "disparity_50": round(disparity_50, 1),
                "disparity_signal": disparity_signal,
                "beta": None,  # Twelve Data 무료에서 미지원
                "beta_signal": "N/A",
                "week_52_high": round(week_52_high, 2),
                "week_52_low": round(week_52_low, 2),
                "from_high_pct": round(from_high_pct, 1),
                "volume_ratio": round(volume_ratio, 2),
            },
            "fundamental": {
                "market_cap": 0,
                "pe_ratio": None,
                "peg_ratio": None,
                "peg_signal": "N/A",
                "eps_growth": None,
                "revenue_growth": None,
                "growth_quality": "N/A",
                "gross_margin": None,
                "gross_margin_trend": "N/A",
                "operating_margin": None,
                "profit_margin": None,
                "free_cash_flow": None,
                "fcf_per_share": None,
                "roic": None,
                "rule_of_40": None,
                "rule_of_40_signal": "N/A",
            },
            "price_history": prices,
            "_source": "twelvedata",
        }

    except Exception as e:
        print(f"  [!!] Twelve Data {ticker} 실패: {e}")
        return None


def fetch_market_sentiment_twelvedata() -> dict:
    """Twelve Data로 VIX 및 시장 심리 지표 수집"""
    result = {
        "vix": None,
        "vix_signal": "N/A",
        "vix_trend": "N/A",
        "fear_greed": None,
        "fear_greed_signal": "N/A",
        "sp500_above_200ma": None,
    }

    if not TWELVEDATA_API_KEY:
        return result

    try:
        # VIX ETF (VXX) 또는 UVXY 사용
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": "VXX",
            "interval": "1day",
            "outputsize": 10,
            "apikey": TWELVEDATA_API_KEY,
        }
        r = requests.get(url, params=params, timeout=30)
        data = r.json()

        if data.get("code") == 429:
            time.sleep(61)
            r = requests.get(url, params=params, timeout=30)
            data = r.json()

        values = data.get("values", [])
        if len(values) >= 2:
            vix_value = float(values[0]["close"])
            vix_prev = float(values[1]["close"])
            # VXX는 VIX의 변동성을 추종하므로 대략적인 VIX 추정
            # 실제 VIX와 다르지만 방향성은 유사
            result["vix"] = round(vix_value, 2)

            # VIX 해석 (VXX 기준으로 조정)
            if vix_value < 15:
                result["vix_signal"] = "낙관 (저변동성)"
            elif vix_value < 25:
                result["vix_signal"] = "정상"
            elif vix_value < 35:
                result["vix_signal"] = "주의 (변동성 상승)"
            elif vix_value < 50:
                result["vix_signal"] = "경계 (고변동성)"
            else:
                result["vix_signal"] = "공포 (극고변동성)"

            # 추세
            if vix_value > vix_prev * 1.1:
                result["vix_trend"] = "급등 중 (관망)"
            elif vix_value < vix_prev * 0.9 and vix_prev > 25:
                result["vix_trend"] = "급등 후 하락 (매수 기회)"
            elif vix_value < vix_prev:
                result["vix_trend"] = "하락 중 (안정화)"
            else:
                result["vix_trend"] = "횡보"

            # Fear & Greed 추정
            fear_greed = max(0, min(100, 100 - ((vix_value - 10) / 40) * 100))
            result["fear_greed"] = round(fear_greed, 0)

            if fear_greed >= 75:
                result["fear_greed_signal"] = "극단적 탐욕 (리스크 관리 필요)"
            elif fear_greed >= 55:
                result["fear_greed_signal"] = "탐욕"
            elif fear_greed >= 45:
                result["fear_greed_signal"] = "중립"
            elif fear_greed >= 25:
                result["fear_greed_signal"] = "공포"
            else:
                result["fear_greed_signal"] = "극단적 공포 (매수 기회)"

        # S&P 500 (SPY ETF) 200일선 체크
        time.sleep(1)
        spy_params = {
            "symbol": "SPY",
            "interval": "1day",
            "outputsize": 210,
            "apikey": TWELVEDATA_API_KEY,
        }
        spy_r = requests.get(url, params=spy_params, timeout=30)
        spy_data = spy_r.json()

        spy_values = spy_data.get("values", [])
        if len(spy_values) >= 200:
            spy_price = float(spy_values[0]["close"])
            spy_closes = [float(v["close"]) for v in spy_values[:200]]
            spy_200ma = sum(spy_closes) / 200
            result["sp500_above_200ma"] = spy_price > spy_200ma

    except Exception as e:
        print(f"  [!!] Twelve Data 시장 심리 수집 실패: {e}")

    return result


# ============ RSI 계산 함수 ============

def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """RSI (Relative Strength Index) 계산"""
    if len(prices) < period + 1:
        return 50.0  # 데이터 부족 시 중립값

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    # 초기 평균
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Smoothed 평균 (Wilder's smoothing)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def fetch_stock_data_yfinance(ticker: str) -> dict | None:
    """
    yfinance로 종목 데이터 수집 + 기술적 지표 계산 (fallback용)

    Returns:
        {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "sector": "Technology",
            "technical": { ... },
            "fundamental": { ... },
            "price_history": [...],  # 6개월
        }
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info or "regularMarketPrice" not in info:
            print(f"  [!!] {ticker}: 데이터 없음")
            return None

        # 기본 정보
        name = info.get("shortName", info.get("longName", ticker))
        sector = info.get("sector", "Unknown")

        # 가격 데이터 (6개월)
        hist_6m = stock.history(period="6mo", interval="1d")
        if hist_6m.empty or len(hist_6m) < 50:
            print(f"  [!!] {ticker}: 가격 데이터 부족")
            return None

        prices = hist_6m["Close"].tolist()
        volumes = hist_6m["Volume"].tolist()
        current_price = prices[-1]

        # 이동평균선
        ma_50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else current_price
        ma_200 = sum(prices[-200:]) / 200 if len(prices) >= 200 else ma_50

        # MA 정배열 여부 (주가 > 50일선 > 200일선)
        ma_alignment = current_price > ma_50 > ma_200

        # RSI 계산
        rsi = calculate_rsi(prices)
        if rsi >= 80:
            rsi_signal = "극과열"
        elif rsi >= 70:
            rsi_signal = "과열"
        elif rsi >= 50:
            rsi_signal = "강세"
        elif rsi >= 30:
            rsi_signal = "약세"
        else:
            rsi_signal = "과매도"

        # 이격도 계산 (주가 / 이동평균선 비율)
        disparity_20 = ((current_price - ma_50) / ma_50) * 100 if ma_50 > 0 else 0
        disparity_50 = ((current_price - ma_50) / ma_50) * 100 if ma_50 > 0 else 0

        # 이격도 신호 (20일선 기준 ±10% 이상이면 주의)
        if disparity_50 > 15:
            disparity_signal = "과열 (조정 주의)"
        elif disparity_50 > 10:
            disparity_signal = "상승 과열"
        elif disparity_50 < -15:
            disparity_signal = "과매도 (반등 가능)"
        elif disparity_50 < -10:
            disparity_signal = "하락 과열"
        else:
            disparity_signal = "정상"

        # 베타 (시장 대비 변동성)
        beta = info.get("beta", None)
        if beta is not None:
            if beta > 2.0:
                beta_signal = "고위험 (변동성 매우 높음)"
            elif beta > 1.5:
                beta_signal = "높은 변동성"
            elif beta > 1.0:
                beta_signal = "시장 평균 이상"
            elif beta > 0.5:
                beta_signal = "안정적"
            else:
                beta_signal = "매우 안정 (방어주)"
        else:
            beta_signal = "N/A"

        # 52주 고점/저점
        week_52_high = info.get("fiftyTwoWeekHigh", max(prices))
        week_52_low = info.get("fiftyTwoWeekLow", min(prices))
        from_high_pct = ((current_price - week_52_high) / week_52_high) * 100

        # 거래량 분석 (최근 5일 평균 vs 20일 평균)
        recent_vol = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volumes[-1]
        avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else recent_vol
        volume_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

        # 펀더멘털 데이터
        market_cap = info.get("marketCap", 0)
        pe_ratio = info.get("trailingPE") or info.get("forwardPE")
        peg_ratio = info.get("pegRatio")

        # PEG 신호
        if peg_ratio is not None:
            if peg_ratio < 1.0:
                peg_signal = "저평가"
            elif peg_ratio < 2.0:
                peg_signal = "적정"
            else:
                peg_signal = "고평가"
        else:
            peg_signal = "N/A"

        # 재무 데이터 수집
        eps_growth = None
        revenue_growth = info.get("revenueGrowth")
        gross_margin = info.get("grossMargins")
        operating_margin = info.get("operatingMargins")
        profit_margin = info.get("profitMargins")

        # Free Cash Flow (실질 현금 창출력)
        free_cash_flow = info.get("freeCashflow")
        fcf_per_share = None
        if free_cash_flow and market_cap:
            shares = info.get("sharesOutstanding", 1)
            fcf_per_share = free_cash_flow / shares if shares else None

        # ROIC (투하자본수익률) - 경제적 해자의 핵심 지표
        roic = info.get("returnOnCapital") or info.get("returnOnEquity")

        # Rule of 40 (소프트웨어/플랫폼 기업 건전성)
        # 매출 성장률 + 영업이익률 >= 40% 면 우량
        rule_of_40 = None
        rule_of_40_signal = "N/A"
        if revenue_growth is not None and operating_margin is not None:
            rev_growth_pct = revenue_growth * 100 if abs(revenue_growth) < 1 else revenue_growth
            op_margin_pct = operating_margin * 100 if abs(operating_margin) < 1 else operating_margin
            rule_of_40 = rev_growth_pct + op_margin_pct
            if rule_of_40 >= 40:
                rule_of_40_signal = "우량 (40% 이상)"
            elif rule_of_40 >= 30:
                rule_of_40_signal = "양호"
            elif rule_of_40 >= 20:
                rule_of_40_signal = "보통"
            else:
                rule_of_40_signal = "주의"

        # EPS 성장률 계산 시도
        try:
            earnings = stock.earnings
            if earnings is not None and len(earnings) >= 2:
                recent_eps = earnings.iloc[-1]["Earnings"] if "Earnings" in earnings.columns else None
                prev_eps = earnings.iloc[-2]["Earnings"] if "Earnings" in earnings.columns else None
                if recent_eps and prev_eps and prev_eps != 0:
                    eps_growth = ((recent_eps - prev_eps) / abs(prev_eps)) * 100
        except Exception:
            pass

        # 성장 품질 판단 (EPS 성장 > 매출 성장이면 양호 = 영업 레버리지)
        if eps_growth is not None and revenue_growth is not None:
            revenue_growth_pct = revenue_growth * 100 if abs(revenue_growth) < 1 else revenue_growth
            if eps_growth > revenue_growth_pct * 1.5:
                growth_quality = "우수 (영업 레버리지)"
            elif eps_growth > revenue_growth_pct:
                growth_quality = "양호"
            else:
                growth_quality = "주의"
        else:
            growth_quality = "N/A"

        # 마진 추이 (간단히 현재값만)
        if gross_margin:
            if gross_margin > 0.5:
                gross_margin_trend = "우수"
            elif gross_margin > 0.3:
                gross_margin_trend = "양호"
            else:
                gross_margin_trend = "주의"
        else:
            gross_margin_trend = "N/A"

        return {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "technical": {
                "price": round(current_price, 2),
                "ma_50": round(ma_50, 2),
                "ma_200": round(ma_200, 2),
                "ma_alignment": ma_alignment,
                "rsi": round(rsi, 1),
                "rsi_signal": rsi_signal,
                "disparity_50": round(disparity_50, 1),
                "disparity_signal": disparity_signal,
                "beta": round(beta, 2) if beta else None,
                "beta_signal": beta_signal,
                "week_52_high": round(week_52_high, 2),
                "week_52_low": round(week_52_low, 2),
                "from_high_pct": round(from_high_pct, 1),
                "volume_ratio": round(volume_ratio, 2),
            },
            "fundamental": {
                "market_cap": market_cap,
                "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
                "peg_ratio": round(peg_ratio, 2) if peg_ratio else None,
                "peg_signal": peg_signal,
                "eps_growth": round(eps_growth, 1) if eps_growth else None,
                "revenue_growth": round(revenue_growth * 100, 1) if revenue_growth else None,
                "growth_quality": growth_quality,
                "gross_margin": round(gross_margin * 100, 1) if gross_margin else None,
                "gross_margin_trend": gross_margin_trend,
                "operating_margin": round(operating_margin * 100, 1) if operating_margin else None,
                "profit_margin": round(profit_margin * 100, 1) if profit_margin else None,
                "free_cash_flow": free_cash_flow,
                "fcf_per_share": round(fcf_per_share, 2) if fcf_per_share else None,
                "roic": round(roic * 100, 1) if roic else None,
                "rule_of_40": round(rule_of_40, 1) if rule_of_40 else None,
                "rule_of_40_signal": rule_of_40_signal,
            },
            "price_history": prices,
        }

    except Exception as e:
        print(f"  [!!] {ticker} 데이터 수집 실패 (yfinance): {e}")
        return None


# ============ Financial Modeling Prep API 함수 ============

def fetch_fundamental_data_fmp(ticker: str) -> tuple[dict, dict]:
    """
    Financial Modeling Prep API로 펀더멘털 데이터 수집
    - /profile: 회사 정보, 섹터, 베타, 시가총액
    - /ratios: PE, PEG, 마진, ROE 등
    - /key-metrics: FCF, ROIC 등
    """
    result = {
        "market_cap": 0,
        "pe_ratio": None,
        "peg_ratio": None,
        "peg_signal": "N/A",
        "eps_growth": None,
        "revenue_growth": None,
        "growth_quality": "N/A",
        "gross_margin": None,
        "gross_margin_trend": "N/A",
        "operating_margin": None,
        "profit_margin": None,
        "free_cash_flow": None,
        "fcf_per_share": None,
        "roic": None,
        "rule_of_40": None,
        "rule_of_40_signal": "N/A",
    }
    beta_info = {"beta": None, "beta_signal": "N/A", "sector": "Unknown"}

    if not FMP_API_KEY:
        return result, beta_info

    # 2025년 8월 이후 새 API 엔드포인트 (/stable/)
    base_url = "https://financialmodelingprep.com/stable"

    try:
        # 1. Company Profile (베타, 섹터, 시가총액)
        profile_url = f"{base_url}/profile?symbol={ticker}&apikey={FMP_API_KEY}"
        profile_r = requests.get(profile_url, timeout=15)
        profile_data = profile_r.json()

        if profile_data and len(profile_data) > 0:
            profile = profile_data[0]
            result["market_cap"] = profile.get("marketCap", 0)
            beta_info["sector"] = profile.get("sector", "Unknown")

            beta = profile.get("beta")
            if beta is not None:
                beta_info["beta"] = round(beta, 2)
                if beta > 2.0:
                    beta_info["beta_signal"] = "고위험 (변동성 매우 높음)"
                elif beta > 1.5:
                    beta_info["beta_signal"] = "높은 변동성"
                elif beta > 1.0:
                    beta_info["beta_signal"] = "시장 평균 이상"
                elif beta > 0.5:
                    beta_info["beta_signal"] = "안정적"
                else:
                    beta_info["beta_signal"] = "매우 안정 (방어주)"

        # 2. Ratios (PE, PEG, 마진 등) - TTM (Trailing Twelve Months)
        time.sleep(0.5)  # API 크레딧 보호
        ratios_url = f"{base_url}/ratios-ttm?symbol={ticker}&apikey={FMP_API_KEY}"
        ratios_r = requests.get(ratios_url, timeout=15)
        ratios_data = ratios_r.json()

        if ratios_data and len(ratios_data) > 0:
            ratios = ratios_data[0]

            # FMP /stable/ API 필드명 (2025년 이후 변경됨)
            pe_ratio = ratios.get("priceToEarningsRatioTTM")
            peg_ratio = ratios.get("priceToEarningsGrowthRatioTTM")
            gross_margin = ratios.get("grossProfitMarginTTM")
            operating_margin = ratios.get("operatingProfitMarginTTM")
            profit_margin = ratios.get("netProfitMarginTTM")
            roic = ratios.get("returnOnCapitalEmployedTTM")
            fcf_per_share = ratios.get("freeCashFlowPerShareTTM")

            result["pe_ratio"] = round(pe_ratio, 2) if pe_ratio else None
            result["peg_ratio"] = round(peg_ratio, 2) if peg_ratio else None
            result["gross_margin"] = round(gross_margin * 100, 1) if gross_margin else None
            result["operating_margin"] = round(operating_margin * 100, 1) if operating_margin else None
            result["profit_margin"] = round(profit_margin * 100, 1) if profit_margin else None
            result["roic"] = round(roic * 100, 1) if roic else None
            if fcf_per_share:
                result["fcf_per_share"] = round(fcf_per_share, 2)

            # PEG 신호
            if peg_ratio is not None:
                if peg_ratio < 1.0:
                    result["peg_signal"] = "저평가"
                elif peg_ratio < 2.0:
                    result["peg_signal"] = "적정"
                else:
                    result["peg_signal"] = "고평가"

            # 마진 추이
            if gross_margin:
                if gross_margin > 0.5:
                    result["gross_margin_trend"] = "우수"
                elif gross_margin > 0.3:
                    result["gross_margin_trend"] = "양호"
                else:
                    result["gross_margin_trend"] = "주의"

        # 3. Key Metrics (FCF 등)
        time.sleep(0.5)
        metrics_url = f"{base_url}/key-metrics-ttm?symbol={ticker}&apikey={FMP_API_KEY}"
        metrics_r = requests.get(metrics_url, timeout=15)
        metrics_data = metrics_r.json()

        if metrics_data and len(metrics_data) > 0:
            metrics = metrics_data[0]

            # FCF (ratios에서 못 가져왔으면 여기서)
            if not result.get("fcf_per_share"):
                fcf = metrics.get("freeCashFlowPerShareTTM")
                if fcf:
                    result["fcf_per_share"] = round(fcf, 2)

            # ROIC (returnOnInvestedCapitalTTM이 더 정확)
            roic_invested = metrics.get("returnOnInvestedCapitalTTM")
            if roic_invested and not result.get("roic"):
                result["roic"] = round(roic_invested * 100, 1)

        # 4. Growth 데이터 (매출 성장률)
        time.sleep(0.5)
        growth_url = f"{base_url}/financial-growth?symbol={ticker}&period=annual&limit=1&apikey={FMP_API_KEY}"
        growth_r = requests.get(growth_url, timeout=15)
        growth_data = growth_r.json()

        if growth_data and len(growth_data) > 0:
            growth = growth_data[0]
            revenue_growth = growth.get("revenueGrowth")
            eps_growth = growth.get("epsgrowth")

            if revenue_growth is not None:
                result["revenue_growth"] = round(revenue_growth * 100, 1)
            if eps_growth is not None:
                result["eps_growth"] = round(eps_growth * 100, 1)

            # Rule of 40 계산
            if revenue_growth is not None and result.get("operating_margin"):
                rev_pct = revenue_growth * 100
                op_pct = result["operating_margin"]
                rule_of_40 = rev_pct + op_pct
                result["rule_of_40"] = round(rule_of_40, 1)

                if rule_of_40 >= 40:
                    result["rule_of_40_signal"] = "우량 (40% 이상)"
                elif rule_of_40 >= 30:
                    result["rule_of_40_signal"] = "양호"
                elif rule_of_40 >= 20:
                    result["rule_of_40_signal"] = "보통"
                else:
                    result["rule_of_40_signal"] = "주의"

            # 성장 품질
            if eps_growth is not None and revenue_growth is not None:
                eps_pct = eps_growth * 100
                rev_pct = revenue_growth * 100
                if eps_pct > rev_pct * 1.5:
                    result["growth_quality"] = "우수 (영업 레버리지)"
                elif eps_pct > rev_pct:
                    result["growth_quality"] = "양호"
                else:
                    result["growth_quality"] = "주의"

    except Exception as e:
        print(f"  [..] FMP API 실패: {e}")

    return result, beta_info


def fetch_fundamental_data_yfinance(ticker: str, retry_count: int = 2) -> tuple[dict, dict]:
    """
    yfinance에서 펀더멘털 데이터만 수집 (Twelve Data 보완용)
    Rate Limit 발생 시 재시도, 최종 실패 시 빈 dict 반환
    """
    # Rate Limit 회피를 위한 딜레이
    time.sleep(3)

    result = {
        "market_cap": 0,
        "pe_ratio": None,
        "peg_ratio": None,
        "peg_signal": "N/A",
        "eps_growth": None,
        "revenue_growth": None,
        "growth_quality": "N/A",
        "gross_margin": None,
        "gross_margin_trend": "N/A",
        "operating_margin": None,
        "profit_margin": None,
        "free_cash_flow": None,
        "fcf_per_share": None,
        "roic": None,
        "rule_of_40": None,
        "rule_of_40_signal": "N/A",
    }
    beta_info = {"beta": None, "beta_signal": "N/A", "sector": "Unknown"}

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        if not info:
            return result, beta_info

        # 베타 및 섹터 (기술적 지표 보완)
        beta = info.get("beta")
        if beta is not None:
            beta_info["beta"] = round(beta, 2)
            if beta > 2.0:
                beta_info["beta_signal"] = "고위험 (변동성 매우 높음)"
            elif beta > 1.5:
                beta_info["beta_signal"] = "높은 변동성"
            elif beta > 1.0:
                beta_info["beta_signal"] = "시장 평균 이상"
            elif beta > 0.5:
                beta_info["beta_signal"] = "안정적"
            else:
                beta_info["beta_signal"] = "매우 안정 (방어주)"

        beta_info["sector"] = info.get("sector", "Unknown")

        # 펀더멘털 데이터
        market_cap = info.get("marketCap", 0)
        pe_ratio = info.get("trailingPE") or info.get("forwardPE")
        peg_ratio = info.get("pegRatio")

        # PEG 신호
        if peg_ratio is not None:
            if peg_ratio < 1.0:
                peg_signal = "저평가"
            elif peg_ratio < 2.0:
                peg_signal = "적정"
            else:
                peg_signal = "고평가"
        else:
            peg_signal = "N/A"

        # 재무 데이터
        revenue_growth = info.get("revenueGrowth")
        gross_margin = info.get("grossMargins")
        operating_margin = info.get("operatingMargins")
        profit_margin = info.get("profitMargins")

        # Free Cash Flow
        free_cash_flow = info.get("freeCashflow")
        fcf_per_share = None
        if free_cash_flow and market_cap:
            shares = info.get("sharesOutstanding", 1)
            fcf_per_share = free_cash_flow / shares if shares else None

        # ROIC
        roic = info.get("returnOnCapital") or info.get("returnOnEquity")

        # Rule of 40
        rule_of_40 = None
        rule_of_40_signal = "N/A"
        if revenue_growth is not None and operating_margin is not None:
            rev_growth_pct = revenue_growth * 100 if abs(revenue_growth) < 1 else revenue_growth
            op_margin_pct = operating_margin * 100 if abs(operating_margin) < 1 else operating_margin
            rule_of_40 = rev_growth_pct + op_margin_pct
            if rule_of_40 >= 40:
                rule_of_40_signal = "우량 (40% 이상)"
            elif rule_of_40 >= 30:
                rule_of_40_signal = "양호"
            elif rule_of_40 >= 20:
                rule_of_40_signal = "보통"
            else:
                rule_of_40_signal = "주의"

        # EPS 성장률
        eps_growth = None
        try:
            earnings = stock.earnings
            if earnings is not None and len(earnings) >= 2:
                recent_eps = earnings.iloc[-1]["Earnings"] if "Earnings" in earnings.columns else None
                prev_eps = earnings.iloc[-2]["Earnings"] if "Earnings" in earnings.columns else None
                if recent_eps and prev_eps and prev_eps != 0:
                    eps_growth = ((recent_eps - prev_eps) / abs(prev_eps)) * 100
        except Exception:
            pass

        # 성장 품질
        if eps_growth is not None and revenue_growth is not None:
            revenue_growth_pct = revenue_growth * 100 if abs(revenue_growth) < 1 else revenue_growth
            if eps_growth > revenue_growth_pct * 1.5:
                growth_quality = "우수 (영업 레버리지)"
            elif eps_growth > revenue_growth_pct:
                growth_quality = "양호"
            else:
                growth_quality = "주의"
        else:
            growth_quality = "N/A"

        # 마진 추이
        if gross_margin:
            if gross_margin > 0.5:
                gross_margin_trend = "우수"
            elif gross_margin > 0.3:
                gross_margin_trend = "양호"
            else:
                gross_margin_trend = "주의"
        else:
            gross_margin_trend = "N/A"

        result = {
            "market_cap": market_cap,
            "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
            "peg_ratio": round(peg_ratio, 2) if peg_ratio else None,
            "peg_signal": peg_signal,
            "eps_growth": round(eps_growth, 1) if eps_growth else None,
            "revenue_growth": round(revenue_growth * 100, 1) if revenue_growth else None,
            "growth_quality": growth_quality,
            "gross_margin": round(gross_margin * 100, 1) if gross_margin else None,
            "gross_margin_trend": gross_margin_trend,
            "operating_margin": round(operating_margin * 100, 1) if operating_margin else None,
            "profit_margin": round(profit_margin * 100, 1) if profit_margin else None,
            "free_cash_flow": free_cash_flow,
            "fcf_per_share": round(fcf_per_share, 2) if fcf_per_share else None,
            "roic": round(roic * 100, 1) if roic else None,
            "rule_of_40": round(rule_of_40, 1) if rule_of_40 else None,
            "rule_of_40_signal": rule_of_40_signal,
        }

    except Exception as e:
        error_msg = str(e)
        if ("Too Many Requests" in error_msg or "Rate" in error_msg) and retry_count > 0:
            wait_time = (3 - retry_count) * 10 + 10  # 10초, 20초
            print(f"  [..] yfinance Rate Limit - {wait_time}초 대기 후 재시도...")
            time.sleep(wait_time)
            return fetch_fundamental_data_yfinance(ticker, retry_count - 1)
        print(f"  [..] 펀더멘털 보완 실패 (yfinance): {e}")

    return result, beta_info


def fetch_stock_data(ticker: str) -> dict | None:
    """
    종목 데이터 수집
    - 기술적 데이터: Twelve Data 우선, yfinance fallback
    - 펀더멘털 데이터: FMP 우선, yfinance fallback
    """
    # Twelve Data로 기술적 데이터 시도
    if TWELVEDATA_API_KEY:
        result = fetch_stock_data_twelvedata(ticker)
        if result:
            print(f"  [OK] Twelve Data로 {ticker} 기술적 데이터 수집 완료")

            # 펀더멘털 보완: FMP 우선, yfinance fallback
            fundamental, beta_info = None, None

            # 1. FMP 시도
            if FMP_API_KEY:
                print(f"  [>>] 펀더멘털 데이터 수집 중 (FMP)...")
                fundamental, beta_info = fetch_fundamental_data_fmp(ticker)
                if fundamental.get("pe_ratio") or fundamental.get("market_cap"):
                    print(f"  [OK] FMP 펀더멘털 수집 완료")
                else:
                    print(f"  [..] FMP 데이터 부족, yfinance fallback...")
                    fundamental, beta_info = None, None

            # 2. yfinance fallback
            if fundamental is None:
                print(f"  [>>] 펀더멘털 데이터 수집 중 (yfinance)...")
                fundamental, beta_info = fetch_fundamental_data_yfinance(ticker)
                if fundamental.get("pe_ratio") or fundamental.get("market_cap"):
                    print(f"  [OK] yfinance 펀더멘털 수집 완료")
                else:
                    print(f"  [--] 펀더멘털 데이터 없음 (기술적 분석만 진행)")

            # 펀더멘털 병합
            result["fundamental"] = fundamental

            # 베타/섹터 보완
            if beta_info and beta_info.get("beta") is not None:
                result["technical"]["beta"] = beta_info["beta"]
                result["technical"]["beta_signal"] = beta_info["beta_signal"]
            if beta_info and beta_info.get("sector") != "Unknown":
                result["sector"] = beta_info["sector"]

            return result
        print(f"  [..] Twelve Data 실패, yfinance fallback...")

    # yfinance fallback (전체 데이터)
    return fetch_stock_data_yfinance(ticker)


def fetch_market_sentiment_yfinance() -> dict:
    """VIX 및 시장 심리 지표 수집"""
    result = {
        "vix": None,
        "vix_signal": "N/A",
        "vix_trend": "N/A",
        "fear_greed": None,
        "fear_greed_signal": "N/A",
        "sp500_above_200ma": None,
    }

    try:
        # VIX 데이터 (5일)
        vix = yf.Ticker("^VIX")
        vix_hist = vix.history(period="10d")
        if not vix_hist.empty and len(vix_hist) >= 2:
            vix_value = vix_hist["Close"].iloc[-1]
            vix_prev = vix_hist["Close"].iloc[-2]
            result["vix"] = round(vix_value, 2)

            # VIX 해석
            if vix_value < 15:
                result["vix_signal"] = "낙관 (저변동성)"
            elif vix_value < 20:
                result["vix_signal"] = "정상"
            elif vix_value < 25:
                result["vix_signal"] = "주의 (변동성 상승)"
            elif vix_value < 30:
                result["vix_signal"] = "경계 (고변동성)"
            else:
                result["vix_signal"] = "공포 (극고변동성)"

            # VIX 추세 (급등 후 꺾임 = 매수 기회 신호)
            if vix_value > vix_prev * 1.1:
                result["vix_trend"] = "급등 중 (관망)"
            elif vix_value < vix_prev * 0.9 and vix_prev > 20:
                result["vix_trend"] = "급등 후 하락 (매수 기회)"
            elif vix_value < vix_prev:
                result["vix_trend"] = "하락 중 (안정화)"
            else:
                result["vix_trend"] = "횡보"

            # Fear & Greed Index 추정 (VIX 기반 역산)
            # VIX 10 = Extreme Greed (95), VIX 40 = Extreme Fear (5)
            fear_greed = max(0, min(100, 100 - ((vix_value - 10) / 30) * 100))
            result["fear_greed"] = round(fear_greed, 0)

            if fear_greed >= 75:
                result["fear_greed_signal"] = "극단적 탐욕 (리스크 관리 필요)"
            elif fear_greed >= 55:
                result["fear_greed_signal"] = "탐욕"
            elif fear_greed >= 45:
                result["fear_greed_signal"] = "중립"
            elif fear_greed >= 25:
                result["fear_greed_signal"] = "공포"
            else:
                result["fear_greed_signal"] = "극단적 공포 (매수 기회)"

        # S&P 500 200일선 대비 위치
        sp500 = yf.Ticker("^GSPC")
        sp500_hist = sp500.history(period="1y")
        if not sp500_hist.empty and len(sp500_hist) >= 200:
            sp500_price = sp500_hist["Close"].iloc[-1]
            sp500_200ma = sp500_hist["Close"].iloc[-200:].mean()
            result["sp500_above_200ma"] = sp500_price > sp500_200ma

    except Exception as e:
        print(f"  [!!] 시장 심리 지표 수집 실패 (yfinance): {e}")

    return result


def fetch_market_sentiment() -> dict:
    """VIX 및 시장 심리 지표 수집 (Twelve Data 우선, yfinance fallback)"""
    # Twelve Data 시도
    if TWELVEDATA_API_KEY:
        result = fetch_market_sentiment_twelvedata()
        if result.get("vix") is not None:
            print(f"  [OK] Twelve Data로 시장 심리 수집 완료")
            return result
        print(f"  [..] Twelve Data 실패, yfinance fallback...")

    # yfinance fallback
    return fetch_market_sentiment_yfinance()


_MOMENTUM_PROMPT = """당신은 모멘텀 투자 전문가입니다. "예측이 아닌 대응" 원칙으로 분석하세요.
"가장 물살이 센 곳(거래대금)에서, 엔진이 튼튼한 배(실적/해자)를 타고, 바람의 방향(기술적 추세)에 맞춰 돛을 올리는" 전략입니다.

[종목 정보]
티커: {ticker}
회사명(영문): {name}
회사명(한글, TTS용): {korean_name}
섹터: {sector}

[기술적 데이터]
- 현재가: ${price}
- 50일선: ${ma_50} / 200일선: ${ma_200}
- MA 정배열: {ma_alignment}
- RSI: {rsi} ({rsi_signal})
- 이격도 (50일선): {disparity_50}% ({disparity_signal})
- 베타: {beta} ({beta_signal})
- 52주 고점 대비: {from_high_pct}%
- 거래량: 평균 대비 {volume_ratio}배

[펀더멘털 데이터]
- 시가총액: {market_cap_str}
- PER: {pe_ratio} / PEG: {peg_ratio} ({peg_signal})
- EPS 성장률: {eps_growth}% vs 매출 성장률: {revenue_growth}% ({growth_quality})
- Gross Margin: {gross_margin}% ({gross_margin_trend})
- Operating Margin: {operating_margin}%
- Rule of 40: {rule_of_40}% ({rule_of_40_signal})
- Free Cash Flow: {fcf_str}
- ROIC: {roic}%

[시장 환경]
- VIX: {vix} ({vix_signal}) - 추세: {vix_trend}
- Fear & Greed: {fear_greed} ({fear_greed_signal})
- S&P 500 200일선 위: {sp500_trend}

[분석 지침]
1. RSI 70~80 이상 과매수 구간에서는 신규 진입 자제, 조정 대기 권고
2. 이격도가 과열이면 기술적 조정 가능성 언급
3. 베타가 높으면 하락장 변동성 위험 경고
4. Rule of 40이 40% 이상이면 플랫폼/소프트웨어 기업의 건전성 양호
5. FCF 양호 + ROIC 높음 = 경제적 해자(Moat) 가능성
6. Fear & Greed 75 이상 = 시장 과열, 현금 비중 확대 권고
7. VIX 급등 후 꺾임 = 저가 매수 기회 신호

반드시 JSON 형식으로만 답변하세요:
{{
    "technical_summary": "기술적 분석 요약 (2-3문장, 한국어). RSI 과열/이격도/베타 위험 포함",
    "fundamental_summary": "펀더멘털 분석 요약 (2-3문장, 한국어). Rule of 40, FCF, 영업 레버리지 포함",
    "moat_analysis": "경제적 해자 분석 (1-2문장). 비용우위/무형자산/전환비용/네트워크효과/규모의 경제 중 해당 사항",
    "catalyst": ["상승 촉매 요인 1", "상승 촉매 요인 2"],
    "risk_factors": ["리스크 요인 1 (베타/변동성 포함)", "리스크 요인 2"],
    "trading_strategy": {{
        "signal": "매수 또는 관망 또는 매도",
        "entry_point": "진입 포인트 (예: $180 50일선 지지)",
        "stop_loss": "손절 라인 (50일선 이탈 기준)",
        "target": "목표가 (예: $200 신고가 돌파)",
        "position_size": "비중 제안 (예: 전체 포트폴리오의 5~10%)"
    }},
    "verdict": "강력매수 또는 매수 또는 관망 또는 매도",
    "confidence": "높음 또는 중간 또는 낮음",
    "narration": "나레이션은 별도 생성됩니다. 이 필드는 빈 문자열로 두세요."
}}
"""

# 나레이션 파트1: 인트로 + 매출/성장 분석 (Manim Scene 1과 동기화)
_NARRATION_PART1_PROMPT = """당신은 데이터 기반 주식 분석 유튜브 채널의 앵커입니다.
영상에서 매출 성장 막대그래프가 보여지는 동안 읽을 나레이션입니다.

★★★ 조사 사용 규칙 (필수) ★★★
- 받침 있는 글자 뒤: 은, 이, 을, 과, 으로 (예: "성장은", "실적이")
- 받침 없는 글자 뒤: 는, 가, 를, 와, 로 (예: "{korean_name}는", "주가가")
- 반드시 앞 글자의 받침 유무를 확인하고 올바른 조사를 사용하세요.

[종목 정보]
회사명(한글): {korean_name}
섹터: {sector}
현재가: ${price}
52주 고점 대비: {from_high_pct}%
투자 판단: {verdict}
매출 성장률: 데이터센터/AI 부문 급성장 중

★★★ 반드시 350자 이상 420자 이하로 작성 ★★★

[Scene 1: 인트로 + 매출 성장 - 약 40초]

(인트로 - 5초)
도발적 질문으로 시작: "{korean_name}, 거품일까요? 아니면 이제 시작일까요? 오늘 숫자로 증명해 드립니다."

(매출 막대그래프 설명 - 35초)
"먼저 {korean_name}의 매출 성장을 보겠습니다."

★ 영상과 동기화될 내용 ★
- 매출이 어떻게 성장해왔는지 (막대그래프가 솟아오르는 장면)
- 핵심 성장 동력이 무엇인지 (데이터센터, AI, 게이밍 등)
- 전체 매출에서 핵심 사업이 차지하는 비중
- 이 성장세가 왜 중요한지

예시: "2021년부터 2025년까지 매출 추이를 보시죠. 특히 주목할 점은 데이터센터 매출입니다. 초록색 영역이 데이터센터인데, 전체 매출의 80%를 넘어섰습니다. AI 수요 폭발이 {korean_name}의 실적을 끌어올리고 있습니다."

★ 필수 규칙 ★
1. '{korean_name}' 뒤에 조사는 받침 확인 후 사용 (예: 엔비디아→받침없음→"는/가/를/로")
2. 숫자를 구체적으로 언급
3. 영상에서 보이는 내용을 설명하는 느낌으로

나레이션만 출력:"""

# 나레이션 파트2: EPS vs 주가 + 결론 (Manim Scene 2, 3과 동기화)
_NARRATION_PART2_PROMPT = """당신은 데이터 기반 주식 분석 유튜브 채널의 앵커입니다.
영상에서 EPS vs 주가 그래프, 그리고 결론 화면이 보여지는 동안 읽을 나레이션입니다.

★★★ 조사 사용 규칙 (필수) ★★★
- 받침 있는 글자 뒤: 은, 이, 을, 과, 으로 (예: "성장은", "실적이")
- 받침 없는 글자 뒤: 는, 가, 를, 와, 로 (예: "엔비디아는", "주가가", "애플을")

[종목 정보]
회사명(한글): {korean_name}
PER: {pe_ratio}배 / PEG: {peg_ratio} ({peg_signal})
EPS 성장률: {eps_growth}%
영업이익률: {operating_margin}%
Rule of 40: {rule_of_40}% ({rule_of_40_signal})

[투자 전략]
신호: {signal}
진입가: {entry_point}
손절라인: {stop_loss}
목표가: {target}

[리스크/촉매]
리스크: {risk_factors}
촉매: {catalyst}

★★★ 반드시 400자 이상 480자 이하로 작성 ★★★

[Scene 2: EPS vs 주가 그래프 - 약 35초]

"그렇다면 {korean_name} 주가는 거품일까요?"로 시작.

★ 영상: 녹색 선(주가)과 금색 선(EPS)이 함께 상승하는 그래프 ★
- "화면을 보세요. 녹색 선이 주가, 금색 선이 이익입니다."
- "두 선이 나란히 올라가고 있습니다. 주가가 오른 만큼 이익도 따라왔다는 뜻이죠."
- "PER {pe_ratio}배, 숫자만 보면 비싸 보입니다."
- "하지만 PEG를 확인해보죠. PEG는 PER을 성장률로 나눈 값입니다. 1 이하면 저평가, 2 이상이면 고평가인데, 현재 {peg_ratio}로 {peg_signal}입니다."

[Scene 3: 결론 화면 - 약 25초]

"정리하겠습니다."로 시작.

★ 영상: "거품이 아닙니다. 이익입니다." 텍스트 + 로고 ★
- 핵심 한 줄: 거품인지 아닌지 결론
- 투자 의견: {signal}
- 매매 전략: 진입가, 손절, 목표가
- CTA: "여러분의 평단가는 얼마인가요? 댓글로 알려주세요."
- 마무리: "숫자는 거짓말하지 않습니다."

★ 필수 규칙 ★
1. 조사 정확히 사용 (받침 유무 확인)
2. 영상 화면을 설명하는 느낌
3. CTA 필수

나레이션만 출력:"""


def _generate_narration_part(prompt: str, min_chars: int = 450) -> str:
    """나레이션 파트 생성 (재시도 포함)"""
    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1000,
    }

    narration = ""
    for attempt in range(1, 4):
        try:
            r = requests.post(_URL, headers=_HEADERS, json=payload, timeout=60)
            if r.status_code == 200:
                narration = r.json()["choices"][0]["message"]["content"].strip()
                if len(narration) >= min_chars:
                    return narration
                print(f"  [..] 파트 {len(narration)}자 부족, 재생성...")
                time.sleep(2)
            elif r.status_code == 429:
                print(f"  [..] Groq 한도, 30초 대기...")
                time.sleep(30)
            else:
                print(f"  [!!] Groq 오류: {r.status_code}")
                break
        except Exception as e:
            print(f"  [!!] 나레이션 생성 실패: {e}")
            break

    return narration


def generate_momentum_analysis(stock_data: dict, market: dict) -> dict | None:
    """Groq AI로 모멘텀 분석 생성"""
    tech = stock_data["technical"]
    fund = stock_data["fundamental"]

    # 시가총액 포맷
    mc = fund["market_cap"]
    if mc >= 1e12:
        market_cap_str = f"${mc / 1e12:.1f}T"
    elif mc >= 1e9:
        market_cap_str = f"${mc / 1e9:.1f}B"
    else:
        market_cap_str = f"${mc / 1e6:.1f}M"

    # FCF 포맷 (주당 잉여현금흐름)
    fcf_per_share = fund.get("fcf_per_share")
    if fcf_per_share:
        fcf_str = f"{fcf_per_share:.2f}"
    else:
        fcf_str = "N/A"

    # S&P 500 추세
    sp500_trend = "상승 추세" if market.get("sp500_above_200ma") else "하락 추세" if market.get("sp500_above_200ma") is False else "N/A"

    # 한글 회사명 (TTS용)
    ticker = stock_data["ticker"]
    korean_name = COMPANY_NAMES.get(ticker, stock_data["name"])

    prompt = _MOMENTUM_PROMPT.format(
        ticker=ticker,
        name=stock_data["name"],
        korean_name=korean_name,
        sector=stock_data["sector"],
        price=tech["price"],
        ma_50=tech["ma_50"],
        ma_200=tech["ma_200"],
        ma_alignment="O (정배열)" if tech["ma_alignment"] else "X (역배열)",
        rsi=tech["rsi"],
        rsi_signal=tech["rsi_signal"],
        disparity_50=tech.get("disparity_50", "N/A"),
        disparity_signal=tech.get("disparity_signal", "N/A"),
        beta=tech.get("beta") or "N/A",
        beta_signal=tech.get("beta_signal", "N/A"),
        from_high_pct=tech["from_high_pct"],
        volume_ratio=tech["volume_ratio"],
        market_cap_str=market_cap_str,
        pe_ratio=fund["pe_ratio"] or "N/A",
        peg_ratio=fund["peg_ratio"] or "N/A",
        peg_signal=fund["peg_signal"],
        eps_growth=fund["eps_growth"] or "N/A",
        revenue_growth=fund["revenue_growth"] or "N/A",
        growth_quality=fund["growth_quality"],
        gross_margin=fund["gross_margin"] or "N/A",
        gross_margin_trend=fund["gross_margin_trend"],
        operating_margin=fund["operating_margin"] or "N/A",
        rule_of_40=fund.get("rule_of_40") or "N/A",
        rule_of_40_signal=fund.get("rule_of_40_signal", "N/A"),
        fcf_str=fcf_str,
        roic=fund.get("roic") or "N/A",
        vix=market.get("vix") or "N/A",
        vix_signal=market.get("vix_signal", "N/A"),
        vix_trend=market.get("vix_trend", "N/A"),
        fear_greed=market.get("fear_greed") or "N/A",
        fear_greed_signal=market.get("fear_greed_signal", "N/A"),
        sp500_trend=sp500_trend,
    )

    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 3000,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.post(_URL, headers=_HEADERS, json=payload, timeout=60)

            if r.status_code == 200:
                raw = r.json()["choices"][0]["message"]["content"]
                result = json.loads(raw)

                # 기본값 설정
                result.setdefault("technical_summary", "")
                result.setdefault("fundamental_summary", "")
                result.setdefault("moat_analysis", "")
                result.setdefault("catalyst", [])
                result.setdefault("risk_factors", [])
                result.setdefault("trading_strategy", {
                    "signal": "관망",
                    "entry_point": "N/A",
                    "stop_loss": "N/A",
                    "target": "N/A",
                    "position_size": "N/A",
                })
                result.setdefault("verdict", "관망")
                result.setdefault("confidence", "중간")
                result.setdefault("narration", "")

                # 나레이션 2파트 생성
                print(f"  [>>] 나레이션 파트1 생성 중...")
                strategy = result.get("trading_strategy", {})

                part1_prompt = _NARRATION_PART1_PROMPT.format(
                    korean_name=korean_name,
                    sector=stock_data["sector"],
                    price=tech["price"],
                    ma_50=tech["ma_50"],
                    ma_200=tech["ma_200"],
                    ma_alignment="정배열(상승추세)" if tech["ma_alignment"] else "역배열(하락추세)",
                    rsi=tech["rsi"],
                    rsi_signal=tech["rsi_signal"],
                    disparity_50=tech.get("disparity_50", "N/A"),
                    disparity_signal=tech.get("disparity_signal", "N/A"),
                    beta=tech.get("beta") or "N/A",
                    beta_signal=tech.get("beta_signal", "N/A"),
                    from_high_pct=tech["from_high_pct"],
                    verdict=result.get("verdict", "관망"),
                )
                part1 = _generate_narration_part(part1_prompt, min_chars=350)
                part1 = _postprocess_narration(part1, stock_data["ticker"])

                print(f"  [>>] 나레이션 파트2 생성 중...")
                time.sleep(1)

                # 리스크/촉매를 문자열로 변환
                risk_str = ", ".join(result.get("risk_factors", ["N/A"])[:2])
                catalyst_str = ", ".join(result.get("catalyst", ["N/A"])[:2])

                part2_prompt = _NARRATION_PART2_PROMPT.format(
                    korean_name=korean_name,
                    market_cap_str=market_cap_str,
                    pe_ratio=fund["pe_ratio"] or "N/A",
                    peg_ratio=fund["peg_ratio"] or "N/A",
                    peg_signal=fund["peg_signal"],
                    eps_growth=fund["eps_growth"] or "N/A",
                    revenue_growth=fund["revenue_growth"] or "N/A",
                    operating_margin=fund["operating_margin"] or "N/A",
                    rule_of_40=fund.get("rule_of_40") or "N/A",
                    rule_of_40_signal=fund.get("rule_of_40_signal", "N/A"),
                    fcf_str=fcf_str,
                    roic=fund.get("roic") or "N/A",
                    risk_factors=risk_str,
                    catalyst=catalyst_str,
                    signal=strategy.get("signal", "관망"),
                    entry_point=strategy.get("entry_point", "N/A"),
                    stop_loss=strategy.get("stop_loss", "N/A"),
                    target=strategy.get("target", "N/A"),
                    position_size=strategy.get("position_size", "N/A"),
                )
                part2 = _generate_narration_part(part2_prompt, min_chars=350)
                part2 = _postprocess_narration(part2, stock_data["ticker"])

                # 나레이션 합치기
                result["narration"] = part1 + " " + part2
                print(f"  [OK] 나레이션 완료: {len(result['narration'])}자")

                return result

            elif r.status_code == 429:
                if attempt == _MAX_RETRIES:
                    print(f"  [!!] Groq 한도 초과")
                    return None
                wait = 30 * attempt
                print(f"  [!!] Groq 한도, {wait}초 대기 후 재시도 ({attempt}/{_MAX_RETRIES})...")
                time.sleep(wait)
            else:
                print(f"  [!!] Groq API 오류 {r.status_code}: {r.text[:200]}")
                return None

        except Exception as e:
            print(f"  [!!] Groq 요청 실패: {e}")
            return None

    return None


def analyze_stock(ticker: str) -> dict | None:
    """
    종목 모멘텀 분석 전체 파이프라인

    Returns:
        {
            "stock_data": { ... },
            "market": { ... },
            "analysis": { ... },
        }
    """
    print(f"\n[Stock Analysis] {ticker} 분석 시작")

    # 1. 종목 데이터 수집
    print(f"  [>>] {ticker} 데이터 수집 중...")
    stock_data = fetch_stock_data(ticker)
    if not stock_data:
        return None
    tech = stock_data['technical']
    fund = stock_data['fundamental']
    print(f"  [OK] {stock_data['name']} ({stock_data['sector']})")
    print(f"      가격: ${tech['price']} | RSI: {tech['rsi']} ({tech['rsi_signal']})")
    print(f"      MA정배열: {tech['ma_alignment']} | 이격도: {tech['disparity_50']}% | 베타: {tech.get('beta', 'N/A')}")
    if fund.get('rule_of_40'):
        print(f"      Rule of 40: {fund['rule_of_40']}% ({fund['rule_of_40_signal']})")

    # 2. 시장 심리 수집
    print(f"  [>>] 시장 심리 지표 수집 중...")
    market = fetch_market_sentiment()
    print(f"  [OK] VIX: {market['vix']} ({market['vix_signal']}) | Fear&Greed: {market.get('fear_greed', 'N/A')}")

    # 3. AI 분석
    print(f"  [>>] AI 모멘텀 분석 중...")
    analysis = generate_momentum_analysis(stock_data, market)
    if not analysis:
        print(f"  [!!] AI 분석 실패")
        return None
    print(f"  [OK] 판정: {analysis['verdict']} (신뢰도: {analysis['confidence']})")
    print(f"      신호: {analysis['trading_strategy']['signal']}")

    return {
        "stock_data": stock_data,
        "market": market,
        "analysis": analysis,
    }


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    result = analyze_stock(ticker)
    if result:
        print("\n=== 분석 결과 ===")
        print(json.dumps(result["analysis"], indent=2, ensure_ascii=False))
