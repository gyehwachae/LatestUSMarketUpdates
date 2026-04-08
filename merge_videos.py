#!/usr/bin/env python3
"""
Manim 시각화 영상 + 종목분석 영상 합치기
- Manim 영상 (가로형 1920x1080)을 세로형 (1080x1920)으로 변환
- 종목분석 영상과 순차 연결
- 전체 나레이션 오디오 합치기
"""
import os
import subprocess
import sys
from datetime import datetime


def merge_videos(manim_video: str, stock_video: str, output_path: str = None) -> str:
    """
    Manim 영상과 종목분석 영상을 합치기

    Args:
        manim_video: Manim 시각화 영상 경로
        stock_video: 종목분석 영상 경로
        output_path: 출력 경로 (None이면 자동 생성)

    Returns:
        합쳐진 영상 경로
    """
    if not os.path.exists(manim_video):
        print(f"[!!] Manim 영상 없음: {manim_video}")
        return None

    if not os.path.exists(stock_video):
        print(f"[!!] 종목분석 영상 없음: {stock_video}")
        return None

    # 출력 경로
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.dirname(stock_video)
        output_path = os.path.join(output_dir, f"merged_{timestamp}.mp4")

    # 임시 파일 경로
    temp_dir = "/tmp/video_merge"
    os.makedirs(temp_dir, exist_ok=True)
    manim_vertical = os.path.join(temp_dir, "manim_vertical.mp4")
    concat_list = os.path.join(temp_dir, "concat_list.txt")

    print(f"[>>] Manim 영상을 세로형으로 변환 중...")

    # 1. Manim 영상 (가로 1920x1080) → 세로 (1080x1920) 변환
    # 배경을 검정색으로 채우고 중앙에 배치
    cmd_convert = [
        "ffmpeg", "-y",
        "-i", manim_video,
        "-vf", "scale=1080:-1,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-an",  # 오디오 제거 (나중에 합칠 것)
        manim_vertical
    ]
    subprocess.run(cmd_convert, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  [OK] 세로형 변환 완료")

    # 2. concat 리스트 생성
    with open(concat_list, "w") as f:
        f.write(f"file '{manim_vertical}'\n")
        f.write(f"file '{os.path.abspath(stock_video)}'\n")

    print(f"[>>] 영상 합치는 중...")

    # 3. 영상 연결 (concat demuxer)
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    subprocess.run(cmd_concat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  [OK] 영상 합치기 완료")

    # 4. 임시 파일 정리
    if os.path.exists(manim_vertical):
        os.remove(manim_vertical)
    if os.path.exists(concat_list):
        os.remove(concat_list)

    print(f"[OK] 최종 영상: {output_path}")
    return output_path


def create_full_video(ticker: str, render_manim: bool = True) -> str:
    """
    종목 분석 + Manim 시각화 전체 영상 생성

    Args:
        ticker: 종목 티커 (예: NVDA)
        render_manim: Manim 영상 새로 렌더링 여부

    Returns:
        최종 영상 경로
    """
    import subprocess

    # 1. Manim 영상 렌더링 (필요시)
    manim_video = "media/videos/manim_nvda_analysis/1080p60/NVDAAnalysis.mp4"

    if render_manim or not os.path.exists(manim_video):
        print(f"\n[>>] Manim 시각화 영상 렌더링 중...")
        cmd = ["manim", "-qh", "manim_nvda_analysis.py", "NVDAAnalysis"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  [!!] Manim 렌더링 실패")
            print(result.stderr[-500:] if result.stderr else "")
            return None
        print(f"  [OK] Manim 렌더링 완료")

    # 2. 종목 분석 영상 생성
    print(f"\n[>>] 종목 분석 영상 생성 중...")
    from modules.stock_analyzer import analyze_stock
    from modules.video_maker_stock import create_stock_video

    analysis_result = analyze_stock(ticker)
    if not analysis_result:
        print(f"  [!!] 종목 분석 실패")
        return None

    stock_video = create_stock_video(analysis_result)
    if not stock_video:
        print(f"  [!!] 영상 생성 실패")
        return None

    # 3. 영상 합치기
    print(f"\n[>>] 영상 합치는 중...")
    final_video = merge_videos(manim_video, stock_video)

    return final_video


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법:")
        print("  python merge_videos.py NVDA              # 전체 영상 생성")
        print("  python merge_videos.py --merge <manim> <stock>  # 영상만 합치기")
        sys.exit(1)

    if sys.argv[1] == "--merge":
        if len(sys.argv) < 4:
            print("사용법: python merge_videos.py --merge <manim_video> <stock_video>")
            sys.exit(1)
        merge_videos(sys.argv[2], sys.argv[3])
    else:
        ticker = sys.argv[1].upper()
        final = create_full_video(ticker, render_manim=False)
        if final:
            print(f"\n{'='*60}")
            print(f"  최종 영상: {final}")
            print(f"{'='*60}")
