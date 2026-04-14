import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

# 1. 签到函数
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
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

# 2. 单个账号的完整流程（登录 + 签到）
def process_single_account(acc, otp):
    # ... 前面的代码保持不变 ...
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            
            # 使用列表来存储，方便在回调中修改
            token_container = []

            def handle_request(request):
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    t = auth.replace("Bearer ", "")
                    token_container.append(t)

            page.on("request", handle_request)
            
            # 这里的 goto 只要到达登录页即可
            page.goto("https://apspace.apu.edu.my/login")
            
            page.fill('input[type="email"]', f"{acc['username']}@mail.apu.edu.my")
            page.click('input[type="submit"]')
            page.wait_for_selector('input[type="password"]')
            page.fill('input[type="password"]', acc['password'])
            page.click('input[type="submit"]')
            
            # 核心优化：只要监听到 Token 存入列表，立刻执行下一步，不再等待页面刷新
            for _ in range(40): # 最多等 20 秒
                if token_container:
                    token = token_container[0]
                    # 抓到 Token 后直接在浏览器后台发送 API，连浏览器都不用关，速度最快
                    result = take_attendance(acc['name'], token, acc['api_key'], otp)
                    print(f"⚡ {acc['name']} FAST-TICK: {result}")
                    browser.close()
                    return True
                time.sleep(0.5)
            
            browser.close()
            return False
        except:
            return False

if __name__ == "__main__":
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    
    if not accounts_raw or not otp:
        exit(1)

    accounts = yaml.safe_load(accounts_raw)
    
    # --- 核心提速：使用多线程同时跑 11 个账号 ---
    print(f"⚡ Parallel processing started for {len(accounts)} accounts...")
    with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
        executor.map(lambda acc: process_single_account(acc, otp), accounts)
    
    print("All done!")
