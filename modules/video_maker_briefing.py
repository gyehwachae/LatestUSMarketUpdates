"""
데일리 마켓 브리핑 전용 영상 생성
- 주요 지수 카드 형태로 표시
- 상승/하락 TOP 5 테이블
- 오늘 이벤트 리스트
"""
import os
import re
import shutil
import subprocess
import textwrap
import time
import asyncio
from datetime import datetime

import edge_tts
import requests as req
from moviepy.config import get_setting
from PIL import Image, ImageDraw, ImageFont

from config import ASSETS_DIR, VIDEO_OUTPUT_DIR

W, H = 1080, 1920

# 색상
BG_DARK = (12, 14, 24)
BG_CARD = (22, 26, 40)
TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (160, 165, 180)
GREEN = (0, 210, 120)
RED = (230, 70, 70)
BLUE = (80, 140, 255)
GOLD = (255, 200, 80)

_FFMPEG = get_setting("FFMPEG_BINARY")
_FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
_FONT_REG = os.path.join(_FONT_DIR, "Pretendard-Regular.otf")
_FONT_BOLD = os.path.join(_FONT_DIR, "Pretendard-Bold.otf")
_VOICE = "ko-KR-HyunsuNeural"  # 더 활기찬 남성 음성
_SILENCE_SEC = 0.3

_PRETENDARD_URLS = {
    "Pretendard-Regular.otf": "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Regular.otf",
    "Pretendard-Bold.otf": "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Bold.otf",
}


def _ensure_fonts():
    os.makedirs(_FONT_DIR, exist_ok=True)
    for fname, url in _PRETENDARD_URLS.items():
        path = os.path.join(_FONT_DIR, fname)
        if not os.path.exists(path):
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
        return ImageFont.load_default()


def _fix_number_josa(text: str) -> str:
    """숫자 뒤 조사를 올바르게 교정합니다. (예: 3와 → 3과)"""
    has_batchim = {'0', '1', '3', '6', '7', '8'}
    josa_pairs = [
        ('와', '과'), ('는', '은'), ('가', '이'), ('를', '을'),
        ('로', '으로'), ('라', '이라'), ('랑', '이랑'),
    ]
    for wrong, correct in josa_pairs:
        pattern = rf'(\d)({re.escape(wrong)})(?=\s|$|[,.]|[가-힣])'
        def replace_josa(m, w=wrong, c=correct):
            return m.group(1) + (c if m.group(1) in has_batchim else w)
        text = re.sub(pattern, replace_josa, text)
        pattern2 = rf'(\d)({re.escape(correct)})(?=\s|$|[,.]|[가-힣])'
        def replace_josa2(m, w=wrong, c=correct):
            return m.group(1) + (w if m.group(1) not in has_batchim else c)
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


async def _tts_async(text: str, out_path: str):
    # rate: +10%로 약간 빠르게, pitch: +5Hz로 약간 높게 (활기찬 느낌)
    communicate = edge_tts.Communicate(text, _VOICE, rate="+10%", pitch="+5Hz")
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


def _draw_rounded_rect(draw: ImageDraw, xy: tuple, radius: int, fill: tuple):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)


def _draw_briefing_layout(data: dict) -> Image.Image:
    """데일리 브리핑 레이아웃"""
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    indices = data.get("indices", [])
    gainers = data.get("gainers", [])
    losers = data.get("losers", [])
    impact = data.get("impact", "중립")

    # 상단 바
    bar_color = GREEN if impact == "긍정" else (RED if impact == "부정" else BLUE)
    draw.rectangle([(0, 0), (W, 6)], fill=bar_color)

    y = 40

    # ── 타이틀 ──
    draw.text((50, y), "DAILY MARKET BRIEFING", font=_font(36, bold=True), fill=GOLD)
    today = datetime.now().strftime("%Y.%m.%d")
    draw.text((W - 200, y + 5), today, font=_font(28), fill=TEXT_GRAY)
    y += 80

    # ── 주요 지수 섹션 ──
    draw.text((50, y), "📊 주요 지수", font=_font(32, bold=True), fill=TEXT_WHITE)
    y += 55

    # 지수 카드 (2x2 그리드)
    card_w = 480
    card_h = 110
    gap = 20

    for i, idx in enumerate(indices[:4]):
        col = i % 2
        row = i // 2
        cx = 50 + col * (card_w + gap)
        cy = y + row * (card_h + gap)

        # 카드 배경
        _draw_rounded_rect(draw, (cx, cy, cx + card_w, cy + card_h), 12, BG_CARD)

        # 지수 이름
        draw.text((cx + 20, cy + 15), idx["name"], font=_font(26, bold=True), fill=TEXT_WHITE)

        # 가격
        price_str = f"{idx['price']:,.0f}"
        draw.text((cx + 20, cy + 50), price_str, font=_font(36, bold=True), fill=TEXT_WHITE)

        # 변동률
        change_color = GREEN if idx["change_pct"] > 0 else RED
        change_str = f"{idx['change_pct']:+.2f}%"
        arrow = "▲" if idx["change_pct"] > 0 else "▼"
        draw.text((cx + 280, cy + 55), f"{arrow} {change_str}", font=_font(30, bold=True), fill=change_color)

    y += 2 * (card_h + gap) + 30

    # ── 구분선 ──
    draw.line([(50, y), (W - 50, y)], fill=(40, 45, 60), width=2)
    y += 25

    # ── 상승 TOP 5 ──
    draw.text((50, y), "📈 상승 TOP 5", font=_font(30, bold=True), fill=GREEN)
    y += 50

    for i, g in enumerate(gainers[:5]):
        rank = f"{i + 1}."
        draw.text((50, y), rank, font=_font(26), fill=TEXT_GRAY)
        draw.text((90, y), g["ticker"], font=_font(26, bold=True), fill=TEXT_WHITE)
        draw.text((200, y), g["name"][:15], font=_font(24), fill=TEXT_GRAY)
        change_str = f"{g['change_pct']:+.2f}%"
        draw.text((W - 150, y), change_str, font=_font(26, bold=True), fill=GREEN)
        y += 42

    y += 20

    # ── 하락 TOP 5 ──
    draw.text((50, y), "📉 하락 TOP 5", font=_font(30, bold=True), fill=RED)
    y += 50

    for i, l in enumerate(losers[:5]):
        rank = f"{i + 1}."
        draw.text((50, y), rank, font=_font(26), fill=TEXT_GRAY)
        draw.text((90, y), l["ticker"], font=_font(26, bold=True), fill=TEXT_WHITE)
        draw.text((200, y), l["name"][:15], font=_font(24), fill=TEXT_GRAY)
        change_str = f"{l['change_pct']:+.2f}%"
        draw.text((W - 150, y), change_str, font=_font(26, bold=True), fill=RED)
        y += 42

    y += 20

    # ── 구분선 ──
    draw.line([(50, y), (W - 50, y)], fill=(40, 45, 60), width=2)
    y += 25

    # ── 오늘 이벤트 ──
    events = data.get("events", [])
    earnings = data.get("earnings", [])

    draw.text((50, y), "📅 오늘 주요 일정", font=_font(30, bold=True), fill=GOLD)
    y += 50

    if earnings:
        draw.text((50, y), "실적 발표:", font=_font(24), fill=TEXT_GRAY)
        tickers = ", ".join([e["ticker"] for e in earnings[:4]])
        draw.text((170, y), tickers, font=_font(24, bold=True), fill=TEXT_WHITE)
        y += 38

    if events:
        for e in events[:2]:
            event_text = e["event"][:35]
            draw.text((50, y), f"• {event_text}", font=_font(24), fill=TEXT_GRAY)
            y += 35
    elif not earnings:
        draw.text((50, y), "• 주요 일정 없음", font=_font(24), fill=TEXT_GRAY)

    # ── 하단 바 ──
    draw.rectangle([(0, H - 6), (W, H)], fill=bar_color)

    # 워터마크
    draw.text((50, H - 50), "US Market Flash  |  매일 아침 증시 브리핑",
              font=_font(22), fill=(70, 75, 90))

    return img


def _draw_subtitle_briefing(img: Image.Image, text: str) -> Image.Image:
    """자막 렌더링"""
    if not text:
        return img

    lines = textwrap.wrap(text, width=24)[:3]
    if not lines:
        return img

    font = _font(40, bold=True)
    line_h = 52
    pad = 20
    ph = len(lines) * line_h + pad * 2
    y_start = H - ph - 70

    # 자막 배경
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    _draw_rounded_rect(overlay_draw, (30, y_start, W - 30, y_start + ph), 12, (10, 12, 20, 230))

    # 왼쪽 바
    overlay_draw.rectangle([(30, y_start), (38, y_start + ph)], fill=GOLD + (255,))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    y = y_start + pad
    for line in lines:
        draw.text((58, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((56, y), line, font=font, fill=TEXT_WHITE)
        y += line_h

    return img


def create_briefing_video(data: dict, narration: str) -> str:
    """데일리 브리핑 영상 생성"""
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # 1. TTS 생성
    audio_path = os.path.join(ASSETS_DIR, "briefing_tts.mp3")
    print(f"  [>>] TTS 생성 중...")
    timings = _make_audio_with_timing(narration, audio_path)
    duration = (timings[-1][2] + 0.5) if timings else 10.0
    print(f"  [OK] TTS 완료: {len(timings)}문장, {duration:.1f}초")

    # 2. 기본 레이아웃 생성
    base_frame = _draw_briefing_layout(data)

    # 3. 프레임 생성
    FPS = 30
    total_frames = int(duration * FPS)
    frames_dir = os.path.join(ASSETS_DIR, "briefing_frames")
    os.makedirs(frames_dir, exist_ok=True)
    frame_paths = []

    for fi in range(total_frames):
        current_time = fi / FPS

        subtitle = ""
        for sent_text, start, end in timings:
            if start <= current_time < end:
                subtitle = sent_text
                break

        frame = base_frame.copy()
        frame = _draw_subtitle_briefing(frame, subtitle)

        path = os.path.join(frames_dir, f"frame_{fi:05d}.png")
        frame.save(path)
        frame_paths.append(path)

    # 4. ffmpeg 인코딩
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(VIDEO_OUTPUT_DIR, f"daily_briefing_{timestamp}.mp4")

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

    # 5. 정리
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
