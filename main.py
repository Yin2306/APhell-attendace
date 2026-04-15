import os
import time
import yaml
import requests
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor

# --- 配置区 ---
# APU Attendix 通用 API KEY
COMMON_API_KEY = "da2-u4ksf3gspnhyjcokxzugo3mqr4"
GRAPHQL_URL = "https://attendix.apu.edu.my/graphql"

def take_attendance(name, token, otp):
    """直接向 GraphQL 发送签到请求"""
    payload = {
        "operationName": "updateAttendance",
        "query": "mutation updateAttendance($otp: String!) {\n  updateAttendance(otp: $otp) {\n    id\n    attendance\n    __typename\n  }\n}\n",
        "variables": {"otp": str(otp)},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-key": COMMON_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
    }
    try:
        res = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=10)
        return res.json()
    except Exception as e:
        return {"error": str(e)}

def process_single_account(acc, otp):
    """单个账号的登录及 Token 抓取流程"""
    print(f"🎬 Starting process for: {acc['name']}")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", 
                "--disable-setuid-sandbox", 
                "--disable-dev-shm-usage", 
                "--disable-gpu",
                "--blink-settings=imagesEnabled=false"
            ])
            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
                viewport={'width': 390, 'height': 844}
            )
            page = context.new_page()

            # FIX #3: Block fonts, CSS, media — not needed for login
            page.route("**/*.{woff,woff2,ttf,css,mp4,svg}", lambda route: route.abort())

            token_container = []
            def handle_request(request):
                auth = request.headers.get("authorization")
                if auth and "Bearer" in auth:
                    token_container.append(auth.replace("Bearer ", ""))

            page.on("request", handle_request)

            login_url = "https://login.microsoftonline.com/0fed03a3-402d-4633-a8cd-8b308822253e/oauth2/v2.0/authorize?client_id=e96b418c-3f97-4b0f-b124-1cb3b347a06e&response_type=code&redirect_uri=https%3A%2F%2Fauth.apu.edu.my%2Fauth_token&scope=Group.Read.All+GroupMember.Read.All+User.Read+offline_access+openid+profile&state=%7B%22origin%22%3A+%22https%3A%2F%2Fapspace.apu.edu.my%22%2C+%22endpoint%22%3A+%22%2Flogin%22%2C+%22app_id%22%3A+%22apspace%22%7D"
            
            print(f"📡 {acc['name']} 正在直达微软登录页...")

            # FIX #2: domcontentloaded instead of networkidle
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            
            full_email = f"{acc['username']}@mail.apu.edu.my"
            try:
                page.wait_for_selector('input[type="email"], [role="listitem"], text="Pick an account"', timeout=20000)
                
                if page.get_by_text(full_email).is_visible():
                    print(f"✅ {acc['name']} 发现已有账号，点击头像登录...")
                    page.get_by_text(full_email).click()
                else:
                    print(f"📝 {acc['name']} 手动输入 TP 号...")
                    page.fill('input[type="email"]', full_email)
                    page.click('input[type="submit"]')
            except:
                print(f"⚠️ {acc['name']} 尝试保底填表...")
                page.fill('input[type="email"]', full_email)
                page.click('input[type="submit"]')

            print(f"🔑 {acc['name']} 正在输入密码...")
            page.wait_for_selector('input[type="password"]', timeout=20000)
            page.fill('input[type="password"]', acc['password'])
            page.click('input[type="submit"]')
            
            try:
                page.wait_for_selector('#idSIButton9', timeout=5000)
                page.click('#idSIButton9')
            except: pass

            print(f"🛰️ {acc['name']} 已登录，正在监听 Token 响应...")
            
            for _ in range(150):
                if token_container:
                    token = token_container[-1]
                    result = take_attendance(acc['name'], token, otp)
                    print(f"🔥 {acc['name']} SUCCESS: {result}")
                    context.close()
                    browser.close()
                    return True
                time.sleep(0.1)
            
            print(f"⚠️ {acc['name']} 抓取 Token 超时")
            browser.close()
            return False
        except Exception as e:
            print(f"❌ {acc['name']} 运行出错: {str(e)}")
            return False

if __name__ == "__main__":
    import time
    start_time = time.time()
    
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    
    if not accounts_raw or not otp:
        print("Missing ACCOUNTS_YAML or OTP_CODE")
        exit(1)

    accounts = yaml.safe_load(accounts_raw)
    
    # FIX #4: Lowered from 7 to 3 workers to reduce CPU thrashing on GitHub Actions
    num_workers = 3
    
    print(f"🚀 极速模式启动 | 线程数: {num_workers} | 目标人数: {len(accounts)} | OTP: {otp}")

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        list(executor.map(lambda acc: process_single_account(acc, otp), accounts))

    end_time = time.time()
    print(f"🏁 全部签到任务完成！总耗时: {int(end_time - start_time)} 秒")
