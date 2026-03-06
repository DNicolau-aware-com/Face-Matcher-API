# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL

def test_health():
    # GET {{BASE_URL}}/facematch/health
    url = f'{BASE_URL}/facematch/health'
    r = requests.get(url)
    print(f'[HEALTH] URL          : {url}')
    print(f'[HEALTH] Status       : {r.status_code}')
    print(f'[HEALTH] Content-Type : {r.headers.get("Content-Type", "not set")}')
    print(f'[HEALTH] Response     : {r.json()}')
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_health()