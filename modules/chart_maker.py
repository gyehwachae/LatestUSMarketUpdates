"""
yfinance + Pillow로 주식 차트 애니메이션 프레임을 생성합니다.
matplotlib 없이 순수 Pillow로 그립니다.
"""
import os
from PIL import Image, ImageDraw

try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    _HAS_YF = False

W_CHART, H_CHART = 1080, 680
PAD = 60


def _fetch_prices(ticker: str) -> list[float]:
    if not _HAS_YF or not ticker:
        return []
    try:
        data = yf.download(ticker, period="5d", interval="1h", progress=False, auto_adjust=True)
        if data.empty:
            return []
        return [float(v) for v in data["Close"].dropna().tolist()]
    except Exception:
        return []


def _draw_chart_frame(prices: list[float], n_show: int,
                      bar_color: tuple, width: int = W_CHART, height: int = H_CHART) -> Image.Image:
    """prices 중 n_show개까지 그린 차트 프레임을 반환합니다."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if len(prices) < 2 or n_show < 2:
        return img

    display = prices[:n_show]
    total   = len(prices)
    p_min   = min(display) * 0.998
    p_max   = max(display) * 1.002
    p_range = p_max - p_min if p_max != p_min else 1

    chart_w = width  - PAD * 2
    chart_h = height - PAD * 2

    def to_xy(i, price):
        x = PAD + int(chart_w * i / (total - 1))
        y = PAD + int(chart_h * (1 - (price - p_min) / p_range))
        return x, y

    # 그리드 라인
    for gi in range(5):
        gy = PAD + int(chart_h * gi / 4)
        draw.line([(PAD, gy), (width - PAD, gy)], fill=(80, 80, 110, 120), width=1)

    # 면적 채우기
    points = [to_xy(i, p) for i, p in enumerate(display)]
    if len(points) >= 2:
        fill_pts = [(PAD, PAD + chart_h)] + points + [(points[-1][0], PAD + chart_h)]
        r, g, b = bar_color[:3]
        draw.polygon(fill_pts, fill=(r, g, b, 35))

        # 라인
        for i in range(len(points) - 1):
            draw.line([points[i], points[i+1]], fill=(r, g, b, 220), width=4)

        # 현재가 점
        lx, ly = points[-1]
        draw.ellipse([lx-8, ly-8, lx+8, ly+8], fill=(r, g, b, 255))

    return img


def generate_chart_frames(tickers: list, n_frames: int,
                          bar_color: tuple,
                          width: int = W_CHART, height: int = H_CHART) -> list:
    """
    n_frames개의 차트 프레임(PIL.Image RGBA)을 반환합니다.
    데이터가 없으면 빈 투명 이미지 리스트를 반환합니다.
    """
    prices = []
    for t in tickers[:1]:
        prices = _fetch_prices(t)
        if prices:
            break

    if len(prices) < 2:
        blank = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        return [blank] * n_frames

    frames = []
    for i in range(n_frames):
        # 20% ~ 100% 범위로 점진적 표시
        ratio   = 0.2 + 0.8 * (i / max(n_frames - 1, 1))
        n_show  = max(2, int(len(prices) * ratio))
        frames.append(_draw_chart_frame(prices, n_show, bar_color, width, height))

    return frames
