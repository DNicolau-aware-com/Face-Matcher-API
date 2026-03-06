# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def test_retry_queue():
    # POST {{BASE_URL}}/facematch/admin/queue/retry
    url = f'{BASE_URL}/facematch/admin/queue/retry'

    r = requests.post(url, headers=HEADERS)

    print(f'[QUEUE RETRY] URL      : {url}')
    print(f'[QUEUE RETRY] Status   : {r.status_code}')
    print(f'[QUEUE RETRY] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[QUEUE RETRY] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_retry_queue()
