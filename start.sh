#!/bin/bash
# 微信个人信息收集机器人 - 一键启动
# 使用方式: ./start.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 启动个人信息收集系统..."
echo ""

# 1. 检查 OpenClaw Gateway
echo "🔍 检查 OpenClaw Gateway..."
if curl -s --connect-timeout 3 http://localhost:18789/health | grep -q "ok"; then
    echo "✅ OpenClaw Gateway 正常运行"
else
    echo "⚠️ OpenClaw Gateway 未运行，正在启动..."
    openclaw gateway install 2>/dev/null
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.gateway.plist 2>/dev/null
    sleep 2
fi

# 2. 启动微信机器人
echo ""
echo "📱 启动微信机器人..."
cd "$SCRIPT_DIR"
python3 wechat_bot.py start
