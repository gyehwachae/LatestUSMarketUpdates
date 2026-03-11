"""
DeepL Free API로 영문 뉴스를 한글로 번역합니다.
월 50만 자 무료.
"""
import deepl
from config import DEEPL_API_KEY


_client = None


def _get_client() -> deepl.Translator:
    global _client
    if _client is None:
        _client = deepl.Translator(DEEPL_API_KEY)
    return _client


def translate_to_korean(text: str) -> str:
    """영문 텍스트를 한국어로 번역합니다."""
    if not text or not text.strip():
        return ""
    result = _get_client().translate_text(text, target_lang="KO")
    return result.text
