#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "[US Market Pipeline] 시작 중..."

if [ -f pipeline.pid ]; then
    PROC_PID=$(cat pipeline.pid)
    if kill -0 "$PROC_PID" 2>/dev/null; then
        echo "[!] 이미 실행 중입니다 (PID: $PROC_PID)"
        echo "    재시작하려면 restart.sh 를 실행하세요."
        exit 1
    else
        rm -f pipeline.pid
    fi
fi

PYTHONIOENCODING=utf-8 python -u main.py --loop >> pipeline.log 2>> pipeline_error.log &
echo $! > pipeline.pid

echo "[OK] 파이프라인 시작됨 (PID: $(cat pipeline.pid))"
echo "     로그: pipeline.log"
