"""
X(Twitter) API v2로 뉴스 요약을 트윗합니다.
Free Tier: 월 1,500건 쓰기 가능 (하루 약 50건).
필요 권한: Read and Write (OAuth 1.0a User Context)
"""
import tweepy
from config import (
    X_API_KEY, X_API_SECRET,
    X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
)

_client = None


def _get_client() -> tweepy.Client:
    global _client
    if _client is None:
        _client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET,
        )
    return _client


def post_tweet(analysis: dict, youtube_url: str | None = None) -> str | None:
    """
    분석 결과를 X에 발행합니다.
    youtube_url이 있으면 트윗 끝에 링크를 추가합니다.
    트윗 ID를 반환하며, 실패 시 None을 반환합니다.
    """
    text = analysis.get("x_post", analysis.get("summary", ""))

    if youtube_url:
        text = f"{text}\n\n▶ {youtube_url}"

    # X Free Tier는 280자 제한
    if len(text) > 280:
        text = text[:277] + "..."

    try:
        client = _get_client()
        response = client.create_tweet(text=text)
        tweet_id = response.data["id"]
        print(f"  ✓ X 발행: https://x.com/i/web/status/{tweet_id}")
        return tweet_id
    except tweepy.TweepyException as e:
        print(f"  ✗ X 발행 실패: {e}")
        return None
