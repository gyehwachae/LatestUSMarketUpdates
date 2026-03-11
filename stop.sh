#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "[US Market Pipeline] 중지 중..."

if [ ! -f pipeline.pid ]; then
    echo "[!] 실행 중인 프로세스가 없습니다 (pipeline.pid 없음)"
    exit 1
fi

PROC_PID=$(cat pipeline.pid)

if kill -0 "$PROC_PID" 2>/dev/null; then
    kill "$PROC_PID"
    echo "[OK] 파이프라인 중지됨 (PID: $PROC_PID)"
else
    echo "[!] PID $PROC_PID 프로세스를 찾을 수 없습니다 (이미 종료됨)"
fi

rm -f pipeline.pid
echo "     pipeline.pid 삭제 완료"
