"""
YouTube Data API v3로 영상을 자동 업로드합니다.
첫 실행 시 브라우저 OAuth 인증이 필요합니다. 이후 token.json에 저장됩니다.
하루 최대 6개 업로드 (10,000 유닛 한도).
"""
import json
import os
from datetime import date

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import YOUTUBE_CLIENT_SECRETS_FILE, MAX_YOUTUBE_UPLOADS_PER_DAY, DATA_DIR

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = "token.json"
UPLOAD_COUNT_FILE = os.path.join(DATA_DIR, "upload_count.json")


def _load_daily_count() -> int:
    if not os.path.exists(UPLOAD_COUNT_FILE):
        return 0
    with open(UPLOAD_COUNT_FILE, "r") as f:
        data = json.load(f)
    if data.get("date") != str(date.today()):
        return 0
    return data.get("count", 0)


def _save_daily_count(count: int):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(UPLOAD_COUNT_FILE, "w") as f:
        json.dump({"date": str(date.today()), "count": count}, f)


def _get_credentials() -> Credentials:
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[Uploader] 인증 갱신 실패: {e}")
                return None
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRETS_FILE, SCOPES)
                # Headless 환경용 수동 인증
                flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
                auth_url, _ = flow.authorization_url(prompt="consent")
                print(f"\n[Uploader] 브라우저에서 다음 URL을 열어 인증하세요:\n{auth_url}\n")
                code = input("인증 코드를 입력하세요: ").strip()
                flow.fetch_token(code=code)
                creds = flow.credentials
            except Exception as e:
                print(f"[Uploader] 인증 실패 (OAuth): {e}")
                return None
        
        if creds:
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
    return creds


def upload_video(video_path: str, title: str, description: str, tags: list[str]) -> str | None:
    """
    영상을 YouTube에 업로드합니다.
    일일 한도 초과 시 None을 반환합니다.
    """
    count = _load_daily_count()
    if count >= MAX_YOUTUBE_UPLOADS_PER_DAY:
        print(f"[Uploader] 일일 업로드 한도({MAX_YOUTUBE_UPLOADS_PER_DAY}건) 도달. 건너뜁니다.")
        return None

    creds = _get_credentials()
    if not creds:
        print("[Uploader] 유효한 인증 정보가 없습니다. 업로드를 건너뜁니다.")
        return None
    
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags,
            "categoryId": "25",  # News & Politics
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    _save_daily_count(count + 1)
    print(f"[Uploader] 업로드 완료: https://youtu.be/{video_id}")
    return video_id


def build_metadata(headline_kr: str, analysis: dict, article_url: str | None = None) -> tuple[str, str, list[str]]:
    """YouTube 제목, 설명, 태그를 생성합니다."""
    impact = analysis.get("impact", "중립")
    tickers = analysis.get("tickers", [])
    companies = analysis.get("companies", [])

    impact_emoji = {"긍정": "🚀", "부정": "🔻", "중립": "📊"}.get(impact, "📊")

    # 제목: 종목이 있으면 포함, 없으면 시장 전반 표기
    if tickers:
        ticker_label = " · ".join(f"${t}" for t in tickers[:2])
        title = f"{impact_emoji} [{ticker_label} 속보] {headline_kr}"
    else:
        title = f"{impact_emoji} [미국 시장 속보] {headline_kr}"

    source_line = f"▶ 원문 기사: {article_url}\n\n" if article_url else ""
    description = (
        f"{analysis.get('summary', '')}\n\n"
        f"▶ 주가 영향: {impact}\n"
        f"▶ 이유: {analysis.get('reason', '')}\n\n"
        f"{source_line}"
        "#미국주식 #주식속보 #Shorts"
    )

    # 태그: 티커 + 회사명 + 공통
    tags = tickers + companies + ["미국주식", "주식속보", "미국시장", "Shorts"]
    return title, description, tags
