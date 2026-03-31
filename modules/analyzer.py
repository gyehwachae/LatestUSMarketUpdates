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


_NARRATION_PART1 = """당신은 한국 주식·경제 유튜브 채널 전문 나레이터입니다.
아래 뉴스를 바탕으로 나레이션 스크립트 전반부(1·2단락)를 작성하세요.

[뉴스 제목] {headline}
[뉴스 요약] {summary}
[기사 본문] {body}
[종목] {tickers} / [영향] {impact}

단락1(기, 700자 이상): 이 뉴스의 배경과 현황 소개. 왜 이 뉴스가 중요한지, 관련 산업 흐름, 기업 배경, 시장 상황 포함.
단락2(승, 700자 이상): 핵심 사건과 세부 내용 전개. 구체적 수치, 발언, 관련 인물·기업·기관 반응 포함.

규칙: 한국어 구어체만 사용. 단락 번호나 태그 없이 자연스럽게 연결. 나레이션 텍스트만 출력."""

_NARRATION_PART2 = """당신은 한국 주식·경제 유튜브 채널 전문 나레이터입니다.
아래는 유튜브 나레이션 전반부입니다. 이어서 후반부(3·4단락)를 작성하세요.

[전반부]
{part1}

[뉴스 정보]
종목: {tickers} / 영향: {impact} / 이유: {reason}

단락3(전, 700자 이상): 시장·경제적 영향 분석. 단기·장기 영향, 경쟁사 비교, 전문가·애널리스트 시각, 관련 데이터 포함.
단락4(결, 700자 이상): 투자자 관점 결론·전망. 매수·매도 관점, 리스크 요인, 주목할 지표, 향후 이벤트 포함.

규칙: 한국어 구어체만 사용. 단락 번호나 태그 없이 전반부와 자연스럽게 이어지도록. 후반부 텍스트만 출력."""


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
    """기승전결 구조의 3000자 나레이션을 2번 Groq 호출로 생성합니다."""
    tickers_str = ", ".join(analysis.get("tickers", [])) or "시장 전반"
    impact = analysis.get("impact", "중립")
    reason = analysis.get("reason", "")

    # 1차 호출: 기·승 단락
    part1 = _call_groq(_NARRATION_PART1.format(
        headline=headline,
        summary=summary or headline,
        body=body[:3000] if body else "본문 없음",
        tickers=tickers_str,
        impact=impact,
    ))

    # 2차 호출: 전·결 단락
    part2 = _call_groq(_NARRATION_PART2.format(
        part1=part1[:800],  # 전반부 요약만 전달 (토큰 절약)
        tickers=tickers_str,
        impact=impact,
        reason=reason,
    ))

    narration = (part1 + "\n\n" + part2).strip()
    if not narration:
        narration = analysis.get("summary", headline)
    return narration
