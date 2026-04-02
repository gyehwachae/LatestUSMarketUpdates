"""
뉴스 보고서 형식의 YouTube Shorts 영상 생성
- 깔끔한 그라데이션 배경
- 종목 + 영향 배지 + 헤드라인 + 핵심 포인트 레이아웃
- 문장별 TTS + 자막 동기화
해상도: 1080x1920 (YouTube Shorts 세로형)
"""
import asyncio
import os
import re
import shutil
import subprocess
import textwrap
import time
from datetime import datetime

import edge_tts
import requests as req
from moviepy.config import get_setting
from PIL import Image, ImageDraw, ImageFont

from config import ASSETS_DIR, VIDEO_OUTPUT_DIR
from modules.chart_maker import generate_chart_frames, W_CHART, H_CHART

W, H = 1080, 1920

# 색상 팔레트
COLORS = {
    "긍정": {
        "primary": (0, 200, 120),      # 메인 녹색
        "bg_top": (10, 35, 30),        # 배경 상단
        "bg_bottom": (5, 20, 25),      # 배경 하단
        "badge": (0, 180, 100),        # 배지 색상
        "accent": (100, 255, 180),     # 강조 색상
    },
    "부정": {
        "primary": (230, 70, 70),      # 메인 빨강
        "bg_top": (40, 15, 20),        # 배경 상단
        "bg_bottom": (25, 10, 15),     # 배경 하단
        "badge": (200, 60, 60),        # 배지 색상
        "accent": (255, 120, 120),     # 강조 색상
    },
    "중립": {
        "primary": (100, 150, 255),    # 메인 파랑
        "bg_top": (15, 20, 40),        # 배경 상단
        "bg_bottom": (10, 12, 30),     # 배경 하단
        "badge": (80, 130, 220),       # 배지 색상
        "accent": (150, 200, 255),     # 강조 색상
    },
}

TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (180, 180, 190)
TEXT_DARK = (40, 40, 50)

_FFMPEG = get_setting("FFMPEG_BINARY")
_FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
_FONT_REG = os.path.join(_FONT_DIR, "Pretendard-Regular.otf")
_FONT_BOLD = os.path.join(_FONT_DIR, "Pretendard-Bold.otf")

_VOICE = "ko-KR-SunHiNeural"
_SILENCE_SEC = 0.3

_PRETENDARD_URLS = {
    "Pretendard-Regular.otf": "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Regular.otf",
    "Pretendard-Bold.otf": "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Bold.otf",
}


# ──────────────────────────── 폰트 ────────────────────────────

def _ensure_fonts():
    os.makedirs(_FONT_DIR, exist_ok=True)
    for fname, url in _PRETENDARD_URLS.items():
        path = os.path.join(_FONT_DIR, fname)
        if not os.path.exists(path):
            print(f"  → Pretendard 폰트 다운로드 중: {fname}")
            r = req.get(url, timeout=15)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        _ensure_fonts()
        path = _FONT_BOLD if bold else _FONT_REG
        return ImageFont.truetype(path, size)
    except Exception:
        fallback = r"C:\Windows\Fonts\malgunbd.ttf" if bold else r"C:\Windows\Fonts\malgun.ttf"
        return ImageFont.truetype(fallback, size)


# ──────────────────────────── 유틸 ────────────────────────────

def _clean_script(text: str) -> str:
    text = re.sub(r"[▶▷►◆◇★☆✓✗✘⚠📊🚀🔻]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FFFF]", "", text)
    text = re.sub(r"\$([A-Z]+)", r"\1", text)
    return text.strip()


def _fix_number_josa(text: str) -> str:
    """숫자 뒤 조사를 올바르게 교정합니다. (예: 3와 → 3과)"""
    # 숫자별 받침 유무 (마지막 자리 기준)
    # 받침 있음: 0(영), 1(일), 3(삼), 6(육), 7(칠), 8(팔)
    # 받침 없음: 2(이), 4(사), 5(오), 9(구)
    has_batchim = {'0', '1', '3', '6', '7', '8'}

    # 조사 쌍: (받침 없을 때, 받침 있을 때)
    josa_pairs = [
        ('와', '과'),
        ('는', '은'),
        ('가', '이'),
        ('를', '을'),
        ('로', '으로'),
        ('라', '이라'),
        ('랑', '이랑'),
    ]

    for wrong_when_batchim, correct_when_batchim in josa_pairs:
        # 패턴: 숫자 + 잘못된 조사
        # 받침 있는 숫자 뒤에 받침 없는 조사가 온 경우 교정
        pattern = rf'(\d)({re.escape(wrong_when_batchim)})(?=\s|$|[,.]|[가-힣])'
        def replace_josa(m):
            digit = m.group(1)
            if digit in has_batchim:
                return digit + correct_when_batchim
            return m.group(0)
        text = re.sub(pattern, replace_josa, text)

        # 반대 케이스: 받침 없는 숫자 뒤에 받침 있는 조사가 온 경우
        pattern2 = rf'(\d)({re.escape(correct_when_batchim)})(?=\s|$|[,.]|[가-힣])'
        def replace_josa2(m):
            digit = m.group(1)
            if digit not in has_batchim:
                return digit + wrong_when_batchim
            return m.group(0)
        text = re.sub(pattern2, replace_josa2, text)

    return text


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _get_mp3_duration(path: str) -> float:
    result = subprocess.run(
        [_FFMPEG, "-i", path],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    )
    for line in result.stderr.splitlines():
        if "Duration" in line:
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", line)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


# ──────────────────────────── TTS ────────────────────────────

async def _tts_async(text: str, out_path: str):
    communicate = edge_tts.Communicate(text, _VOICE)
    await communicate.save(out_path)


def _tts_sentence(text: str, out_path: str):
    text = _fix_number_josa(text)  # 숫자 뒤 조사 교정
    try:
        asyncio.run(_tts_async(text, out_path))
    except Exception:
        from gtts import gTTS
        gTTS(text=text, lang="ko", slow=False).save(out_path)


def _make_silence(duration: float, out_path: str):
    cmd = [_FFMPEG, "-y", "-f", "lavfi", "-i",
           f"anullsrc=r=24000:cl=mono", "-t", str(duration),
           "-q:a", "9", "-acodec", "libmp3lame", out_path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _make_audio_with_timing(script: str, out_path: str) -> list[tuple[str, float, float]]:
    sentences = _split_sentences(script) or [script]
    timings = []
    tmp_files = []
    current_time = 0.0

    for i, sent in enumerate(sentences):
        tmp = out_path.replace(".mp3", f"_s{i}.mp3")
        _tts_sentence(sent, tmp)
        dur = _get_mp3_duration(tmp)
        timings.append((sent, current_time, current_time + dur))
        current_time += dur
        tmp_files.append(tmp)

        if i < len(sentences) - 1:
            sil = out_path.replace(".mp3", f"_sil{i}.mp3")
            _make_silence(_SILENCE_SEC, sil)
            current_time += _SILENCE_SEC
            tmp_files.append(sil)

    if len(tmp_files) == 1:
        shutil.copy(tmp_files[0], out_path)
    else:
        inputs = []
        for f in tmp_files:
            inputs += ["-i", f]
        n = len(tmp_files)
        filter_str = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
        subprocess.run(
            [_FFMPEG, "-y"] + inputs + ["-filter_complex", filter_str, "-map", "[out]", out_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )

    for f in tmp_files:
        if os.path.exists(f):
            os.remove(f)

    return timings


# ──────────────────────────── 그라데이션 배경 ────────────────────────────

def _create_gradient_background(impact: str) -> Image.Image:
    """영향(긍정/부정/중립)에 따른 그라데이션 배경 생성"""
    colors = COLORS.get(impact, COLORS["중립"])
    top = colors["bg_top"]
    bottom = colors["bg_bottom"]

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        ratio = y / H
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    return img


def _draw_rounded_rect(draw: ImageDraw, xy: tuple, radius: int, fill: tuple):
    """둥근 모서리 사각형 그리기"""
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)


# ──────────────────────────── 보고서 레이아웃 ────────────────────────────

def _draw_report_layout(img: Image.Image, tickers: list, companies_en: list,
                        impact: str, headline_kr: str, summary: str,
                        chart_frame: Image.Image | None = None) -> Image.Image:
    """뉴스 보고서 형식 레이아웃 렌더링"""
    colors = COLORS.get(impact, COLORS["중립"])
    primary = colors["primary"]
    badge_color = colors["badge"]
    accent = colors["accent"]

    draw = ImageDraw.Draw(img)

    # 상단/하단 컬러 바
    draw.rectangle([(0, 0), (W, 8)], fill=primary)
    draw.rectangle([(0, H - 8), (W, H)], fill=primary)

    y = 50

    # ── 채널 로고/타이틀 ──
    draw.text((50, y), "US MARKET FLASH", font=_font(32, bold=True), fill=accent)
    ts = datetime.now().strftime("%Y.%m.%d %H:%M")
    draw.text((W - 250, y + 5), ts, font=_font(26), fill=TEXT_GRAY)
    y += 80

    # ── 종목 블록 ──
    if tickers:
        for i, ticker in enumerate(tickers[:2]):  # 최대 2개
            # 티커 배경 박스
            ticker_text = f"${ticker}"
            _draw_rounded_rect(draw, (50, y, 280, y + 70), 10, (30, 30, 45))
            draw.text((70, y + 12), ticker_text, font=_font(42, bold=True), fill=primary)

            # 회사명
            en_name = companies_en[i] if i < len(companies_en) else ""
            if en_name:
                draw.text((300, y + 20), en_name[:25], font=_font(30), fill=TEXT_WHITE)
            y += 85
    else:
        _draw_rounded_rect(draw, (50, y, 350, y + 70), 10, (30, 30, 45))
        draw.text((70, y + 12), "US MARKET", font=_font(42, bold=True), fill=primary)
        y += 85

    # ── 영향 배지 ──
    y += 10
    impact_text = {"긍정": "📈 긍정적 전망", "부정": "📉 부정적 전망", "중립": "➖ 중립 전망"}.get(impact, "➖ 중립")
    _draw_rounded_rect(draw, (50, y, 320, y + 55), 8, badge_color)
    draw.text((75, y + 10), impact_text, font=_font(32, bold=True), fill=TEXT_WHITE)
    y += 90

    # ── 구분선 ──
    draw.line([(50, y), (W - 50, y)], fill=(60, 60, 80), width=2)
    y += 30

    # ── 헤드라인 ──
    headline_lines = textwrap.wrap(headline_kr, width=17)[:4]
    for line in headline_lines:
        draw.text((50, y), line, font=_font(52, bold=True), fill=TEXT_WHITE)
        y += 70
    y += 20

    # ── 구분선 ──
    draw.line([(50, y), (W - 50, y)], fill=(60, 60, 80), width=2)
    y += 30

    # ── 차트 영역 ──
    if chart_frame:
        chart_y = y
        img.paste(chart_frame, (0, chart_y), chart_frame)
        y += H_CHART + 20

    # ── 핵심 포인트 ──
    if summary:
        draw.text((50, y), "핵심 포인트", font=_font(28, bold=True), fill=accent)
        y += 45

        # 요약을 줄로 나누기
        summary_lines = textwrap.wrap(summary, width=28)[:4]
        for i, line in enumerate(summary_lines):
            bullet = "•"
            draw.text((50, y), bullet, font=_font(28), fill=primary)
            draw.text((80, y), line, font=_font(28), fill=TEXT_GRAY)
            y += 42

    # ── 워터마크 ──
    draw.text((50, H - 55), "US Market Flash  |  실시간 미국 주식 뉴스",
              font=_font(24), fill=(80, 80, 100))

    return img


def _draw_subtitle(img: Image.Image, text: str, impact: str) -> Image.Image:
    """현재 문장을 하단 자막으로 렌더링"""
    if not text:
        return img

    colors = COLORS.get(impact, COLORS["중립"])
    primary = colors["primary"]

    lines = textwrap.wrap(text, width=22)[:3]
    if not lines:
        return img

    font = _font(44, bold=True)
    line_h = 58
    pad = 24
    ph = len(lines) * line_h + pad * 2
    y_start = H - ph - 75

    # 자막 배경 (반투명 + 테두리)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # 배경 박스
    _draw_rounded_rect(overlay_draw, (30, y_start, W - 30, y_start + ph), 15, (15, 15, 25, 230))

    # 왼쪽 강조 바
    overlay_draw.rectangle([(30, y_start), (38, y_start + ph)], fill=primary + (255,))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    y = y_start + pad
    for line in lines:
        # 텍스트 그림자
        draw.text((62, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((60, y), line, font=font, fill=TEXT_WHITE)
        y += line_h

    return img


# ──────────────────────────── 영상 생성 ────────────────────────────

def create_video(headline_kr: str, analysis: dict,
                 image_url: str | None = None,
                 article_url: str | None = None) -> str:
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    companies = analysis.get("companies", [])
    companies_en = analysis.get("companies_en", [])
    impact = analysis.get("impact", "중립")
    summary = analysis.get("summary", "")
    tickers = analysis.get("tickers", [])

    # 나레이션 스크립트 준비
    raw_script = analysis.get("narration") or analysis.get("script", headline_kr)
    raw_script = _clean_script(raw_script)

    # 한국어 회사명 → 영문 치환 (TTS 영어 발음)
    for ko, en in zip(companies, companies_en):
        if ko and en:
            raw_script = raw_script.replace(ko, en)

    script = raw_script

    # 1. 문장별 TTS 생성 + 자막 타이밍
    audio_path = os.path.join(ASSETS_DIR, "tts_temp.mp3")
    print(f"  [>>] TTS 생성 중 ({len(_split_sentences(script))}문장)...")
    timings = _make_audio_with_timing(script, audio_path)
    duration = (timings[-1][2] + 0.5) if timings else 10.0
    print(f"  [OK] TTS 완료: {len(timings)}문장, {duration:.1f}초")

    # 2. 그라데이션 배경 생성
    bg = _create_gradient_background(impact)
    print(f"  [OK] 보고서 배경 생성 ({impact})")

    # 3. 차트 프레임 생성
    FPS = 30
    total_frames = int(duration * FPS)
    bar_color = COLORS.get(impact, COLORS["중립"])["primary"]
    chart_frames = generate_chart_frames(tickers, total_frames, bar_color, W_CHART, H_CHART)

    frames_dir = os.path.join(ASSETS_DIR, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    frame_paths = []

    for fi in range(total_frames):
        current_time = fi / FPS

        # 현재 시간에 해당하는 자막 선택
        subtitle = ""
        for sent_text, start, end in timings:
            if start <= current_time < end:
                subtitle = sent_text
                break

        chart_idx = min(fi, len(chart_frames) - 1)
        frame = bg.copy()

        # 보고서 레이아웃 렌더링
        frame = _draw_report_layout(
            frame, tickers, companies_en, impact, headline_kr, summary,
            chart_frame=chart_frames[chart_idx]
        )

        # 자막 렌더링
        frame = _draw_subtitle(frame, subtitle, impact)

        path = os.path.join(frames_dir, f"frame_{fi:05d}.png")
        frame.save(path)
        frame_paths.append(path)

    # 4. ffmpeg: 프레임 + 음성 합성
    ticker_str = "_".join(tickers) if tickers else "market"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(VIDEO_OUTPUT_DIR, f"{ticker_str}_{timestamp}.mp4")

    cmd = [
        _FFMPEG, "-y",
        "-framerate", str(FPS),
        "-i", os.path.join(frames_dir, "frame_%05d.png"),
        "-i", audio_path,
        "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 5. 임시 파일 정리
    time.sleep(1)
    for p in frame_paths:
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(audio_path):
        os.remove(audio_path)
    try:
        os.rmdir(frames_dir)
    except Exception:
        pass

    return output_path
