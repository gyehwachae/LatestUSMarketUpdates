#!/usr/bin/env bash
# crontab용 1회 실행 스크립트
# crontab: 0 6 * * 1-6 /path/to/project/cron_run.sh

cd "$(dirname "$0")"

# 가상환경 활성화
source venv/bin/activate

PYTHONIOENCODING=utf-8 python main.py >> pipeline.log 2>> pipeline_error.log
