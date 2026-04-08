"""
NVIDIA 재무 분석 시각화 - Manim
실행: manim -qh manim_nvda_analysis.py NVDAAnalysis
"""

from manim import *
import numpy as np

# 한글 폰트 설정
Text.set_default(font="NanumSquareRound")

# 색상 정의
NVIDIA_GREEN = "#76B900"
ACCENT_GOLD = "#FFD700"
DEEP_NAVY = "#0a0a1a"
CHART_WHITE = "#FFFFFF"
CHART_GRAY = "#888888"


class NVDAAnalysis(Scene):
    def construct(self):
        # 배경색 설정
        self.camera.background_color = DEEP_NAVY

        # Scene 1: 매출 폭발 성장
        self.play_revenue_scene()
        self.wait(1)
        self.clear()

        # Scene 2: EPS vs 주가
        self.play_eps_vs_price_scene()
        self.wait(1)
        self.clear()

        # Scene 3: 결론
        self.play_conclusion_scene()

    def play_revenue_scene(self):
        """Scene 1: NVIDIA 매출 성장 막대그래프"""

        # 제목
        title = Text("NVIDIA 매출 성장", font_size=48, color=CHART_WHITE)
        subtitle = Text("데이터센터가 이끄는 폭발적 성장", font_size=28, color=CHART_GRAY)
        title_group = VGroup(title, subtitle).arrange(DOWN, buff=0.3)
        title_group.to_edge(UP, buff=0.5)

        self.play(Write(title), run_time=1)
        self.play(FadeIn(subtitle), run_time=0.5)

        # 데이터 (단위: 십억 달러)
        years = ["2021", "2022", "2023", "2024", "2025E"]
        revenues = [16, 26, 27, 60, 130]  # 실제 데이터 기반
        datacenter_pct = [0.4, 0.5, 0.55, 0.8, 0.88]  # 데이터센터 비중

        # 축 생성
        axes = Axes(
            x_range=[0, 6, 1],
            y_range=[0, 140, 20],
            x_length=10,
            y_length=5,
            axis_config={"color": CHART_WHITE, "include_tip": False},
            x_axis_config={"numbers_to_include": []},
            y_axis_config={"numbers_to_include": np.arange(0, 141, 40)},
        )
        axes.shift(DOWN * 0.5)

        # Y축 라벨
        y_label = Text("매출 ($B)", font_size=20, color=CHART_GRAY)
        y_label.next_to(axes.y_axis, UP, buff=0.2)

        self.play(Create(axes), Write(y_label), run_time=1)

        # 막대그래프 생성
        bars = VGroup()
        labels = VGroup()
        dc_bars = VGroup()  # 데이터센터 부분

        bar_width = 0.6
        for i, (year, rev, dc_pct) in enumerate(zip(years, revenues, datacenter_pct)):
            x_pos = i + 1

            # 전체 매출 막대 (회색)
            bar_height = rev / 140 * 5  # 스케일링
            bar = Rectangle(
                width=bar_width,
                height=bar_height,
                fill_color=CHART_GRAY,
                fill_opacity=0.5,
                stroke_color=CHART_WHITE,
                stroke_width=1
            )
            bar.move_to(axes.c2p(x_pos, rev/2))

            # 데이터센터 매출 막대 (NVIDIA Green)
            dc_height = bar_height * dc_pct
            dc_bar = Rectangle(
                width=bar_width,
                height=dc_height,
                fill_color=NVIDIA_GREEN,
                fill_opacity=0.9,
                stroke_width=0
            )
            dc_bar.align_to(bar, DOWN)
            dc_bar.move_to(axes.c2p(x_pos, (rev * dc_pct) / 2))

            # 연도 라벨
            year_label = Text(year, font_size=18, color=CHART_WHITE)
            year_label.next_to(bar, DOWN, buff=0.2)

            # 매출 수치
            rev_label = Text(f"${rev}B", font_size=16, color=CHART_WHITE)
            rev_label.next_to(bar, UP, buff=0.1)

            bars.add(bar)
            dc_bars.add(dc_bar)
            labels.add(year_label, rev_label)

        # 막대 애니메이션 (하나씩 성장)
        for i, (bar, dc_bar) in enumerate(zip(bars, dc_bars)):
            self.play(
                GrowFromEdge(bar, DOWN),
                run_time=0.4
            )
            self.play(
                GrowFromEdge(dc_bar, DOWN),
                run_time=0.3
            )

        self.play(FadeIn(labels), run_time=0.5)

        # 범례
        legend_box = Rectangle(width=3.5, height=1.2, fill_color=DEEP_NAVY, fill_opacity=0.8, stroke_color=CHART_WHITE)
        legend_box.to_corner(UR, buff=0.5)

        dc_legend = Rectangle(width=0.3, height=0.3, fill_color=NVIDIA_GREEN, fill_opacity=0.9)
        dc_text = Text("데이터센터", font_size=16, color=CHART_WHITE)
        dc_group = VGroup(dc_legend, dc_text).arrange(RIGHT, buff=0.2)

        other_legend = Rectangle(width=0.3, height=0.3, fill_color=CHART_GRAY, fill_opacity=0.5)
        other_text = Text("��타 사업", font_size=16, color=CHART_GRAY)
        other_group = VGroup(other_legend, other_text).arrange(RIGHT, buff=0.2)

        legend_content = VGroup(dc_group, other_group).arrange(DOWN, buff=0.3, aligned_edge=LEFT)
        legend_content.move_to(legend_box.get_center())

        self.play(FadeIn(legend_box), FadeIn(legend_content), run_time=0.5)

        # 강조 텍스트
        highlight = Text(
            "데이터센터 매출 비중: 40% → 88%",
            font_size=24,
            color=NVIDIA_GREEN
        )
        highlight.to_edge(DOWN, buff=0.5)

        self.play(Write(highlight), run_time=1)
        self.wait(2)

    def play_eps_vs_price_scene(self):
        """Scene 2: EPS vs 주가 상관관계"""

        # 제목
        title = Text("주가 vs 이익(EPS)", font_size=48, color=CHART_WHITE)
        subtitle = Text("거품이 아닌, 실적이 이끄는 상승", font_size=28, color=CHART_GRAY)
        title_group = VGroup(title, subtitle).arrange(DOWN, buff=0.3)
        title_group.to_edge(UP, buff=0.5)

        self.play(Write(title), run_time=1)
        self.play(FadeIn(subtitle), run_time=0.5)

        # 데이터 (분기별, 2022 Q1 ~ 2025 Q1)
        # 인덱스화된 값 (2022 Q1 = 100)
        quarters = list(range(13))  # 0~12 (13개 분기)
        stock_price = [100, 80, 60, 50, 55, 80, 120, 160, 200, 250, 280, 300, 350]  # 인덱스화
        eps_growth = [100, 90, 70, 60, 65, 90, 130, 180, 220, 280, 310, 340, 380]  # 인덱스화

        # 축 생성
        axes = Axes(
            x_range=[0, 13, 1],
            y_range=[0, 400, 100],
            x_length=10,
            y_length=4.5,
            axis_config={"color": CHART_WHITE, "include_tip": False},
            x_axis_config={"numbers_to_include": []},
            y_axis_config={"numbers_to_include": [100, 200, 300, 400]},
        )
        axes.shift(DOWN * 0.3)

        # 축 라벨
        x_label = Text("2022                    2023                    2024                    2025",
                       font_size=14, color=CHART_GRAY)
        x_label.next_to(axes.x_axis, DOWN, buff=0.3)

        y_label = Text("인덱스 (2022=100)", font_size=16, color=CHART_GRAY)
        y_label.next_to(axes.y_axis, UP, buff=0.2)

        self.play(Create(axes), Write(x_label), Write(y_label), run_time=1)

        # 주가 선그래프 (NVIDIA Green)
        price_points = [axes.c2p(i, p) for i, p in enumerate(stock_price)]
        price_line = VMobject()
        price_line.set_points_smoothly(price_points)
        price_line.set_stroke(color=NVIDIA_GREEN, width=4)

        # EPS 선그래프 (Gold, 점선)
        eps_points = [axes.c2p(i, e) for i, e in enumerate(eps_growth)]
        eps_line = VMobject()
        eps_line.set_points_smoothly(eps_points)
        eps_line.set_stroke(color=ACCENT_GOLD, width=3)

        # 선 그리기 애니메이션
        self.play(Create(price_line), run_time=2)
        self.play(Create(eps_line), run_time=2)

        # 범례
        price_legend = Line(ORIGIN, RIGHT * 0.5, color=NVIDIA_GREEN, stroke_width=4)
        price_text = Text("주가", font_size=18, color=NVIDIA_GREEN)
        price_group = VGroup(price_legend, price_text).arrange(RIGHT, buff=0.2)

        eps_legend = Line(ORIGIN, RIGHT * 0.5, color=ACCENT_GOLD, stroke_width=3)
        eps_text = Text("EPS (이익)", font_size=18, color=ACCENT_GOLD)
        eps_group = VGroup(eps_legend, eps_text).arrange(RIGHT, buff=0.2)

        legend = VGroup(price_group, eps_group).arrange(DOWN, buff=0.2, aligned_edge=LEFT)
        legend.to_corner(UR, buff=0.8)

        self.play(FadeIn(legend), run_time=0.5)

        # 핵심 메시지
        fact_box = Rectangle(
            width=8, height=1.2,
            fill_color=NVIDIA_GREEN,
            fill_opacity=0.2,
            stroke_color=NVIDIA_GREEN,
            stroke_width=2
        )
        fact_box.to_edge(DOWN, buff=0.4)

        fact_text = Text(
            "주가 상승률 ≈ EPS 상승률 → 거품이 아닌 실적 성장",
            font_size=22,
            color=CHART_WHITE
        )
        fact_text.move_to(fact_box.get_center())

        self.play(FadeIn(fact_box), Write(fact_text), run_time=1)
        self.wait(2)

    def play_conclusion_scene(self):
        """Scene 3: 결론"""

        # NVIDIA 로고 스타일 (녹��� 원형)
        logo_circle = Circle(radius=1.5, color=NVIDIA_GREEN, fill_opacity=0.3, stroke_width=4)
        logo_text = Text("NVDA", font_size=60, color=NVIDIA_GREEN, weight=BOLD)
        logo_group = VGroup(logo_circle, logo_text)

        self.play(
            GrowFromCenter(logo_circle),
            Write(logo_text),
            run_time=1.5
        )

        # 글로우 효과
        glow = logo_circle.copy()
        glow.set_stroke(color=NVIDIA_GREEN, width=8, opacity=0.3)
        glow.scale(1.2)

        self.play(
            logo_group.animate.shift(UP * 1.5),
            FadeIn(glow),
            run_time=1
        )

        # 핵심 메시지
        main_quote = Text(
            '"거품일까요? 아닙니다. 이익입니다."',
            font_size=36,
            color=CHART_WHITE
        )
        main_quote.next_to(logo_group, DOWN, buff=1)

        self.play(Write(main_quote), run_time=1.5)

        # 부연 설명
        sub_quote = Text(
            "AI 인프라 확장은 아직 1회초입니다.",
            font_size=24,
            color=ACCENT_GOLD
        )
        sub_quote.next_to(main_quote, DOWN, buff=0.5)

        self.play(FadeIn(sub_quote), run_time=1)

        # 채널 로고
        channel_name = Text(
            "Centsible Fact",
            font_size=28,
            color=CHART_WHITE,
            weight=BOLD
        )
        channel_slogan = Text(
            "Compare, Learn, and Grow",
            font_size=18,
            color=CHART_GRAY
        )
        channel_group = VGroup(channel_name, channel_slogan).arrange(DOWN, buff=0.2)
        channel_group.to_edge(DOWN, buff=0.8)

        self.play(FadeIn(channel_group), run_time=1)

        # 최종 글로우 애니메이션
        self.play(
            logo_circle.animate.set_stroke(opacity=1),
            glow.animate.scale(1.1).set_stroke(opacity=0.5),
            run_time=0.5
        )
        self.play(
            logo_circle.animate.set_stroke(opacity=0.5),
            glow.animate.scale(0.95).set_stroke(opacity=0.2),
            run_time=0.5
        )

        self.wait(2)


class RevenueBarChart(Scene):
    """매출 막대그래프만 별도 렌더링"""
    def construct(self):
        self.camera.background_color = DEEP_NAVY
        scene = NVDAAnalysis()
        scene.camera = self.camera
        scene.play_revenue_scene()


class EPSvsPrice(Scene):
    """EPS vs 주가 그래프만 별도 렌더링"""
    def construct(self):
        self.camera.background_color = DEEP_NAVY
        scene = NVDAAnalysis()
        scene.camera = self.camera
        scene.play_eps_vs_price_scene()


# 실행 방법:
# 전체: manim -pqh manim_nvda_analysis.py NVDAAnalysis
# 매출만: manim -pqh manim_nvda_analysis.py RevenueBarChart
# EPS만: manim -pqh manim_nvda_analysis.py EPSvsPrice
