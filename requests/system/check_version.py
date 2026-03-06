# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config import BASE_URL

def test_version():
    # GET {{BASE_URL}}/facematch/version
    url = f"{BASE_URL}/facematch/version"
    r = requests.get(url)
    print(f"[VERSION] URL          : {url}")
    print(f"[VERSION] Status       : {r.status_code}")
    print(f"[VERSION] Content-Type : {r.headers.get('Content-Type', 'not set')}")
    print(f"[VERSION] Response     : {r.text}")
    return r

def test_health():
    # GET {{BASE_URL}}/facematch/health
    url = f"{BASE_URL}/facematch/health"
    r = requests.get(url)
    print(f"[HEALTH] URL          : {url}")
    print(f"[HEALTH] Status       : {r.status_code}")
    print(f"[HEALTH] Content-Type : {r.headers.get('Content-Type', 'not set')}")
    print(f"[HEALTH] Response     : {r.text}")
    return r

if __name__ == "__main__":
    test_version()
    test_health()