import os
import yaml
import requests
from concurrent.futures import ThreadPoolExecutor

def get_token_via_api(username, password):
    """直接模拟 Apspace 登录接口，不通过浏览器"""
    session = requests.Session()
    login_url = "https://apspace.apu.edu.my/api/login" # 模拟登录 API
    payload = {
        "username": f"{username}@mail.apu.edu.my",
        "password": password
    }
    try:
        # 直接发送 POST 请求获取 Token
        response = session.post(login_url, json=payload, timeout=10)
        data = response.json()
        # 注意：这里需要根据 APU 实际 API 的返回字段来提取 token
        # 通常是 data['token'] 或 data['data']['token']
        return data.get('token') or data.get('data', {}).get('token')
    except:
        return None

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

def process_account(acc, otp):
    print(f"⚡ Processing {acc['name']}...")
    # 核心：不再调用 Playwright，直接发请求
    token = get_token_via_api(acc['username'], acc['password'])
    if token:
        res = take_attendance(acc['name'], token, acc['api_key'], otp)
        print(f"✅ {acc['name']} Done: {res}")
    else:
        print(f"❌ {acc['name']} Login Failed")

if __name__ == "__main__":
    accounts_raw = os.getenv("ACCOUNTS_YAML")
    otp = os.getenv("OTP_CODE")
    if not accounts_raw or not otp: exit(1)

    accounts = yaml.safe_load(accounts_raw)
    
    # 11个人一起跑，API 模式下负载极低
    with ThreadPoolExecutor(max_workers=len(accounts)) as executor:
        executor.map(lambda acc: process_account(acc, otp), accounts)
