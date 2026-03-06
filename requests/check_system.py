import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import BASE_URL, HEADERS

def check_version():
    r = requests.get(f"{BASE_URL}/facematch/version")
    print(f"[VERSION] {r.status_code} -> {r.json()}")
    return r

def check_health():
    r = requests.get(f"{BASE_URL}/facematch/health")
    print(f"[HEALTH]  {r.status_code} -> {r.json()}")
    return r

if __name__ == "__main__":
    check_version()
    check_health()
