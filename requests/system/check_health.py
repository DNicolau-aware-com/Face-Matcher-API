import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config import BASE_URL

def check_health():
    url = f"{BASE_URL}/facematch/health"
    r = requests.get(url)
    print(f"[HEALTH] URL     : {url}")
    print(f"[HEALTH] Status  : {r.status_code}")
    print(f"[HEALTH] Response: {r.json()}")
    return r

if __name__ == "__main__":
    check_health()
