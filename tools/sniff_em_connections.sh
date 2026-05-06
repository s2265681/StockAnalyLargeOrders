#!/bin/bash
# 发现东方财富桌面端的网络连接
# 用法: bash tools/sniff_em_connections.sh

echo "=== 查找东方财富桌面端进程 ==="
EM_PIDS=$(pgrep -if "eastmoney\|em_\|dfcf\|eastmoneychina\|com.eastmoney" 2>/dev/null)

if [ -z "$EM_PIDS" ]; then
    echo "未找到东方财富进程，尝试更宽泛的搜索..."
    # 列出所有可能的相关进程
    ps aux | grep -i -E "eastmoney|em_|dfcf|east|money|财富|stock" | grep -v grep
    echo ""
    echo "请手动确认东方财富的进程名，或者先打开东方财富桌面端"
    exit 1
fi

echo "找到进程 PID: $EM_PIDS"
for pid in $EM_PIDS; do
    echo "  PID $pid: $(ps -p $pid -o comm= 2>/dev/null)"
done

echo ""
echo "=== 活跃网络连接 ==="
for pid in $EM_PIDS; do
    echo "--- PID $pid ---"
    lsof -i -n -P -p $pid 2>/dev/null | grep -E "TCP|UDP" | head -30
done

echo ""
echo "=== 连接的远程服务器 (去重) ==="
for pid in $EM_PIDS; do
    lsof -i -n -P -p $pid 2>/dev/null | grep "ESTABLISHED" | awk '{print $9}' | sed 's/.*->//' | sort -u
done | sort -u

echo ""
echo "=== 远程服务器 DNS 反查 ==="
for pid in $EM_PIDS; do
    lsof -i -n -P -p $pid 2>/dev/null | grep "ESTABLISHED" | awk '{print $9}' | sed 's/.*->//' | cut -d: -f1 | sort -u
done | sort -u | while read ip; do
    hostname=$(host "$ip" 2>/dev/null | grep "domain name" | awk '{print $NF}' | sed 's/\.$//')
    echo "  $ip → ${hostname:-无法反查}"
done
