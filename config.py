import os
from dotenv import load_dotenv

load_dotenv()

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")

# X (Twitter) API v2 - developer.twitter.com
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

# YouTube 영상 업로드 기준 중요도 점수 (1~10)
YOUTUBE_MIN_IMPORTANCE = int(os.getenv("YOUTUBE_MIN_IMPORTANCE", "7"))

# 수집할 뉴스 카테고리: general | forex | crypto | merger
NEWS_CATEGORY = os.getenv("NEWS_CATEGORY", "general")

ARTICLE_DELAY_SECONDS = 5    # 기사 간 API 호출 간격 (초, Groq은 빠르므로 5초면 충분)
MAX_YOUTUBE_UPLOADS_PER_DAY = 6
VIDEO_OUTPUT_DIR = "output/videos"
DATA_DIR = "data"
ASSETS_DIR = "assets"
