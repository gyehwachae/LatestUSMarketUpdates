#!/bin/bash
# 매일 오전 데일리 브리핑 실행 스크립트
# crontab 예시: 0 7 * * * /app/LatestUSMarketUpdates/daily_briefing.sh

cd /app/LatestUSMarketUpdates
source venv/bin/activate

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily Briefing 시작" >> pipeline.log
python -c "from modules.daily_briefing import create_daily_briefing; create_daily_briefing()" >> pipeline.log 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily Briefing 완료" >> pipeline.log
