import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright

# 1. 签到函数：负责发送具体的签到请求
def take_attendance(name, token, api_key, otp):
    url = "https://attendix.apu.edu.my/graphql"
    payload = {
        "operationName": "updateAttendance",
        "query": "mutation updateAttendance($otp: String!) {\n  updateAttendance(otp: $otp) {\n    id\n    attendance\n    classcode\n    date\n    startTime\n    endTime\n    classType\n    __typename\n  }\n}\n",
        "variables": {"otp": otp},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# 2. 登录函数：负责模拟浏览器拿到最新的 Bearer Token
def login_and_get_token(username, password):
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context()
            page = context.new_page()
            token = None

            # 监听所有请求，抓取带有 Bearer 的 Authorization Header
            def handle_request(request):
                nonlocal token
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    token = auth.replace("Bearer ", "")

            page.on("request", handle_request)
            page.goto("https://apspace.apu.edu.my/login", timeout=60000)
            
            # 填入账号密码
            page.fill('input[type="email"]', f"{username}@mail.apu.edu.my")
            page.click('input[type="submit"]')
            page.wait_for_selector('input[type="password"]', timeout=20000)
            page.fill('input[type="password"]', password)
            page.click('input[type="submit"]')
            
            # 点击“保持登录”确认
            try:
                page.wait_for_selector('#idSIButton9', timeout=10000)
                page.click('#idSIButton9')
            except: pass

            # 等待进入系统
            page.wait_for_url("**/dashboard**", timeout=60000)
            time.sleep(5) 
            browser.close()
            return token
        except Exception as e:
            print(f"❌ 登录失败 ({username}): {str(e)}")
            return None

# 3. 主程序：批量执行
if __name__ == "__main__":
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    
    if not accounts_raw or not otp:
        print("❌ 缺少配置或 OTP 码")
        exit(1)

    accounts = yaml.safe_load(accounts_raw)
    print(f"开始为 {len(accounts)} 个账号处理签到，OTP: {otp}")

    for acc in accounts:
        print(f"\n>>> 正在处理: {acc['name']}")
        token = login_and_get_token(acc['username'], acc['password'])
        
        if token:
            print(f"✅ 成功获取 Token，正在签到...")
            res = take_attendance(acc['name'], token, acc['api_key'], otp)
            print(f"结果: {res}")
        else:
            print(f"❌ 无法获取 Token，跳过该用户。")
