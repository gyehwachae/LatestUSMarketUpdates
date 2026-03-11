"""
뉴스 기사 URL에서 본문을 추출합니다.
trafilatura로 1차 시도, 실패 시 BeautifulSoup으로 fallback.
DeepL 무료 한도 보호를 위해 최대 2000자까지만 반환합니다.
"""
import requests
from bs4 import BeautifulSoup

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

_MAX_CHARS = 2000
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_article_body(url: str) -> str:
    """
    기사 URL에서 본문 텍스트를 추출합니다.
    실패 시 빈 문자열을 반환합니다.
    """
    if not url:
        return ""

    try:
        # 1차: trafilatura (정확도 높음)
        if _HAS_TRAFILATURA:
            downloaded = trafilatura.fetch_url(url)
            text = trafilatura.extract(downloaded, include_comments=False,
                                       include_tables=False)
            if text and len(text) > 100:
                return text[:_MAX_CHARS]

        # 2차: BeautifulSoup fallback
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        text = " ".join(p for p in paragraphs if len(p) > 40)
        return text[:_MAX_CHARS]

    except Exception as e:
        print(f"  ⚠ 기사 본문 추출 실패: {e}")
        return ""
