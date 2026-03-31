"""
Pillow + ffmpeg + edge-tts/gTTS로 뉴스 쇼츠 영상을 자동 생성합니다.
- 문장별 TTS 생성 → 자막 타이밍 추출
- 프레임마다 자막 텍스트 렌더링 (대본 동기화)
- Pretendard 폰트 자동 다운로드
해상도: 1080x1920 (YouTube Shorts 세로형)
"""
import asyncio
import io
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
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import ASSETS_DIR, VIDEO_OUTPUT_DIR
from modules.chart_maker import generate_chart_frames, W_CHART, H_CHART

W, H = 1080, 1920
BG_COLOR      = (10, 10, 30)
TEXT_COLOR    = (255, 255, 255)
SUBTITLE_BG   = (0, 0, 0, 200)
IMPACT_COLORS = {"긍정": (0, 210, 100), "부정": (220, 60, 60), "중립": (160, 160, 160)}
IMPACT_LABEL  = {"긍정": "매매의견 : 긍정", "부정": "매매의견 : 부정", "중립": "매매의견 : 중립"}

_FFMPEG    = get_setting("FFMPEG_BINARY")
_FONT_DIR  = os.path.join(ASSETS_DIR, "fonts")
_FONT_REG  = os.path.join(_FONT_DIR, "Pretendard-Regular.otf")
_FONT_BOLD = os.path.join(_FONT_DIR, "Pretendard-Bold.otf")

_VOICE           = "ko-KR-SunHiNeural"
_SILENCE_SEC     = 0.3   # 문장 사이 묵음 길이

_PRETENDARD_URLS = {
    "Pretendard-Regular.otf": "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Regular.otf",
    "Pretendard-Bold.otf":    "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Bold.otf",
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
    """단일 문장 TTS (edge-tts 우선, gTTS 폴백)"""
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
    """
    문장별 TTS를 생성하고 합친 뒤 각 문장의 (텍스트, 시작초, 끝초)를 반환합니다.
    이 타이밍으로 영상에 자막을 동기화합니다.
    """
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


# ──────────────────────────── 이미지 검색 ────────────────────────────

def _fetch_web_image(query: str) -> str | None:
    """DuckDuckGo 이미지 검색으로 관련 이미지 URL을 반환합니다."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=5, type_image="photo"))
            for r in results:
                url = r.get("image", "")
                if url and url.startswith("http"):
                    return url
    except Exception as e:
        print(f"  [!!] 웹 이미지 검색 실패: {e}")
    return None


def _load_background(image_url: str | None) -> Image.Image:
    bg = Image.new("RGB", (W, H), BG_COLOR)
    if not image_url:
        return bg
    try:
        r = req.get(image_url, timeout=8)
        r.raise_for_status()
        news_img = Image.open(io.BytesIO(r.content)).convert("RGB")
        ratio    = W / news_img.width
        new_h    = max(int(news_img.height * ratio), H)
        news_img = news_img.resize((W, new_h), Image.LANCZOS)
        top      = (news_img.height - H) // 2
        news_img = news_img.crop((0, top, W, top + H))
        news_img = news_img.filter(ImageFilter.GaussianBlur(radius=12))
        overlay  = Image.new("RGBA", (W, H), (0, 0, 20, 210))
        bg = Image.alpha_composite(news_img.convert("RGBA"), overlay).convert("RGB")
    except Exception as e:
        print(f"  [!!] 배경 이미지 로드 실패: {e}")
    return bg


# ──────────────────────────── 오버레이 렌더링 ────────────────────────────

def _draw_text_overlays(img: Image.Image, tickers: list, companies: list,
                        companies_en: list, impact: str, headline_kr: str) -> Image.Image:
    """정적 텍스트 패널(종목·매매의견·헤드라인)을 렌더링합니다."""
    bar   = IMPACT_COLORS.get(impact, IMPACT_COLORS["중립"])
    label = IMPACT_LABEL.get(impact, f"매매의견 : {impact}")
    draw  = ImageDraw.Draw(img)

    # 상단/하단 컬러 바
    draw.rectangle([(0, 0),      (W, 14)], fill=bar)
    draw.rectangle([(0, H - 14), (W, H)], fill=bar)

    y = 30

    # ── 종목 블록 ──
    if tickers:
        for i, ticker in enumerate(tickers[:3]):
            en_name = companies_en[i] if i < len(companies_en) else ""
            draw.text((44, y), f"${ticker}", font=_font(72, bold=True), fill=bar)
            tw = int(_font(72, bold=True).getlength(f"${ticker}"))
            if en_name:
                draw.text((44 + tw + 24, y + 20), en_name, font=_font(34), fill=TEXT_COLOR)
            y += 90
    else:
        draw.text((44, y), "US Market", font=_font(64, bold=True), fill=bar)
        y += 90

    # ── 매매의견 (종목이 있을 때만) ──
    if tickers:
        y += 8
        op_bg = Image.new("RGBA", (W, 96), (0, 0, 0, 200))
        img.paste(op_bg, (0, y), op_bg)
        draw = ImageDraw.Draw(img)
        draw.text((44, y + 12), label, font=_font(58, bold=True), fill=bar)
        y += 110

    # ── 차트 영역 (chart_maker가 채움) ──
    y += H_CHART + 20

    # ── 헤드라인 패널 ──
    headline_lines = textwrap.wrap(headline_kr, width=19)[:3]
    ph = len(headline_lines) * 74 + 32
    panel = Image.new("RGBA", (W, ph), (0, 0, 0, 175))
    img.paste(panel, (0, y), panel)
    draw = ImageDraw.Draw(img)
    y += 16
    for line in headline_lines:
        draw.text((44, y), line, font=_font(52, bold=True), fill=TEXT_COLOR)
        y += 74

    # 워터마크
    ts = datetime.now().strftime("%Y.%m.%d %H:%M KST")
    draw.text((44, H - 46), f"US Market Flash  |  {ts}",
              font=_font(26), fill=(120, 120, 140))

    return img


def _draw_subtitle(img: Image.Image, text: str) -> Image.Image:
    """현재 문장을 하단 자막으로 렌더링합니다."""
    if not text:
        return img

    lines = textwrap.wrap(text, width=21)[:3]
    if not lines:
        return img

    font    = _font(46, bold=True)
    line_h  = 62
    pad     = 20
    ph      = len(lines) * line_h + pad * 2
    y_start = H - ph - 58  # 워터마크 위

    # 반투명 배경
    panel = Image.new("RGBA", (W, ph), SUBTITLE_BG)
    img.paste(panel, (0, y_start), panel)

    draw = ImageDraw.Draw(img)
    y = y_start + pad
    for line in lines:
        # 외곽선 (가독성)
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            draw.text((44 + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((44, y), line, font=font, fill=TEXT_COLOR)
        y += line_h

    return img


def _chart_y_offset(tickers: list) -> int:
    ticker_count   = len(tickers[:3]) if tickers else 1
    opinion_height = 8 + 110 if tickers else 0
    return 30 + ticker_count * 90 + opinion_height


# ──────────────────────────── 영상 생성 ────────────────────────────

def create_video(headline_kr: str, analysis: dict,
                 image_url: str | None = None,
                 article_url: str | None = None) -> str:
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    companies    = analysis.get("companies", [])
    companies_en = analysis.get("companies_en", [])
    impact       = analysis.get("impact", "중립")
    reason       = analysis.get("reason", "")
    tickers      = analysis.get("tickers", [])

    # 나레이션 스크립트 준비
    raw_script = analysis.get("narration") or analysis.get("script", headline_kr)
    raw_script = _clean_script(raw_script)

    # 한국어 회사명 → 영문 치환 (TTS 영어 발음)
    for ko, en in zip(companies, companies_en):
        if ko and en:
            raw_script = raw_script.replace(ko, en)

    # 종목 관련 뉴스: 마지막에 분석 요약 추가
    if tickers:
        ticker_label = ", ".join(companies_en[:3]) if companies_en else ", ".join(tickers[:3])
        impact_word  = {"긍정": "긍정적", "부정": "부정적", "중립": "중립적"}.get(impact, impact)
        reason_clean = _clean_script(reason)
        summary_line = f"종목 분석. {ticker_label}은 이번 뉴스로 {impact_word} 영향이 예상됩니다. {reason_clean}"
        script = raw_script.rstrip() + " " + summary_line
    else:
        script = raw_script

    # 이미지가 없으면 웹 검색
    if not image_url:
        if companies_en:
            query = f"{companies_en[0]} stock market finance"
        elif tickers:
            query = f"{tickers[0]} stock market"
        else:
            query = "US stock market finance news"
        print(f"  [>>] 이미지 없음, 웹 검색 중: {query}")
        image_url = _fetch_web_image(query)
        if image_url:
            print(f"  [OK] 웹 이미지 획득")
        else:
            print(f"  [--] 웹 이미지 없음, 다크 배경 사용")

    # 1. 문장별 TTS 생성 + 자막 타이밍
    audio_path = os.path.join(ASSETS_DIR, "tts_temp.mp3")
    print(f"  [>>] TTS 생성 중 ({len(_split_sentences(script))}문장)...")
    timings  = _make_audio_with_timing(script, audio_path)
    duration = (timings[-1][2] + 0.5) if timings else 10.0
    print(f"  [OK] TTS 완료: {len(timings)}문장, {duration:.1f}초")

    # 2. 배경
    bg = _load_background(image_url)

    # 3. 차트 프레임 생성 (영상 전체 길이)
    FPS          = 30
    total_frames = int(duration * FPS)
    bar_color    = IMPACT_COLORS.get(impact, IMPACT_COLORS["중립"])
    chart_frames = generate_chart_frames(tickers, total_frames, bar_color, W_CHART, H_CHART)
    chart_y      = _chart_y_offset(tickers)

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
        if chart_frames[chart_idx]:
            frame.paste(chart_frames[chart_idx], (0, chart_y), chart_frames[chart_idx])

        frame = _draw_text_overlays(frame, tickers, companies, companies_en,
                                    impact, headline_kr)
        frame = _draw_subtitle(frame, subtitle)

        path = os.path.join(frames_dir, f"frame_{fi:05d}.png")
        frame.save(path)
        frame_paths.append(path)

    # 4. ffmpeg: 프레임 + 음성 합성
    ticker_str  = "_".join(tickers) if tickers else "market"
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
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
