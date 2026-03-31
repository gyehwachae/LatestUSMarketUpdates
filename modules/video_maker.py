"""
Pillow + ffmpeg + gTTS로 뉴스 쇼츠 영상을 자동 생성합니다.
- 주식 차트 애니메이션 배경
- Pretendard 폰트 자동 다운로드
- 문장 사이 0.5초 묵음 삽입
해상도: 1080x1920 (YouTube Shorts 세로형)
"""
import asyncio
import io
import os
import re
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
BG_COLOR   = (10, 10, 30)
TEXT_COLOR = (255, 255, 255)
GRAY_COLOR = (200, 200, 210)
IMPACT_COLORS = {"긍정": (0, 210, 100), "부정": (220, 60, 60), "중립": (160, 160, 160)}
IMPACT_LABEL  = {"긍정": "매매의견 : 긍정", "부정": "매매의견 : 부정", "중립": "매매의견 : 중립"}

_FFMPEG    = get_setting("FFMPEG_BINARY")
_FONT_DIR  = os.path.join(ASSETS_DIR, "fonts")
_FONT_REG  = os.path.join(_FONT_DIR, "Pretendard-Regular.otf")
_FONT_BOLD = os.path.join(_FONT_DIR, "Pretendard-Bold.otf")

_VOICE = "ko-KR-SunHiNeural"  # Microsoft Azure TTS 한국어 여성 음성

_PRETENDARD_URLS = {
    "Pretendard-Regular.otf": "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Regular.otf",
    "Pretendard-Bold.otf":    "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-Bold.otf",
}


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
        # 다운로드 실패 시 맑은 고딕 fallback
        fallback = r"C:\Windows\Fonts\malgunbd.ttf" if bold else r"C:\Windows\Fonts\malgun.ttf"
        return ImageFont.truetype(fallback, size)


def _clean_script(text: str) -> str:
    text = re.sub(r"[▶▷►◆◇★☆✓✗✘⚠📊🚀🔻]", "", text)
    text = re.sub(r"[\U0001F000-\U0001FFFF]", "", text)
    text = re.sub(r"\$([A-Z]+)", r"\1", text)
    return text.strip()



async def _tts_async(script: str, out_path: str):
    communicate = edge_tts.Communicate(script, _VOICE)
    await communicate.save(out_path)


def _make_audio(script: str, out_path: str):
    """edge-tts (Microsoft Azure)로 고품질 한국어 음성을 생성합니다.
    접속 실패 시 gTTS로 자동 폴백합니다."""
    try:
        asyncio.run(_tts_async(script, out_path))
    except Exception as e:
        print(f"  [!!] edge-tts 실패 ({e}), gTTS로 폴백합니다.")
        from gtts import gTTS
        import shutil
        sentences = [s.strip() for s in re.split(r"(?<=[.!?。])\s+", script.strip()) if s.strip()] or [script]
        tmp_files, sil_idx = [], 0
        for i, sent in enumerate(sentences):
            tmp = out_path.replace(".mp3", f"_s{i}.mp3")
            gTTS(text=sent, lang="ko", slow=False).save(tmp)
            tmp_files.append(tmp)
            if i < len(sentences) - 1:
                sil = out_path.replace(".mp3", f"_sil{sil_idx}.mp3")
                subprocess.run(
                    [_FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                     "-t", "0.5", "-q:a", "9", "-acodec", "libmp3lame", sil],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
                )
                tmp_files.append(sil)
                sil_idx += 1
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


def _draw_text_overlays(img: Image.Image, tickers: list, companies: list,
                        companies_en: list, impact: str,
                        headline_kr: str, reason: str) -> Image.Image:
    """텍스트 패널을 이미지 위에 그립니다."""
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

    # ── 차트 영역은 y ~ y+H_CHART (텍스트 없음, chart_maker가 채움) ──
    y += H_CHART + 20

    # ── 헤드라인 패널 ──
    headline_lines = textwrap.wrap(headline_kr, width=19)[:4]
    ph = len(headline_lines) * 78 + 36
    panel = Image.new("RGBA", (W, ph), (0, 0, 0, 165))
    img.paste(panel, (0, y), panel)
    draw = ImageDraw.Draw(img)
    y += 18
    for line in headline_lines:
        draw.text((44, y), line, font=_font(54, bold=True), fill=TEXT_COLOR)
        y += 78

    # ── 분석 패널 (하단) ──
    reason_lines = textwrap.wrap(reason, width=24)[:3]
    ph2  = len(reason_lines) * 62 + 100
    pan2 = Image.new("RGBA", (W, ph2), (0, 0, 0, 190))
    img.paste(pan2, (0, H - ph2 - 50), pan2)
    draw = ImageDraw.Draw(img)
    y2   = H - ph2 - 18
    draw.text((44, y2), "📊 주가 영향 분석", font=_font(38, bold=True), fill=bar)
    y2  += 62
    for line in reason_lines:
        draw.text((44, y2), line, font=_font(40), fill=GRAY_COLOR)
        y2  += 62

    # 워터마크
    ts = datetime.now().strftime("%Y.%m.%d %H:%M KST")
    draw.text((44, H - 46), f"US Market Flash  |  {ts}",
              font=_font(26), fill=(120, 120, 140))

    return img


def _chart_y_offset(tickers: list) -> int:
    """차트가 붙을 y 좌표 계산 (종목 수에 따라 달라짐)"""
    ticker_count = len(tickers[:3]) if tickers else 1
    opinion_height = 8 + 110 if tickers else 0  # 매매의견 블록 (종목 없으면 0)
    return 30 + ticker_count * 90 + opinion_height  # y after 매매의견


def create_video(headline_kr: str, analysis: dict,
                 image_url: str | None = None,
                 article_url: str | None = None) -> str:
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    companies     = analysis.get("companies", [])
    companies_en  = analysis.get("companies_en", [])
    impact        = analysis.get("impact", "중립")
    reason        = analysis.get("reason", "")
    tickers       = analysis.get("tickers", [])

    # Groq가 생성한 기승전결 나레이션을 TTS 본문으로 사용
    raw_script = analysis.get("narration") or analysis.get("script", headline_kr)
    raw_script = _clean_script(raw_script)

    # 이미지가 없으면 DuckDuckGo 웹 검색으로 보완
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

    # 한국어 회사명 → 영문으로 치환 (TTS 영어 발음)
    for ko, en in zip(companies, companies_en):
        if ko and en:
            raw_script = raw_script.replace(ko, en)

    # 종목 관련 뉴스면 마지막에 한 줄 분석 추가
    if tickers:
        ticker_label = ", ".join(companies_en[:3]) if companies_en else ", ".join(tickers[:3])
        impact_word  = {"긍정": "긍정적", "부정": "부정적", "중립": "중립적"}.get(impact, impact)
        reason_clean = _clean_script(reason)
        summary_line = f"종목 분석. {ticker_label}은 이번 뉴스로 {impact_word} 영향이 예상됩니다. {reason_clean}"
        script = raw_script.rstrip() + " " + summary_line
    else:
        script = raw_script

    # 1. 음성 생성 (문장 사이 0.5초 묵음)
    audio_path = os.path.join(ASSETS_DIR, "tts_temp.mp3")
    _make_audio(script, audio_path)

    # 오디오 길이 측정
    result = subprocess.run(
        [_FFMPEG, "-i", audio_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    )
    duration = 10.0  # fallback
    for line in result.stderr.splitlines():
        if "Duration" in line:
            m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", line)
            if m:
                duration = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
            break

    # 2. 배경 (뉴스 이미지 or 다크)
    bg = _load_background(image_url)

    # 3. 차트 애니메이션 프레임 생성 (영상 전체 길이에 걸쳐 애니메이션)
    FPS = 30
    total_frames = int(duration * FPS)
    bar_color = IMPACT_COLORS.get(impact, IMPACT_COLORS["중립"])
    chart_frames = generate_chart_frames(tickers, total_frames, bar_color, W_CHART, H_CHART)

    chart_y = _chart_y_offset(tickers)
    frames_dir = os.path.join(ASSETS_DIR, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    frame_paths  = []

    for fi in range(total_frames):
        chart_idx = min(fi, len(chart_frames) - 1)
        chart_img = chart_frames[chart_idx]

        frame = bg.copy()
        if chart_img:
            frame.paste(chart_img, (0, chart_y), chart_img)

        frame = _draw_text_overlays(frame, tickers, companies, companies_en,
                                    impact, headline_kr, reason)

        path = os.path.join(frames_dir, f"frame_{fi:05d}.png")
        frame.save(path)
        frame_paths.append(path)

    # 4. ffmpeg로 프레임 + 음성 합성
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

    # 임시 파일 정리 (ffmpeg 프로세스가 파일 점유 해제할 시간 확보)
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
