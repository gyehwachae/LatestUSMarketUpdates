"""
뉴스 기사 URL에서 본문과 이미지를 추출합니다.
trafilatura로 1차 시도, 실패 시 BeautifulSoup으로 fallback.
DeepL 무료 한도 보호를 위해 최대 4000자까지만 반환합니다.
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

_MAX_CHARS = 4000
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _extract_image_url(soup: BeautifulSoup, base_url: str) -> str:
    """메타 태그 또는 본문에서 대표 이미지 URL을 추출합니다."""
    # 1순위: Open Graph 이미지
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"]

    # 2순위: Twitter 카드 이미지
    tw_image = soup.find("meta", attrs={"name": "twitter:image"})
    if tw_image and tw_image.get("content"):
        return tw_image["content"]

    # 3순위: article 또는 main 내 첫 번째 큰 이미지
    for container in soup.find_all(["article", "main", "div"], class_=lambda x: x and "content" in str(x).lower()):
        img = container.find("img", src=True)
        if img:
            src = img.get("src", "")
            if src and not any(x in src.lower() for x in ["logo", "icon", "avatar", "button"]):
                return urljoin(base_url, src)

    return ""


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
        print(f"  [!!] 기사 본문 추출 실패: {e}")
        return ""


def fetch_article_with_image(url: str) -> tuple[str, str]:
    """
    기사 URL에서 본문 텍스트와 대표 이미지 URL을 추출합니다.
    반환: (본문, 이미지URL) - 실패 시 빈 문자열
    """
    if not url:
        return "", ""

    body = ""
    image_url = ""

    try:
        r = requests.get(url, headers=_HEADERS, timeout=10)
        r.raise_for_status()
        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # 이미지 추출
        image_url = _extract_image_url(soup, url)

        # 본문 추출: trafilatura 우선
        if _HAS_TRAFILATURA:
            text = trafilatura.extract(html, include_comments=False, include_tables=False)
            if text and len(text) > 100:
                body = text[:_MAX_CHARS]

        # trafilatura 실패 시 BeautifulSoup fallback
        if not body:
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            body = " ".join(p for p in paragraphs if len(p) > 40)[:_MAX_CHARS]

    except Exception as e:
        print(f"  [!!] 기사 추출 실패: {e}")

    return body, image_url
