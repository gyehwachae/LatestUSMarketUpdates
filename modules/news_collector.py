"""
Finnhub general-news 엔드포인트로 미국 시장 전체 최신 뉴스를 수집합니다.
특정 종목 필터 없이 최신 뉴스 상위 5건을 반환합니다.
"""
import json
import os
import requests
from config import FINNHUB_API_KEY, NEWS_CATEGORY, DATA_DIR

PROCESSED_FILE = os.path.join(DATA_DIR, "processed_news.json")


def _load_processed_ids() -> set:
    if not os.path.exists(PROCESSED_FILE):
        return set()
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def _save_processed_ids(ids: set):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f)


def fetch_new_articles() -> list[dict]:
    """
    Finnhub market-news 엔드포인트에서 최신 뉴스를 가져옵니다.
    이미 처리한 기사(id 기준)는 제외하고 최신순 5건을 반환합니다.
    """
    url = "https://finnhub.io/api/v1/news"
    params = {
        "category": NEWS_CATEGORY,
        "token": FINNHUB_API_KEY,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    articles = response.json()

    processed_ids = _load_processed_ids()
    new_articles = [a for a in articles if str(a["id"]) not in processed_ids]

    new_articles.sort(key=lambda x: x["datetime"], reverse=True)
    return new_articles[:5]


def mark_as_processed(article_ids: list[str]):
    processed_ids = _load_processed_ids()
    processed_ids.update(article_ids)
    _save_processed_ids(processed_ids)
