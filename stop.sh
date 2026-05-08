#!/bin/bash
# 停止墓志检索系统服务器

PORT=8000

echo "查找端口 $PORT 上的进程..."
PID_LIST=$(netstat -ano 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | sort -u)

if [ -z "$PID_LIST" ]; then
    echo "端口 $PORT 上没有运行中的进程"
    exit 0
fi

echo "发现进程: $PID_LIST"
for PID in $PID_LIST; do
    if [ "$PID" != "0" ] && [ -n "$PID" ]; then
        echo "正在终止 PID $PID..."
        taskkill //F //PID $PID 2>/dev/null
    fi
done

# 验证是否已停止
sleep 1
REMAINING=$(netstat -ano 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | sort -u)
if [ -n "$REMAINING" ]; then
    echo "警告: 仍有进程残留: $REMAINING"
    exit 1
else
    echo "端口 $PORT 已成功释放"
    exit 0
fi
