# -*- coding: utf-8 -*-
"""
전체 파이프라인 테스트 (news_collector 기준 최대 5건)
뉴스 수집 -> 본문 스크래핑 -> 번역 -> 분석 -> 영상 제작 -> YouTube 업로드
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
from dotenv import load_dotenv
load_dotenv()

from modules.news_collector import fetch_new_articles, mark_as_processed
from modules.translator import translate_to_korean
from modules.analyzer import analyze_article, generate_narration
from modules.article_scraper import fetch_article_with_image
from modules.video_maker import create_video
from modules.uploader import build_metadata, upload_video
from config import ARTICLE_DELAY_SECONDS, YOUTUBE_MIN_IMPORTANCE

print("=" * 60)
print("뉴스 수집")
print("=" * 60)
articles = fetch_new_articles()
print(f"새 기사 {len(articles)}건 발견")

if not articles:
    print("처리할 새 기사가 없습니다.")
    sys.exit(0)

processed_ids = []

for idx, article in enumerate(articles, 1):
    headline_en = article.get("headline", "")
    summary_en  = article.get("summary", "")
    article_url = article.get("url", "")
    image_url   = article.get("image", "")

    print(f"\n{'=' * 60}")
    print(f"[{idx}/{len(articles)}] {headline_en[:80]}")
    print("=" * 60)

    try:
        # 1. 번역 + 본문 수집
        headline_kr = translate_to_korean(headline_en)
        print(f"헤드라인(한): {headline_kr}")

        body_en, scraped_image = fetch_article_with_image(article_url)
        if body_en:
            print(f"본문 추출: {len(body_en)}자 (영문)")
        else:
            print("본문 추출 실패 - Groq 스크립트로 대체")

        # Finnhub 이미지가 없으면 스크래핑한 이미지 사용
        if not image_url and scraped_image:
            image_url = scraped_image
            print(f"기사 이미지 추출: {image_url[:60]}...")

        # 2. 분석
        analysis = analyze_article(headline_en, summary_en, body=body_en or "")
        score = analysis.get("importance_score", 5)
        tickers = analysis.get("tickers", [])
        print(f"종목: {', '.join(tickers) or '시장 전반'}  |  영향: {analysis.get('impact')}  |  중요도: {score}/10")
        print(json.dumps(analysis, ensure_ascii=False, indent=2))

        # 3. 영상 제작 + YouTube 업로드
        youtube_url = None
        if score >= YOUTUBE_MIN_IMPORTANCE:
            print(f"중요도 {score} >= {YOUTUBE_MIN_IMPORTANCE}: 나레이션 생성 중...")
            narration = generate_narration(headline_en, summary_en, body_en or "", analysis)
            analysis["narration"] = narration
            print(f"나레이션: {len(narration)}자")
            print(f"--- 나레이션 내용 ---")
            print(narration)
            print(f"--- 나레이션 끝 ---")

            print(f"영상 제작 중...")
            video_path = create_video(headline_kr, analysis,
                                      image_url=image_url,
                                      article_url=article_url)
            print(f"영상 저장: {video_path}")

            title, description, tags = build_metadata(headline_kr, analysis, article_url=article_url)
            print(f"업로드 제목: {title}")
            video_id = upload_video(video_path, title, description, tags)
            if video_id:
                youtube_url = f"https://youtu.be/{video_id}"
                print(f"YouTube 업로드 완료: {youtube_url}")
            else:
                print("YouTube 업로드 실패 또는 일일 한도 초과")
        else:
            print(f"중요도 {score} < {YOUTUBE_MIN_IMPORTANCE}: 영상 건너뜀")

        processed_ids.append(str(article["id"]))

    except RuntimeError as e:
        print(f"중단 (복구 불가 오류): {e}")
        break
    except Exception as e:
        print(f"오류 발생, 건너뜀: {e}")

    if idx < len(articles):
        print(f"\n{ARTICLE_DELAY_SECONDS}초 대기 후 다음 기사 처리...")
        time.sleep(ARTICLE_DELAY_SECONDS)

if processed_ids:
    mark_as_processed(processed_ids)
    print(f"\n처리 완료: {len(processed_ids)}건 기록됨")
