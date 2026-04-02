"""
Groq REST API로 뉴스에서 관련 종목을 추출하고 주가 영향을 분석합니다.
SDK 대신 requests 직접 호출 (Python 3.14 호환)
무료 티어: 하루 14,400회
"""
import json
import time
import requests
from config import GROQ_API_KEY

_MODEL = "llama-3.3-70b-versatile"
_URL = "https://api.groq.com/openai/v1/chat/completions"
_HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json",
}
_MAX_RETRIES = 3

_PROMPT = """다음 미국 주식 시장 뉴스를 분석해줘. 반드시 JSON 형식으로만 답변해. 다른 텍스트 없이 JSON만 출력해.

뉴스 제목: {headline}
뉴스 내용: {summary}
{body_section}
{{
  "tickers": ["이 뉴스에서 직접 언급되거나 가장 영향을 받는 미국 주식 티커 심볼 목록 (최대 3개, 없으면 빈 배열)"],
  "companies": ["해당 티커의 한국어 회사명 목록 (tickers와 순서 동일)"],
  "companies_en": ["해당 티커의 영어 공식 회사명 목록 (tickers와 순서 동일, 예: Apple Inc., NVIDIA Corporation)"],
  "summary": "한국 주식 투자자를 위한 3줄 이내 핵심 요약 (한국어)",
  "impact": "긍정 또는 부정 또는 중립",
  "reason": "주가에 미치는 영향과 이유 1~2문장 (한국어)",
  "importance_score": "1~10 정수. 채점 기준: Fed/금리/CPI 등 매크로=9~10, 어닝서프라이즈/가이던스=8~9, M&A/대형 계약=7~8, 경영진 교체/소송=6~7, 일반 분석/의견=1~5",
  "x_post": "X(트위터) 발행용 텍스트. 형식: 이모지+핵심내용 2~3줄+관련해시태그. 280자 이내 한국어"
}}"""


def analyze_article(headline: str, summary: str, body: str = "") -> dict:
    body_section = f"기사 본문:\n{body[:4000]}" if body else ""
    prompt = _PROMPT.format(headline=headline, summary=summary or headline, body_section=body_section)
    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        r = requests.post(_URL, headers=_HEADERS, json=payload, timeout=60)

        if r.status_code == 200:
            raw = r.json()["choices"][0]["message"]["content"]
            break
        elif r.status_code == 429:
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"Groq 한도 초과: {r.text[:200]}")
            wait = 30 * attempt
            print(f"  [!!] Groq 한도, {wait}초 대기 후 재시도 ({attempt}/{_MAX_RETRIES})...")
            time.sleep(wait)
        else:
            raise RuntimeError(f"Groq API 오류 {r.status_code}: {r.text[:200]}")

    result = json.loads(raw)
    result.setdefault("tickers", [])
    result.setdefault("companies", [])
    result.setdefault("companies_en", [])
    result.setdefault("impact", "중립")
    result.setdefault("importance_score", 5)
    result.setdefault("x_post", result.get("summary", ""))
    result["importance_score"] = int(result["importance_score"])
    return result


_NARRATION_SHORTS = """당신은 한국 주식·경제 유튜브 Shorts 전문 나레이터입니다.
아래 뉴스를 바탕으로 60초 분량의 나레이션을 작성하세요.

[뉴스 제목] {headline}
[뉴스 요약] {summary}
[기사 본문] {body}
[종목] {tickers} / [영향] {impact} / [이유] {reason}

규칙:
1. 반드시 280~320자로 작성 (너무 짧으면 안 됨!)
2. 구성:
   - 후킹 (1문장): 시청자 관심을 끄는 강렬한 도입
   - 핵심 내용 (3~4문장): 무슨 일이 있었는지, 구체적 수치/사실 포함
   - 시장 영향 (1~2문장): 왜 중요한지, 어떤 영향이 있는지
   - 투자자 시사점 (1문장): 투자자가 주목할 포인트
3. 한국어 구어체, 뉴스 앵커처럼 또박또박
4. 회사명은 한국어로 (엔비디아, 테슬라, 애플 등)
5. 나레이션 텍스트만 출력

예시 (약 300자):
"엔비디아가 또 한 번 월가를 놀라게 했습니다. 2분기 매출이 300억 달러를 돌파하며 시장 예상치를 20% 이상 상회했는데요. 전년 동기 대비 무려 122% 증가한 수치입니다. AI 반도체 수요가 여전히 폭발적이라는 걸 다시 한번 증명한 셈이죠. 데이터센터 매출만 263억 달러로, 전체의 87%를 차지했습니다. 다만 주가가 이미 많이 오른 만큼 밸류에이션 부담은 커졌습니다. 단기 변동성에 유의하면서 AI 투자 흐름을 지켜보시기 바랍니다."
"""


def _call_groq(prompt: str, temperature: float = 0.7) -> str:
    payload = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 2048,
    }
    for attempt in range(1, _MAX_RETRIES + 1):
        r = requests.post(_URL, headers=_HEADERS, json=payload, timeout=60)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        elif r.status_code == 429:
            if attempt == _MAX_RETRIES:
                return ""
            wait = 30 * attempt
            print(f"  [!!] Groq 한도, {wait}초 대기 ({attempt}/{_MAX_RETRIES})...")
            time.sleep(wait)
        else:
            return ""
    return ""


def generate_narration(headline: str, summary: str, body: str, analysis: dict) -> str:
    """60초 Shorts용 300~350자 나레이션을 1회 Groq 호출로 생성합니다."""
    tickers_str = ", ".join(analysis.get("tickers", [])) or "시장 전반"
    impact = analysis.get("impact", "중립")
    reason = analysis.get("reason", "")

    narration = _call_groq(_NARRATION_SHORTS.format(
        headline=headline,
        summary=summary or headline,
        body=body[:2000] if body else "본문 없음",
        tickers=tickers_str,
        impact=impact,
        reason=reason,
    ))

    if not narration:
        narration = analysis.get("summary", headline)
    return narration
