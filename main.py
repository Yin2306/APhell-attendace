import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

def take_attendance(name, token, api_key, otp):
    url = "https://attendix.apu.edu.my/graphql"
    payload = {
        "operationName": "updateAttendance",
        "query": "mutation updateAttendance($otp: String!) {\n  updateAttendance(otp: $otp) {\n    id\n    attendance\n    __typename\n  }\n}\n",
        "variables": {"otp": otp},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=5)
        return res.json()
    except:
        return None

def process_single_account(acc, otp):
    print(f"🚀 {acc['name']} 正在启动...")
    with sync_playwright() as p:
        try:
            # 使用手机模式模拟，通常比电脑版网页加载快且稳定
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            )
            page = context.new_page()
            
            token_container = []
            def handle_request(request):
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    token_container.append(auth.replace("Bearer ", ""))

            page.on("request", handle_request)

            # 1. 访问主页
            page.goto("https://apspace.apu.edu.my/login", timeout=60000)
            
            # 2. 点击右上角的 Log In 按钮 (对应你发的新图)
            try:
                page.wait_for_selector('text="Log In"', timeout=10000)
                page.click('text="Log In"')
            except:
                # 如果没找到按钮，可能是已经自动跳转了，继续下一步
                pass

            # 3. 等待进入微软登录页
            page.wait_for_url("**/login.microsoftonline.com/**", timeout=20000)

            # 4. 处理“选择账号”或“输入账号” (对应你发的第一张图)
            full_email = f"{acc['username']}@mail.apu.edu.my"
            try:
                # 检查是否有“Pick an account”列表
                account_selector = f"text='{full_email}'"
                if page.is_visible(account_selector, timeout=5000):
                    print(f"🔎 发现已有账号 {acc['name']}，直接点击...")
                    page.click(account_selector)
                else:
                    # 如果没有列表，就正常输入 TP 号
                    page.wait_for_selector('input[type="email"]', timeout=10000)
                    page.fill('input[type="email"]', full_email)
                    page.click('input[type="submit"]')
            except:
                # 保底操作：尝试强制输入
                page.fill('input[type="email"]', full_email)
                page.click('input[type="submit"]')

            # 5. 输入密码
            page.wait_for_selector('input[type="password"]', timeout=15000)
            page.fill('input[type="password"]', acc['password'])
            page.click('input[type="submit"]')
            
            # 处理“保持登录状态”询问 (如果有的话)
            try:
                page.wait_for_selector('#idSIButton9', timeout=5000)
                page.click('#idSIButton9')
            except: pass

            # 6. 抢跑：只要抓到 Token 立刻执行签到
            for _ in range(40):
                if token_container:
                    token = token_container[0]
                    result = take_attendance(acc['name'], token, acc['api_key'], otp)
                    print(f"✅ {acc['name']} 签到结果: {result}")
                    browser.close()
                    return True
                time.sleep(0.5)
            
            print(f"❌ {acc['name']} 未能在超时前抓取到 Token")
            browser.close()
            return False
        except Exception as e:
            print(f"❌ {acc['name']} 运行出错: {str(e)}")
            return False

if __name__ == "__main__":
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    if not accounts_raw or not otp: exit(1)
    accounts = yaml.safe_load(accounts_raw)
    
    # 11人同时起步
    with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
        executor.map(lambda acc: process_single_account(acc, otp), accounts)
