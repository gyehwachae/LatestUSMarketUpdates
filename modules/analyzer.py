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

{{
  "tickers": ["이 뉴스에서 직접 언급되거나 가장 영향을 받는 미국 주식 티커 심볼 목록 (최대 3개, 없으면 빈 배열)"],
  "companies": ["해당 티커의 한국어 회사명 목록 (tickers와 순서 동일)"],
  "companies_en": ["해당 티커의 영어 공식 회사명 목록 (tickers와 순서 동일, 예: Apple Inc., NVIDIA Corporation)"],
  "summary": "한국 주식 투자자를 위한 3줄 이내 핵심 요약 (한국어)",
  "impact": "긍정 또는 부정 또는 중립",
  "reason": "주가에 미치는 영향과 이유 1~2문장 (한국어)",
  "importance_score": "1~10 정수. 채점 기준: Fed/금리/CPI 등 매크로=9~10, 어닝서프라이즈/가이던스=8~9, M&A/대형 계약=7~8, 경영진 교체/소송=6~7, 일반 분석/의견=1~5",
  "script": "유튜브 쇼츠용 나레이션 (한국어 구어체, 200자 이내, 종목명 언급 포함)",
  "x_post": "X(트위터) 발행용 텍스트. 형식: 이모지+핵심내용 2~3줄+관련해시태그. 280자 이내 한국어"
}}"""


def analyze_article(headline: str, summary: str) -> dict:
    prompt = _PROMPT.format(headline=headline, summary=summary or headline)
    body = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        r = requests.post(_URL, headers=_HEADERS, json=body, timeout=30)

        if r.status_code == 200:
            raw = r.json()["choices"][0]["message"]["content"]
            break
        elif r.status_code == 429:
            if attempt == _MAX_RETRIES:
                raise RuntimeError(f"Groq 한도 초과: {r.text[:200]}")
            wait = 30 * attempt
            print(f"  ⚠ Groq 한도, {wait}초 대기 후 재시도 ({attempt}/{_MAX_RETRIES})...")
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
