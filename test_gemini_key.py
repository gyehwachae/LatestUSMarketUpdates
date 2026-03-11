"""
Gemini API 키가 정상인지 REST API로 직접 확인
"""
import requests
from dotenv import load_dotenv
import os

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
print(f"사용 중인 키: ...{key[-6:]}\n")

models = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-002",
]

body = {"contents": [{"parts": [{"text": "Hello, reply with OK only."}]}]}

for model in models:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    r = requests.post(url, json=body, timeout=15)
    status = r.status_code
    if status == 200:
        print(f"✓ {model}: 정상 작동!")
    else:
        msg = r.json().get("error", {}).get("message", "")[:80]
        print(f"✗ {model}: {status} - {msg}")
