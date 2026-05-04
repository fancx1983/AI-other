#!/usr/bin/env python3
"""
微信信息收集机器人
- 入口：微信「文件传输助手」或给自己发消息
- 消息自动转发到 OpenClaw Gateway 处理
- 处理结果回写到 IMA / LLM Wiki / 豆瓣

使用方式:
  python3 wechat_bot.py start      # 启动机器人
  python3 wechat_bot.py test      # 测试 OpenClaw 连接
  python3 wechat_bot.py setup     # 首次设置
"""

import os
import sys
import json
import time
import subprocess
import webbrowser
import re
from pathlib import Path

# itchat
import itchat
from itchat.content import TEXT, MAP, CARD, NOTE, SHARING, PICTURE, VIDEO, ATTACHMENT, FRIENDS

# ============ 配置 ============
OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://localhost:18789")
BOT_NAME = "个人信息收集助手"

STATE_FILE = Path(__file__).parent / "bot_state.json"
LOG_FILE = Path(__file__).parent / "wechat_bot.log"


def log(msg):
    """写入日志"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    """加载状态"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"logged_in": False, "user_id": None, "file_helper_id": None}


def save_state(state):
    """保存状态"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============ OpenClaw Gateway 交互 ============
def notify_openclaw(content: str, source: str = "wechat", user: str = ""):
    """发送消息到 OpenClaw Gateway"""
    import requests

    payload = {
        "content": content,
        "source": source,
        "user": user,
        "timestamp": int(time.time()),
    }

    try:
        resp = requests.post(
            f"{OPENCLAW_URL}/webhook/inbox",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            log(f"⚠️ OpenClaw 返回非200: {resp.status_code}")
            return None
    except requests.exceptions.ConnectionError:
        log("❌ 无法连接到 OpenClaw Gateway，请确认服务已启动")
        return None
    except Exception as e:
        log(f"❌ OpenClaw 请求失败: {e}")
        return None


def check_openclaw():
    """检查 OpenClaw 连接状态"""
    import requests
    try:
        resp = requests.get(f"{OPENCLAW_URL}/health", timeout=5)
        if resp.status_code == 200 and resp.json().get("ok"):
            print(f"✅ OpenClaw Gateway 正常: {resp.json()}")
            return True
    except Exception as e:
        print(f"❌ OpenClaw Gateway 连接失败: {e}")
    return False


# ============ 内容识别与分发 ============
def parse_and_route(content: str) -> str:
    """识别内容类型并路由到对应工具

    Returns:
        状态描述字符串
    """
    content_lower = content.lower()

    # 1. 检测豆瓣链接
    douban_patterns = [
        r"douban\.com/(?:subject|film|book|music)/(\d+)",
        r"movie\.douban\.com/subject/(\d+)",
        r"book\.douban\.com/subject/(\d+)",
    ]
    for pattern in douban_patterns:
        match = re.search(pattern, content)
        if match:
            subject_id = match.group(1)
            # 判断类型
            if "book.douban" in content or pattern == r"book\.douban\.com/subject/(\d+)":
                return f"douban_book:{subject_id}"
            return f"douban_movie:{subject_id}"

    # 2. 检测待办关键字
    todo_keywords = ["待办", "todo", "记得", "要做", "要搞", "待做", "TODO"]
    if any(kw in content for kw in todo_keywords):
        return "ima_todo"

    # 3. 检测感想/灵感关键字
    inspiration_keywords = ["感想", "想法", "感悟", "思考", "启发", "觉得", "我认为"]
    if any(kw in content for kw in inspiration_keywords):
        return "ima_note"

    # 4. 检测公众号/文章链接
    if re.search(r"https?://[^\s]+", content):
        return "llm_wiki"

    # 5. 默认存入 IMA 通用收集箱
    return "ima_inbox"


def handle_douban_add(subject_id: str, media_type: str = "movie") -> str:
    """通过豆瓣机器人添加想看"""
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).parent / "douban_bot.py"),
                "add",
                media_type,
                subject_id,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path(__file__).parent),
        )
        return result.stdout + result.stderr
    except Exception as e:
        return f"豆瓣操作失败: {e}"


# ============ 微信消息处理 ============
def handle_text(msg):
    """处理文本消息"""
    content = msg["Text"].strip()
    user_id = msg["FromUserName"]
    to_user_id = msg.get("ToUserName", "")
    
    # 只处理发给"文件传输助手"的消息
    if to_user_id != "filehelper":
        return
    
    log(f"📩 收到消息 [文件传输助手]: {content[:80]}")

    # 路由
    route = parse_and_route(content)
    log(f"🔀 路由结果: {route}")

    # 发送确认消息
    reply = ""

    if route.startswith("douban_"):
        # route 格式: "douban_movie:12345" 或 "douban_book:12345"
        prefix, sid = route.split(":", 1)
        media = prefix.split("_")[1]  # "douban_movie" -> "movie"
        reply = f"🎬 检测到豆瓣内容，正在添加到「想{media_type_label(media)}」..."
        result = handle_douban_add(sid, media)
        reply += f"\n\n✅ 已尝试添加到豆瓣\n{result[:200]}"

    elif route == "ima_todo":
        reply = "✅ 已识别为待办事项，正在存入 IMA..."
        # 发送到 OpenClaw 处理
        resp = notify_openclaw(content, "wechat_todo", user_id)
        if resp:
            reply = "✅ 已记入 IMA 待办！"

    elif route == "ima_note":
        reply = "📝 已识别为感想，正在存入 IMA..."
        resp = notify_openclaw(content, "wechat_note", user_id)
        if resp:
            reply = "📝 已存入 IMA 感想收集！"

    elif route == "llm_wiki":
        reply = "📚 检测到文章链接，正在摄入 LLM Wiki..."
        resp = notify_openclaw(content, "wechat_article", user_id)
        if resp:
            reply = "📚 已存入 LLM Wiki！"

    else:  # ima_inbox
        reply = "📥 已收到，正在整理..."
        resp = notify_openclaw(content, "wechat_inbox", user_id)
        if resp:
            reply = "✅ 已存入 IMA 收集箱！"

    # 回复消息
    try:
        msg.user.send(reply)
        log(f"📤 回复: {reply[:80]}")
    except Exception as e:
        log(f"⚠️ 回复失败: {e}")


def media_type_label(media):
    labels = {"movie": "看", "book": "读", "music": "听"}
    return labels.get(media, "看")


# ============ 启动 ============
def start_bot():
    """启动微信机器人"""
    log("=" * 50)
    log("🚀 启动微信个人信息收集机器人")
    log("=" * 50)

    # 检查 OpenClaw
    print("\n🔍 检查 OpenClaw Gateway...")
    if not check_openclaw():
        print("⚠️ 警告: OpenClaw Gateway 未运行，功能将受限")
        print("   请先运行: openclaw gateway install && openclaw gateway start")

    # 注册消息处理
    @itchat.msg_register(TEXT)
    def text_handler(msg):
        handle_text(msg)

    @itchat.msg_register(SHARING)
    def sharing_handler(msg):
        """处理分享内容"""
        log(f"📩 收到分享: {msg['Text']}")
        # 转发分享链接
        resp = notify_openclaw(msg["Text"], "wechat_share", msg["FromUserName"])
        if resp:
            msg.user.send("✅ 链接已收到，正在整理...")
        else:
            msg.user.send("📥 已收到分享内容！")

    @itchat.msg_register(PICTURE)
    def picture_handler(msg):
        """处理图片"""
        log(f"📷 收到图片 from {msg['FromUserName']}")
        msg.user.send("📷 图片已收到，我会记住这张图！")

    # 登录
    print("\n📱 正在登录微信...")
    log("开始微信登录流程")

    # hotReload=True 保存登录状态，无需每次扫码
    itchat.auto_login(hotReload=True, enableCmdQR=2)

    state = load_state()
    state["logged_in"] = True
    save_state(state)

    # 获取登录用户信息
    myself = itchat.get_friends(update=True)
    if myself:
        log(f"✅ 登录成功: {myself[0].get('NickName', '未知')}")

    print("\n" + "=" * 50)
    print(f"✅ 机器人已启动！")
    print("=" * 50)
    print("📌 使用方式：")
    print("   1. 在微信中打开「文件传输助手」（就是发消息给自己的那个）")
    print("   2. 发送内容，机器人自动处理：")
    print("      - 豆瓣链接 → 自动添加「想看/想读」")
    print("      - 包含'待办/TODO' → 存入IMA待办")
    print("      - 包含'感想/想法' → 存入IMA笔记")
    print("      - 文章链接 → 存入LLM Wiki")
    print("      - 其他内容 → 存入IMA收集箱")
    print("   3. 按 Ctrl+C 退出")
    print("=" * 50)

    itchat.run(debug=False)


# ============ 命令行 ============
def main():
    import argparse

    parser = argparse.ArgumentParser(description="微信个人信息收集机器人")
    subparsers = parser.add_subparsers(dest="cmd")

    subparsers.add_parser("start", help="启动机器人")
    subparsers.add_parser("test", help="测试 OpenClaw 连接")
    subparsers.add_parser("setup", help="首次设置")

    args = parser.parse_args()

    if args.cmd == "test":
        check_openclaw()
        return

    if args.cmd == "setup":
        print("🔧 首次设置")
        print("1. 确保 OpenClaw Gateway 已启动")
        print("2. 确保豆瓣已登录: python3 douban_bot.py login")
        print("3. 启动机器人: python3 wechat_bot.py start")
        return

    if args.cmd == "start" or args.cmd is None:
        start_bot()


if __name__ == "__main__":
    main()
