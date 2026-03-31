# -*- coding: utf-8 -*-
"""
메인 파이프라인:
  모든 뉴스 -> 번역 -> Groq 분석
  importance_score >= YOUTUBE_MIN_IMPORTANCE -> 영상 제작 -> YouTube 업로드

폴링 간격 (KST 기준):
  06:00~10:00 -> 1분  (기상 후 핵심 시간)
  21:00~24:00 -> 2분  (프리마켓)
  00:00~06:00 -> 10분 (미국 정규장, 속보만)
  10:00~21:00 -> 30분 (낮, 뉴스 적음)
"""
import time
import traceback
from datetime import datetime, timezone, timedelta

from config import NEWS_CATEGORY, YOUTUBE_MIN_IMPORTANCE, ARTICLE_DELAY_SECONDS
from modules.news_collector import fetch_new_articles, mark_as_processed
from modules.translator import translate_to_korean
from modules.analyzer import analyze_article
from modules.article_scraper import fetch_article_body
from modules.video_maker import create_video
from modules.uploader import build_metadata, upload_video

KST = timezone(timedelta(hours=9))

# KST 시간대별 폴링 간격 (초): [(시작시, 끝시, 간격초), ...]
_SCHEDULE = [
    (6,  10, 60),    # 아침: 1분
    (21, 24, 120),   # 저녁 프리마켓: 2분
    (0,   6, 600),   # 새벽 정규장: 10분
    (10, 21, 1800),  # 낮: 30분
]


def get_poll_interval() -> int:
    hour = datetime.now(KST).hour
    for start, end, interval in _SCHEDULE:
        if start <= hour < end:
            return interval
    return 1800


def process_article(article: dict):
    headline_en = article.get("headline", "")
    summary_en  = article.get("summary", "")
    article_url = article.get("url", "")
    image_url   = article.get("image", "")

    print(f"\n[Pipeline] 처리 중: {headline_en[:80]}...")

    # 1. 번역 (헤드라인 + 전체 기사 본문)
    headline_kr = translate_to_korean(headline_en)
    print(f"  [OK] 번역: {headline_kr[:60]}...")

    body_en = fetch_article_body(article_url)
    full_text_kr = translate_to_korean(body_en) if body_en else None
    if full_text_kr:
        print(f"  [OK] 본문 번역: {len(full_text_kr)}자")

    # 2. 분석
    analysis = analyze_article(headline_en, summary_en)
    score = analysis.get("importance_score", 5)
    tickers = analysis.get("tickers", [])
    ticker_str = ", ".join(tickers) if tickers else "시장 전반"
    print(f"  [OK] 분석: 종목={ticker_str}, 영향={analysis.get('impact')}, 중요도={score}/10")

    # 3. YouTube: 중요도 기준 이상일 때만 영상 제작 + 업로드
    if score >= YOUTUBE_MIN_IMPORTANCE:
        print(f"  [>>] 중요도 {score} >= {YOUTUBE_MIN_IMPORTANCE}: 영상 제작 시작")
        video_path = create_video(headline_kr, analysis,
                                   image_url=image_url,
                                   article_url=article_url,
                                   full_text_kr=full_text_kr)
        print(f"  [OK] 영상: {video_path}")

        title, description, tags = build_metadata(headline_kr, analysis, article_url=article_url)
        video_id = upload_video(video_path, title, description, tags)
        if video_id:
            print(f"  [OK] YouTube: https://youtu.be/{video_id}")
        else:
            print("  [--] YouTube 업로드 건너뜀 (일일 한도)")
    else:
        print(f"  [--] 중요도 {score} < {YOUTUBE_MIN_IMPORTANCE}: 영상 건너뜀")


def run_once():
    now_kst = datetime.now(KST).strftime("%H:%M")
    interval = get_poll_interval()
    print(f"[Pipeline] 뉴스 확인 중 (KST {now_kst}, 다음 폴링: {interval//60}분 후)")

    articles = fetch_new_articles()
    if not articles:
        print("[Pipeline] 새 뉴스 없음.")
        return

    print(f"[Pipeline] 새 뉴스 {len(articles)}건 발견.")
    processed_ids = []

    for i, article in enumerate(articles):
        try:
            process_article(article)
            processed_ids.append(str(article["id"]))
        except RuntimeError as e:
            # 일일 한도 소진 등 복구 불가 오류 → 루프 중단
            print(f"[Pipeline] 중단: {e}")
            break
        except Exception:
            print("[Pipeline] 오류 발생, 건너뜀:")
            traceback.print_exc()
        if i < len(articles) - 1:
            time.sleep(ARTICLE_DELAY_SECONDS)

    if processed_ids:
        mark_as_processed(processed_ids)


def run_loop():
    print("[Pipeline] 루프 시작 (KST 시간대별 자동 조절)")
    while True:
        try:
            run_once()
        except Exception:
            print("[Pipeline] 루프 오류:")
            traceback.print_exc()
        time.sleep(get_poll_interval())


if __name__ == "__main__":
    import sys
    if "--loop" in sys.argv:
        run_loop()
    else:
        run_once()
