#!/usr/bin/env python3
"""
豆瓣自动化工具 - 添加想看/想读/想听
用法:
  python3 douban_bot.py add movie 1291561    # 添加电影想看
  python3 douban_bot.py add book 1234567     # 添加图书想读
  python3 douban_bot.py login                # 登录（首次需要）
  python3 douban_bot.py status              # 查看登录状态
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ============ 配置 ============
COOKIE_FILE = Path(__file__).parent / "douban_cookies.json"
CHROMEDRIVER_PATH = Path.home() / "bin" / "chromedriver"

DOUBAN_BASE = "https://www.douban.com"
DOUBAN_LOGIN_URL = "https://accounts.douban.com/passport/login"

# ============ Chrome 浏览器设置 ============
def get_chrome_driver(headless=False):
    """创建 Chrome 浏览器驱动"""
    options = Options()

    # macOS Chrome 路径
    options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    # 反爬虫配置
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")

    # 用户数据目录（保持登录状态）
    user_data_dir = Path.home() / ".douban-chrome-profile"
    user_data_dir.mkdir(exist_ok=True)
    options.add_argument(f"--user-data-dir={user_data_dir}")

    # 禁用自动化标识（更接近真实浏览器）
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(str(CHROMEDRIVER_PATH))
    driver = webdriver.Chrome(service=service, options=options)

    # 删除 webdriver 属性
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    return driver


# ============ 登录模块 ============
def check_login_status(driver):
    """检查是否已登录（通过Cookie判断）"""
    try:
        # 方法1：检查关键Cookie
        cookies = driver.get_cookies()
        cookie_names = [c['name'] for c in cookies]
        
        # 豆瓣登录后会设置这些Cookie
        login_cookies = ['dbcl2', 'ck', 'bid']
        has_login_cookie = any(c in cookie_names for c in login_cookies)
        
        if has_login_cookie:
            print(f"✅ 检测到登录Cookie: {[c for c in login_cookies if c in cookie_names]}")
            return True
        
        # 方法2：访问豆瓣首页，检查是否有用户名
        driver.get("https://www.douban.com")
        time.sleep(2)
        
        # 检查页面源码中是否有用户名（登录后页面会显示）
        page_source = driver.page_source.lower()
        if '登出' in page_source or 'logout' in page_source:
            print("✅ 检测到'登出'链接")
            return True
            
        # 检查是否有用户头像或用户名元素
        try:
            user_img = driver.find_element(By.CSS_SELECTOR, ".nav-user-account img, .top-nav-info img")
            if user_img:
                print("✅ 检测到用户头像")
                return True
        except:
            pass
            
        print(f"⚠️ 未检测到登录状态，当前Cookie: {cookie_names}")
        return False
    except Exception as e:
        print(f"⚠️ 检查登录状态时出错: {e}")
        return False


def login_interactive(driver):
    """交互式登录 - 需要用户扫描二维码"""
    print("\n" + "=" * 50)
    print("📱 豆瓣登录步骤")
    print("=" * 50)

    driver.get(DOUBAN_LOGIN_URL)
    time.sleep(3)

    print("✅ 请在浏览器窗口中：")
    print("   1. 选择「扫码登录」（推荐）或账号密码登录")
    print("   2. 用豆瓣 App 扫描二维码")
    print("   3. 确认登录")
    print("\n⏳ 等待登录中...", flush=True)

    # 等待登录成功（检查 URL 变化或用户信息出现）
    wait = WebDriverWait(driver, 120)  # 最多等2分钟
    try:
        wait.until(lambda d: "accounts.douban.com" not in d.current_url)
        time.sleep(2)

        if check_login_status(driver):
            save_cookies(driver)
            print("✅ 登录成功！Cookie 已保存")
            print("⏳ 3秒后自动关闭浏览器...")
            time.sleep(3)
            return True
        else:
            print("❌ 登录似乎未成功，请重试")
            print("⏳ 5秒后自动关闭浏览器...")
            time.sleep(5)
            return False
    except TimeoutException:
        print("❌ 登录超时，请重试")
        print("⏳ 3秒后自动关闭浏览器...")
        time.sleep(3)
        return False


def save_cookies(driver):
    """保存登录 Cookie"""
    cookies = driver.get_cookies()
    with open(COOKIE_FILE, "w") as f:
        json.dump(cookies, f, ensure_ascii=False)
    print(f"✅ Cookie 已保存到: {COOKIE_FILE}")


def load_cookies(driver):
    """加载已保存的 Cookie"""
    if not COOKIE_FILE.exists():
        return False

    driver.get(DOUBAN_BASE)
    time.sleep(1)

    with open(COOKIE_FILE, "r") as f:
        cookies = json.load(f)

    for cookie in cookies:
        # 清理可能导致问题的字段
        cookie.pop("sameSite", None)
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass

    driver.refresh()
    time.sleep(2)
    return check_login_status(driver)


# ============ 豆瓣操作 ============
TYPE_MAPPING = {
    "movie": ("电影", "wish"),
    "book": ("图书", "wish"),
    "music": ("音乐", "wish"),
    "tv": ("剧集", "wish"),
}


def add_to_wishlist(driver, subject_id, media_type="movie"):
    """添加想看/想读/想听

    Args:
        subject_id: 豆瓣的 subject ID（如电影 1291561）
        media_type: movie / book / music / tv
    """
    type_name, action = TYPE_MAPPING.get(media_type, ("电影", "wish"))

    url = f"https://movie.douban.com/subject/{subject_id}/"
    if media_type == "book":
        url = f"https://book.douban.com/subject/{subject_id}/"
    elif media_type == "music":
        url = f"https://music.douban.com/subject/{subject_id}/"
    elif media_type == "tv":
        url = f"https://movie.douban.com/subject/{subject_id}/"

    print(f"\n🎬 正在访问: {url}")
    driver.get(url)
    time.sleep(3)

    # 获取标题
    try:
        title_elem = driver.find_element(By.CSS_SELECTOR, "h1 span[property='v:itemreviewed']")
        title = title_elem.text
    except NoSuchElementException:
        try:
            title = driver.find_element(By.TAG_NAME, "h1").text
        except:
            title = f"ID: {subject_id}"
    print(f"📌 内容: {title}")

    # 点击"想看"按钮
    # 豆瓣有多种按钮样式，尝试多种选择器
    selectors = [
        f"a[href*='{subject_id}'][class*='wish'], a[data-type='{media_type}'][class*='wish']",
        f".jq_add_to_wishlist[href*='{subject_id}']",
        f"a.wish[href*='{subject_id}']",
        "//a[contains(text(), '想看')]",
        "//a[contains(text(), '想读')]",
        "//a[contains(text(), '想听')]",
        "//span[contains(text(), '想看')]/..",
        "//button[contains(text(), '想看')]",
        "//a[contains(@class, 'btn-wish')]",
    ]

    button_found = False
    for selector in selectors:
        try:
            if selector.startswith("//"):
                buttons = driver.find_elements(By.XPATH, selector)
            else:
                buttons = driver.find_elements(By.CSS_SELECTOR, selector)

            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    btn_text = btn.text.strip()
                    print(f"✅ 找到按钮: {btn_text}")
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)
                    button_found = True
                    break
            if button_found:
                break
        except NoSuchElementException:
            continue
        except Exception as e:
            print(f"   选择器 {selector} 出错: {e}")

    if not button_found:
        print("❌ 未找到「想看/想读」按钮，请手动点击")
        return False

    # 【关键】点击"想看/想读"后会弹出确认框，需要再点"保存"
    time.sleep(3)
    save_selectors = [
        "//input[@value='保存']",
        "//button[contains(text(), '保存')]",
        "//a[contains(text(), '保存')]",
    ]
    for sel in save_selectors:
        try:
            saves = driver.find_elements(By.XPATH, sel)
            for s in saves:
                if s.is_displayed():
                    print(f"✅ 找到保存按钮，点击中...")
                    driver.execute_script("arguments[0].click();", s)
                    time.sleep(2)
                    break
        except:
            pass

    # 验证是否添加成功
    try:
        # 刷新页面检查状态
        driver.refresh()
        time.sleep(2)

        # 检查是否有"已加入"标记
        joined_selectors = [
            "//span[contains(text(), '已加入')]",
            "//a[contains(text(), '已加入')]",
            "//span[contains(text(), '已标记')]",
        ]
        for sel in joined_selectors:
            try:
                elems = driver.find_elements(By.XPATH, sel)
                for e in elems:
                    if e.is_displayed():
                        print(f"✅ 添加成功: {e.text}")
                        return True
            except:
                pass
        print("✅ 按钮已点击（请刷新页面确认）")
        return True
    except Exception as e:
        print(f"⚠️ 验证失败: {e}")
        return True  # 按钮已点，视为成功


# ============ 主入口 ============
def main():
    parser = argparse.ArgumentParser(description="豆瓣自动化工具")
    subparsers = parser.add_subparsers(dest="cmd", help="子命令")

    # login
    subparsers.add_parser("login", help="登录豆瓣（需要扫描二维码）")

    # status
    subparsers.add_parser("status", help="查看登录状态")

    # add
    add_parser = subparsers.add_parser("add", help="添加到想看/想读")
    add_parser.add_argument("type", choices=["movie", "book", "music", "tv"], help="媒体类型")
    add_parser.add_argument("subject_id", help="豆瓣 Subject ID（数字，如 1291561）")

    # interactive
    subparsers.add_parser("interactive", help="交互模式 - 添加想看")

    args = parser.parse_args()

    if args.cmd == "login":
        driver = get_chrome_driver(headless=False)
        try:
            if check_login_status(driver):
                print("✅ 已经登录，无需重复登录")
                time.sleep(2)
            else:
                login_interactive(driver)
        finally:
            driver.quit()
        return

    if args.cmd == "status":
        driver = get_chrome_driver(headless=False)
        try:
            logged_in = load_cookies(driver) or check_login_status(driver)
            if logged_in:
                print("✅ 已登录豆瓣")
            else:
                print("❌ 未登录，请先运行 login 命令")
        finally:
            driver.quit()
        return

    if args.cmd == "add":
        driver = get_chrome_driver(headless=False)
        try:
            # 尝试加载 Cookie
            if not (load_cookies(driver) or check_login_status(driver)):
                print("⚠️ 未登录，开始登录流程...")
                if not login_interactive(driver):
                    print("❌ 登录失败，退出")
                    return

            add_to_wishlist(driver, args.subject_id, args.type)
        finally:
            input("\n按回车键关闭浏览器...")
            driver.quit()
        return

    if args.cmd == "interactive":
        driver = get_chrome_driver(headless=False)
        try:
            if not (load_cookies(driver) or check_login_status(driver)):
                print("⚠️ 未登录，开始登录流程...")
                if not login_interactive(driver):
                    print("❌ 登录失败，退出")
                    return

            print("\n📍 交互模式")
            print("输入豆瓣链接或 subject ID（输入 q 退出）")
            print("-" * 40)

            while True:
                user_input = input("\n🎯 豆瓣链接或 ID: ").strip()
                if user_input.lower() in ["q", "quit", "exit"]:
                    break

                # 解析输入
                subject_id = None
                media_type = "movie"

                if "douban.com/subject/" in user_input:
                    # 从链接提取 ID
                    import re
                    match = re.search(r"subject/(\d+)", user_input)
                    if match:
                        subject_id = match.group(1)
                    if "/book/" in user_input:
                        media_type = "book"
                    elif "/music/" in user_input:
                        media_type = "music"
                    elif "/tv/" in user_input:
                        media_type = "tv"
                elif user_input.isdigit():
                    subject_id = user_input
                else:
                    print("⚠️ 请输入豆瓣链接或纯数字 ID")
                    continue

                if subject_id:
                    add_to_wishlist(driver, subject_id, media_type)
        finally:
            driver.quit()
        return

    # 无子命令时默认进入交互模式
    parser.print_help()


if __name__ == "__main__":
    main()
