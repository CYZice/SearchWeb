#!/bin/bash
# 启动墓志检索系统服务器

PORT=8000
HOST="127.0.0.1"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "检查端口 $PORT 上的残留进程..."
# Windows netstat output format: TCP 127.0.0.1:8000 0.0.0.0:0 LISTENING 43612
PID_LIST=$(netstat -ano 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | sort -u)

if [ -n "$PID_LIST" ]; then
    echo "发现残留进程: $PID_LIST"
    for PID in $PID_LIST; do
        if [ "$PID" != "0" ] && [ -n "$PID" ]; then
            echo "正在终止 PID $PID..."
            taskkill //F //PID $PID 2>/dev/null
        fi
    done
    sleep 1
fi

# 再次检查并清理
REMAINING=$(netstat -ano 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | sort -u)
if [ -n "$REMAINING" ]; then
    echo "仍有进程残留，尝试强制清理..."
    for PID in $REMAINING; do
        if [ "$PID" != "0" ] && [ -n "$PID" ]; then
            taskkill //F //PID $PID 2>/dev/null
        fi
    done
    sleep 2
fi

echo "启动服务器 on $HOST:$PORT..."
cd "$DIR"
uvicorn app.main:app --host $HOST --port $PORT
