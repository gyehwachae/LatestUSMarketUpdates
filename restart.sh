#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "[US Market Pipeline] 재시작 중..."

# 기존 프로세스 중지
if [ -f pipeline.pid ]; then
    PROC_PID=$(cat pipeline.pid)
    if kill -0 "$PROC_PID" 2>/dev/null; then
        kill "$PROC_PID"
        echo "[OK] 기존 프로세스 중지됨 (PID: $PROC_PID)"
    else
        echo "[*] PID $PROC_PID 이미 종료된 상태"
    fi
    rm -f pipeline.pid
    sleep 2
else
    echo "[*] 실행 중인 프로세스 없음, 새로 시작합니다."
fi

# 새 프로세스 시작
PYTHONIOENCODING=utf-8 python -u main.py --loop >> pipeline.log 2>> pipeline_error.log &
echo $! > pipeline.pid

echo "[OK] 파이프라인 재시작 완료 (PID: $(cat pipeline.pid))"
echo "     로그: pipeline.log"
