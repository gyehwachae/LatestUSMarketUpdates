"""
종목 모멘텀 분석 전용 YouTube Shorts 영상 생성
- 기술적 신호 섹션 (MA 정배열, RSI, 52주 고점)
- 펀더멘털 섹션 (PEG, EPS/매출 성장률, 마진)
- 6개월 차트 + 이동평균선
- 트레이딩 전략 (신호, 진입점, 손절, 목표가)
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
from modules.daily_briefing import COMPANY_NAMES

W, H = 1080, 1920

# 색상 팔레트
COLORS = {
    "강력매수": {
        "primary": (0, 220, 100),
        "bg_top": (8, 35, 25),
        "bg_bottom": (5, 20, 18),
        "badge": (0, 200, 90),
    },
    "매수": {
        "primary": (0, 180, 120),
        "bg_top": (10, 32, 28),
        "bg_bottom": (6, 18, 20),
        "badge": (0, 160, 100),
    },
    "관망": {
        "primary": (100, 150, 255),
        "bg_top": (15, 20, 40),
        "bg_bottom": (10, 12, 30),
        "badge": (80, 130, 220),
    },
    "매도": {
        "primary": (230, 70, 70),
        "bg_top": (40, 15, 20),
        "bg_bottom": (25, 10, 15),
        "badge": (200, 60, 60),
    },
}

TEXT_WHITE = (255, 255, 255)
TEXT_GRAY = (180, 180, 190)
TEXT_DARK = (40, 40, 50)
GREEN = (0, 210, 120)
RED = (230, 70, 70)
GOLD = (255, 200, 80)
BLUE = (80, 140, 255)

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
    has_batchim = {'0', '1', '3', '6', '7', '8'}
    josa_pairs = [
        ('와', '과'), ('는', '은'), ('가', '이'), ('를', '을'),
        ('로', '으로'), ('라', '이라'), ('랑', '이랑'),
    ]

    for wrong_when_batchim, correct_when_batchim in josa_pairs:
        pattern = rf'(\d)({re.escape(wrong_when_batchim)})(?=\s|$|[,.]|[가-힣])'
        def replace_josa(m):
            digit = m.group(1)
            if digit in has_batchim:
                return digit + correct_when_batchim
            return m.group(0)
        text = re.sub(pattern, replace_josa, text)

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
    text = _fix_number_josa(text)
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

def _create_gradient_background(verdict: str) -> Image.Image:
    colors = COLORS.get(verdict, COLORS["관망"])
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
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)


# ──────────────────────────── 차트 생성 ────────────────────────────

def _draw_stock_chart(prices: list[float], ma_50: float, ma_200: float,
                      bar_color: tuple, n_show: int,
                      width: int = 1000, height: int = 400) -> Image.Image:
    """6개월 주가 차트 + 이동평균선"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if len(prices) < 10:
        return img

    pad = 40
    chart_w = width - pad * 2
    chart_h = height - pad * 2

    display = prices[:n_show] if n_show < len(prices) else prices
    total = len(prices)

    p_min = min(display) * 0.97
    p_max = max(display) * 1.03
    p_range = p_max - p_min if p_max != p_min else 1

    def to_xy(i, price, total_pts):
        x = pad + int(chart_w * i / max(total_pts - 1, 1))
        y = pad + int(chart_h * (1 - (price - p_min) / p_range))
        return x, y

    # 그리드 라인
    for gi in range(5):
        gy = pad + int(chart_h * gi / 4)
        draw.line([(pad, gy), (width - pad, gy)], fill=(60, 65, 85, 100), width=1)

    # 가격 라벨
    font_small = _font(18)
    for gi in range(5):
        gy = pad + int(chart_h * gi / 4)
        price_label = p_max - (p_max - p_min) * (gi / 4)
        draw.text((5, gy - 10), f"${price_label:.0f}", font=font_small, fill=(100, 105, 120))

    # 면적 채우기
    points = [to_xy(i, p, len(display)) for i, p in enumerate(display)]
    if len(points) >= 2:
        fill_pts = [(pad, pad + chart_h)] + points + [(points[-1][0], pad + chart_h)]
        r, g, b = bar_color[:3]
        draw.polygon(fill_pts, fill=(r, g, b, 30))

        # 메인 라인
        for i in range(len(points) - 1):
            draw.line([points[i], points[i + 1]], fill=(r, g, b, 255), width=3)

        # 현재가 점
        lx, ly = points[-1]
        draw.ellipse([lx - 6, ly - 6, lx + 6, ly + 6], fill=(r, g, b, 255))

    # 이동평균선 (전체 차트에 수평선으로 표시)
    if p_min <= ma_50 <= p_max:
        ma50_y = pad + int(chart_h * (1 - (ma_50 - p_min) / p_range))
        draw.line([(pad, ma50_y), (width - pad, ma50_y)], fill=(255, 200, 80, 180), width=2)
        draw.text((width - pad - 60, ma50_y - 18), "50MA", font=font_small, fill=GOLD)

    if p_min <= ma_200 <= p_max:
        ma200_y = pad + int(chart_h * (1 - (ma_200 - p_min) / p_range))
        draw.line([(pad, ma200_y), (width - pad, ma200_y)], fill=(150, 150, 255, 180), width=2)
        draw.text((width - pad - 70, ma200_y + 2), "200MA", font=font_small, fill=BLUE)

    return img


# ──────────────────────────── 레이아웃 ────────────────────────────

def _draw_stock_layout(img: Image.Image, result: dict, chart_frame: Image.Image | None = None) -> Image.Image:
    """종목 분석 레이아웃 렌더링"""
    stock_data = result["stock_data"]
    analysis = result["analysis"]
    market = result["market"]

    ticker = stock_data["ticker"]
    name = stock_data["name"]
    sector = stock_data["sector"]
    tech = stock_data["technical"]
    fund = stock_data["fundamental"]
    strategy = analysis["trading_strategy"]
    verdict = analysis["verdict"]

    colors = COLORS.get(verdict, COLORS["관망"])
    primary = colors["primary"]
    badge_color = colors["badge"]

    draw = ImageDraw.Draw(img)

    # 상단/하단 컬러 바
    draw.rectangle([(0, 0), (W, 6)], fill=primary)
    draw.rectangle([(0, H - 6), (W, H)], fill=primary)

    y = 35

    # ── 타이틀 ──
    draw.text((50, y), "MOMENTUM ANALYSIS", font=_font(30, bold=True), fill=GOLD)
    ts = datetime.now().strftime("%Y.%m.%d")
    draw.text((W - 180, y + 5), ts, font=_font(24), fill=TEXT_GRAY)
    y += 60

    # ── 종목 헤더 ──
    _draw_rounded_rect(draw, (50, y, 350, y + 70), 10, (25, 28, 42))
    draw.text((70, y + 12), f"${ticker}", font=_font(40, bold=True), fill=primary)
    draw.text((370, y + 8), name[:20], font=_font(28), fill=TEXT_WHITE)
    draw.text((370, y + 42), sector[:20], font=_font(22), fill=TEXT_GRAY)
    y += 90

    # ── 판정 배지 ──
    verdict_text = f"📌 {verdict}"
    confidence_text = f"신뢰도: {analysis['confidence']}"
    _draw_rounded_rect(draw, (50, y, 250, y + 50), 8, badge_color)
    draw.text((70, y + 8), verdict_text, font=_font(28, bold=True), fill=TEXT_WHITE)
    draw.text((270, y + 15), confidence_text, font=_font(22), fill=TEXT_GRAY)
    y += 70

    # ── 기술적 신호 섹션 ──
    _draw_rounded_rect(draw, (40, y, W - 40, y + 180), 12, (20, 24, 38))
    draw.text((60, y + 10), "📈 기술적 신호", font=_font(24, bold=True), fill=GOLD)

    # 왼쪽 컬럼
    # MA 정배열
    ma_text = "정배열 ✅" if tech["ma_alignment"] else "역배열 ❌"
    ma_color = GREEN if tech["ma_alignment"] else RED
    draw.text((60, y + 42), f"MA: {ma_text}", font=_font(22), fill=ma_color)

    # RSI
    rsi_color = GREEN if tech["rsi_signal"] == "강세" else (RED if tech["rsi_signal"] in ["과열", "극과열"] else TEXT_GRAY)
    draw.text((60, y + 72), f"RSI: {tech['rsi']} ({tech['rsi_signal']})", font=_font(22), fill=rsi_color)

    # 이격도
    disparity = tech.get("disparity_50", 0)
    disparity_signal = tech.get("disparity_signal", "정상")
    disp_color = RED if "과열" in disparity_signal else (GREEN if "반등" in disparity_signal else TEXT_GRAY)
    draw.text((60, y + 102), f"이격도: {disparity}% ({disparity_signal})", font=_font(20), fill=disp_color)

    # 베타
    beta = tech.get("beta")
    beta_signal = tech.get("beta_signal", "N/A")
    beta_color = RED if beta and beta > 1.5 else TEXT_GRAY
    beta_text = f"베타: {beta} ({beta_signal})" if beta else "베타: N/A"
    draw.text((60, y + 132), beta_text, font=_font(20), fill=beta_color)

    # 오른쪽 컬럼: 가격 정보
    draw.text((550, y + 42), f"현재가: ${tech['price']}", font=_font(24, bold=True), fill=TEXT_WHITE)
    draw.text((550, y + 75), f"50일선: ${tech['ma_50']}", font=_font(20), fill=GOLD)
    draw.text((550, y + 102), f"200일선: ${tech['ma_200']}", font=_font(20), fill=BLUE)
    draw.text((550, y + 132), f"52주高 대비: {tech['from_high_pct']}%", font=_font(20), fill=TEXT_GRAY)

    y += 195

    # ── 펀더멘털 섹션 ──
    _draw_rounded_rect(draw, (40, y, W - 40, y + 160), 12, (20, 24, 38))
    draw.text((60, y + 10), "📊 펀더멘털", font=_font(24, bold=True), fill=GOLD)

    # 왼쪽 컬럼
    # PEG
    peg_color = GREEN if fund["peg_signal"] == "저평가" else (RED if fund["peg_signal"] == "고평가" else TEXT_GRAY)
    peg_text = f"PEG: {fund['peg_ratio']} ({fund['peg_signal']})" if fund["peg_ratio"] else "PEG: N/A"
    draw.text((60, y + 42), peg_text, font=_font(22), fill=peg_color)

    # EPS vs 매출 성장률
    growth_quality = fund.get("growth_quality", "N/A")
    gq_color = GREEN if growth_quality in ["우수 (영업 레버리지)", "양호"] else TEXT_GRAY
    eps_text = f"EPS: {fund['eps_growth']}%" if fund["eps_growth"] else "EPS: N/A"
    rev_text = f"매출: {fund['revenue_growth']}%" if fund["revenue_growth"] else "매출: N/A"
    draw.text((60, y + 72), f"{eps_text} / {rev_text}", font=_font(20), fill=gq_color)

    # Rule of 40
    rule_of_40 = fund.get("rule_of_40")
    rule_of_40_signal = fund.get("rule_of_40_signal", "N/A")
    r40_color = GREEN if rule_of_40 and rule_of_40 >= 40 else TEXT_GRAY
    r40_text = f"Rule of 40: {rule_of_40}% ({rule_of_40_signal})" if rule_of_40 else "Rule of 40: N/A"
    draw.text((60, y + 102), r40_text, font=_font(20), fill=r40_color)

    # 오른쪽 컬럼
    # Gross Margin
    margin_text = f"GM: {fund['gross_margin']}%" if fund["gross_margin"] else "GM: N/A"
    margin_color = GREEN if fund["gross_margin_trend"] in ["우수", "양호"] else TEXT_GRAY
    draw.text((550, y + 42), margin_text, font=_font(20), fill=margin_color)

    # Operating Margin
    op_margin = fund.get("operating_margin")
    op_text = f"OM: {op_margin}%" if op_margin else "OM: N/A"
    draw.text((700, y + 42), op_text, font=_font(20), fill=TEXT_GRAY)

    # FCF
    fcf = fund.get("free_cash_flow")
    if fcf:
        if fcf >= 1e9:
            fcf_str = f"FCF: ${fcf / 1e9:.1f}B"
        elif fcf >= 1e6:
            fcf_str = f"FCF: ${fcf / 1e6:.0f}M"
        else:
            fcf_str = "FCF: N/A"
        fcf_color = GREEN if fcf > 0 else RED
    else:
        fcf_str = "FCF: N/A"
        fcf_color = TEXT_GRAY
    draw.text((550, y + 72), fcf_str, font=_font(20), fill=fcf_color)

    # ROIC
    roic = fund.get("roic")
    roic_text = f"ROIC: {roic}%" if roic else "ROIC: N/A"
    roic_color = GREEN if roic and roic > 15 else TEXT_GRAY
    draw.text((700, y + 72), roic_text, font=_font(20), fill=roic_color)

    y += 175

    # ── 시장 환경 섹션 (작은 인라인) ──
    vix = market.get("vix")
    fear_greed = market.get("fear_greed")
    if vix or fear_greed:
        vix_str = f"VIX: {vix}" if vix else ""
        fg_str = f"F&G: {int(fear_greed)}" if fear_greed else ""
        market_str = f"📉 {vix_str}  {fg_str}".strip()
        fg_color = RED if fear_greed and fear_greed >= 75 else (GREEN if fear_greed and fear_greed <= 25 else TEXT_GRAY)
        draw.text((60, y), market_str, font=_font(20), fill=fg_color)
        y += 30

    # ── 차트 영역 ──
    if chart_frame:
        chart_y = y
        chart_x = 40
        img.paste(chart_frame, (chart_x, chart_y), chart_frame)
        y += chart_frame.height + 15

    # ── 트레이딩 전략 섹션 ──
    _draw_rounded_rect(draw, (40, y, W - 40, y + 160), 12, (25, 28, 42))
    draw.text((60, y + 10), "📌 트레이딩 전략", font=_font(24, bold=True), fill=primary)

    signal_color = GREEN if strategy["signal"] == "매수" else (RED if strategy["signal"] == "매도" else BLUE)
    draw.text((60, y + 42), f"• 신호: {strategy['signal']}", font=_font(22, bold=True), fill=signal_color)
    draw.text((60, y + 72), f"• 진입: {strategy['entry_point'][:30]}", font=_font(20), fill=TEXT_GRAY)
    draw.text((60, y + 100), f"• 손절: {strategy['stop_loss'][:30]}", font=_font(20), fill=RED)
    draw.text((60, y + 128), f"• 목표: {strategy['target'][:30]}", font=_font(20), fill=GREEN)

    # 비중 제안
    position_size = strategy.get("position_size", "N/A")
    if position_size and position_size != "N/A":
        draw.text((550, y + 72), f"비중: {position_size[:15]}", font=_font(20), fill=TEXT_GRAY)

    # ── 워터마크 ──
    draw.text((50, H - 50), "US Market Flash  |  모멘텀 종목 분석",
              font=_font(22), fill=(70, 75, 90))

    return img


def _draw_subtitle(img: Image.Image, text: str, verdict: str) -> Image.Image:
    """현재 문장을 하단 자막으로 렌더링"""
    if not text:
        return img

    colors = COLORS.get(verdict, COLORS["관망"])
    primary = colors["primary"]

    lines = textwrap.wrap(text, width=22)[:3]
    if not lines:
        return img

    font = _font(42, bold=True)
    line_h = 56
    pad = 22
    ph = len(lines) * line_h + pad * 2
    y_start = H - ph - 70

    # 자막 배경 (반투명 + 테두리)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # 배경 박스
    _draw_rounded_rect(overlay_draw, (30, y_start, W - 30, y_start + ph), 15, (12, 14, 24, 235))

    # 왼쪽 강조 바
    overlay_draw.rectangle([(30, y_start), (38, y_start + ph)], fill=primary + (255,))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)
    y = y_start + pad
    for line in lines:
        # 텍스트 그림자
        draw.text((60, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((58, y), line, font=font, fill=TEXT_WHITE)
        y += line_h

    return img


# ──────────────────────────── 영상 생성 ────────────────────────────

def create_stock_video(result: dict) -> str:
    """종목 분석 영상 생성"""
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    stock_data = result["stock_data"]
    analysis = result["analysis"]
    ticker = stock_data["ticker"]
    verdict = analysis["verdict"]

    # 나레이션 스크립트 준비
    raw_script = analysis.get("narration", "")
    if not raw_script:
        raw_script = f"{stock_data['name']} 종목 분석입니다. {analysis.get('technical_summary', '')} {analysis.get('fundamental_summary', '')}"

    raw_script = _clean_script(raw_script)

    # 한국어 회사명을 영문으로 변환 (TTS용)
    # COMPANY_NAMES의 역맵핑
    ko_to_en = {v: k for k, v in COMPANY_NAMES.items()}
    for ko, en in ko_to_en.items():
        raw_script = raw_script.replace(ko, en)

    script = raw_script

    # 1. 문장별 TTS 생성 + 자막 타이밍
    audio_path = os.path.join(ASSETS_DIR, f"stock_tts_{ticker}.mp3")
    print(f"  [>>] TTS 생성 중 ({len(_split_sentences(script))}문장)...")
    timings = _make_audio_with_timing(script, audio_path)
    duration = (timings[-1][2] + 0.5) if timings else 10.0
    print(f"  [OK] TTS 완료: {len(timings)}문장, {duration:.1f}초")

    # 2. 그라데이션 배경 생성
    bg = _create_gradient_background(verdict)
    print(f"  [OK] 배경 생성 ({verdict})")

    # 3. 차트 프레임 생성
    FPS = 30
    total_frames = int(duration * FPS)
    prices = stock_data["price_history"]
    tech = stock_data["technical"]
    colors = COLORS.get(verdict, COLORS["관망"])
    bar_color = colors["primary"]

    frames_dir = os.path.join(ASSETS_DIR, f"stock_frames_{ticker}")
    os.makedirs(frames_dir, exist_ok=True)
    frame_paths = []

    print(f"  [>>] {total_frames}개 프레임 생성 중...")

    for fi in range(total_frames):
        current_time = fi / FPS

        # 현재 시간에 해당하는 자막 선택
        subtitle = ""
        for sent_text, start, end in timings:
            if start <= current_time < end:
                subtitle = sent_text
                break

        # 차트 애니메이션 (20% → 100% 점진적 표시)
        ratio = 0.2 + 0.8 * (fi / max(total_frames - 1, 1))
        n_show = max(10, int(len(prices) * ratio))

        chart_frame = _draw_stock_chart(
            prices, tech["ma_50"], tech["ma_200"],
            bar_color, n_show,
            width=1000, height=380
        )

        frame = bg.copy()

        # 레이아웃 렌더링
        frame = _draw_stock_layout(frame, result, chart_frame=chart_frame)

        # 자막 렌더링
        frame = _draw_subtitle(frame, subtitle, verdict)

        path = os.path.join(frames_dir, f"frame_{fi:05d}.png")
        frame.save(path)
        frame_paths.append(path)

    print(f"  [OK] 프레임 생성 완료")

    # 4. ffmpeg: 프레임 + 음성 합성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(VIDEO_OUTPUT_DIR, f"stock_{ticker}_{timestamp}.mp4")

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
    print(f"  [OK] 영상 인코딩 완료")

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


def build_stock_metadata(result: dict) -> tuple[str, str, list[str]]:
    """YouTube 제목, 설명, 태그 생성"""
    stock_data = result["stock_data"]
    analysis = result["analysis"]

    ticker = stock_data["ticker"]
    name = stock_data["name"]
    verdict = analysis["verdict"]
    strategy = analysis["trading_strategy"]

    # 판정별 이모지
    verdict_emoji = {
        "강력매수": "🚀",
        "매수": "📈",
        "관망": "⏸️",
        "매도": "📉",
    }.get(verdict, "📊")

    # 한글 회사명
    kr_name = COMPANY_NAMES.get(ticker, name)

    title = f"{verdict_emoji} [{ticker}] {kr_name} 모멘텀 분석 | {verdict} 신호"

    moat = analysis.get('moat_analysis', '')
    moat_section = f"\n[경제적 해자]\n{moat}\n" if moat else ""

    description = f"""📊 {kr_name} ({ticker}) 모멘텀 투자 분석

[기술적 분석]
{analysis.get('technical_summary', '')}

[펀더멘털 분석]
{analysis.get('fundamental_summary', '')}
{moat_section}
[트레이딩 전략]
• 신호: {strategy['signal']}
• 진입: {strategy['entry_point']}
• 손절: {strategy['stop_loss']}
• 목표: {strategy['target']}
• 비중: {strategy.get('position_size', 'N/A')}

⚠️ 본 영상은 투자 참고용이며, 투자 결정은 본인 책임입니다.
"예측이 아닌 대응" - 손절 라인을 반드시 지키세요!

#미국주식 #{ticker} #{kr_name} #모멘텀투자 #주식분석 #Shorts

🤖 Generated with Claude Code
"""

    tags = [
        ticker, kr_name, name,
        "미국주식", "모멘텀투자", "주식분석", "기술적분석",
        "Shorts", verdict, stock_data["sector"]
    ]

    return title, description, tags
