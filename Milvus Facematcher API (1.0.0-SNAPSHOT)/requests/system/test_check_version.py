# -*- coding: utf-8 -*-
import requests  # import before sys.path modification to avoid shadowing by local requests/ folder
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL

def test_version():
    # GET {{BASE_URL}}/facematch/version
    url = f'{BASE_URL}/facematch/version'
    r = requests.get(url)
    print(f'[VERSION] URL          : {url}')
    print(f'[VERSION] Status       : {r.status_code}')
    print(f'[VERSION] Content-Type : {r.headers.get("Content-Type", "not set")}')
    print(f'[VERSION] Response     : {r.text}')
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_version()