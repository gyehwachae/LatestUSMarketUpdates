#!/usr/bin/env python3
"""
종목 모멘텀 분석 영상 생성 CLI

사용법:
    python analyze_stock.py AAPL                # 분석 + 업로드
    python analyze_stock.py AAPL --no-upload    # 영상만 생성
    python analyze_stock.py AAPL NVDA TSLA      # 여러 종목
"""
import argparse
import sys
import time

from modules.stock_analyzer import analyze_stock
from modules.video_maker_stock import create_stock_video, build_stock_metadata
from modules.uploader import upload_video


def main():
    parser = argparse.ArgumentParser(
        description="종목 모멘텀 분석 YouTube Shorts 영상 생성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
    python analyze_stock.py AAPL                  # AAPL 분석 + YouTube 업로드
    python analyze_stock.py AAPL --no-upload      # AAPL 분석, 영상만 생성
    python analyze_stock.py AAPL NVDA TSLA        # 여러 종목 분석 + 업로드
    python analyze_stock.py AAPL NVDA --no-upload # 여러 종목, 영상만 생성
        """
    )
    parser.add_argument(
        "tickers",
        nargs="+",
        help="분석할 종목 티커 (예: AAPL NVDA TSLA)"
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="YouTube 업로드 없이 영상만 생성"
    )

    args = parser.parse_args()

    # 티커 정규화 (대문자)
    tickers = [t.upper() for t in args.tickers]

    print("=" * 60)
    print(f"  종목 모멘텀 분석 시작: {', '.join(tickers)}")
    print(f"  YouTube 업로드: {'비활성화' if args.no_upload else '활성화'}")
    print("=" * 60)

    results = []

    for ticker in tickers:
        try:
            # 1. 종목 분석
            result = analyze_stock(ticker)
            if not result:
                print(f"\n[!] {ticker}: 분석 실패, 건너뜀")
                continue

            # 2. 영상 생성
            print(f"\n[Video] {ticker} 영상 생성 중...")
            video_path = create_stock_video(result)
            print(f"[OK] 영상 생성 완료: {video_path}")

            # 3. YouTube 업로드
            if not args.no_upload:
                print(f"\n[Upload] {ticker} YouTube 업로드 중...")
                title, description, tags = build_stock_metadata(result)
                video_id = upload_video(video_path, title, description, tags)

                if video_id:
                    url = f"https://youtu.be/{video_id}"
                    print(f"[OK] 업로드 완료: {url}")
                    results.append({
                        "ticker": ticker,
                        "video_path": video_path,
                        "youtube_url": url,
                        "verdict": result["analysis"]["verdict"],
                    })
                else:
                    print(f"[!] {ticker}: 업로드 실패 또는 한도 초과")
                    results.append({
                        "ticker": ticker,
                        "video_path": video_path,
                        "youtube_url": None,
                        "verdict": result["analysis"]["verdict"],
                    })
            else:
                results.append({
                    "ticker": ticker,
                    "video_path": video_path,
                    "youtube_url": None,
                    "verdict": result["analysis"]["verdict"],
                })

            # 종목 간 딜레이 (API 쿼터 보호)
            if ticker != tickers[-1]:
                print("\n[..] 다음 종목 처리 전 5초 대기...")
                time.sleep(5)

        except KeyboardInterrupt:
            print("\n\n[!] 사용자 중단")
            break
        except Exception as e:
            print(f"\n[ERROR] {ticker}: {e}")
            continue

    # 결과 요약
    print("\n" + "=" * 60)
    print("  분석 결과 요약")
    print("=" * 60)

    for r in results:
        status = "✅" if r.get("youtube_url") else "📁"
        print(f"  {status} {r['ticker']}: {r['verdict']}")
        print(f"     영상: {r['video_path']}")
        if r.get("youtube_url"):
            print(f"     URL: {r['youtube_url']}")

    print("=" * 60)
    print(f"  완료: {len(results)}/{len(tickers)} 종목")

    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
