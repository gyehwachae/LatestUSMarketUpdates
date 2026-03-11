"""
뉴스 수집만 테스트 (API 키 소모 없음)
"""
import json
from modules.news_collector import fetch_new_articles

articles = fetch_new_articles()

if not articles:
    print("새 뉴스 없음 (이미 처리된 기사만 있거나 API 오류)")
else:
    print(f"뉴스 {len(articles)}건 수집\n")
    for i, a in enumerate(articles, 1):
        print(f"[{i}] {a.get('headline', '')}")
        print(f"     출처: {a.get('source', '')} | {a.get('url', '')[:60]}")
        print()
