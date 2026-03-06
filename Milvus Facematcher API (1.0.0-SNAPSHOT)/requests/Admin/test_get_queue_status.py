# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def test_get_queue_status():
    # GET {{BASE_URL}}/facematch/admin/queue
    url = f'{BASE_URL}/facematch/admin/queue'

    r = requests.get(url, headers=HEADERS)

    print(f'[QUEUE STATUS] URL      : {url}')
    print(f'[QUEUE STATUS] Status   : {r.status_code}')
    print(f'[QUEUE STATUS] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[QUEUE STATUS] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_get_queue_status()
