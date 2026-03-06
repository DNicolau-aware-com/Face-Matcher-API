# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def test_list_jobs():
    # GET {{BASE_URL}}/facematch/admin/jobs
    url = f'{BASE_URL}/facematch/admin/jobs'

    r = requests.get(url, headers=HEADERS)

    print(f'[LIST JOBS] URL      : {url}')
    print(f'[LIST JOBS] Status   : {r.status_code}')
    print(f'[LIST JOBS] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[LIST JOBS] Response : {r.text}')


    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_list_jobs()
