# -*- coding: utf-8 -*-
import requests
import sys, os
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


def test_health_response_fields():
    # All documented fields must be present and the algorithm/vectorDim pair must be valid.
    url  = f'{BASE_URL}/facematch/health'
    r    = requests.get(url)
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    body = r.json()

    for field in ('status', 'algorithm', 'vectorDim', 'sdk', 'milvus', 'database'):
        assert field in body, f'"{field}" key missing from health response: {body}'

    print(f'[HEALTH FIELDS] status    : {body.get("status")}')
    print(f'[HEALTH FIELDS] algorithm : {body.get("algorithm")}')
    print(f'[HEALTH FIELDS] vectorDim : {body.get("vectorDim")}')
    print(f'[HEALTH FIELDS] sdk       : {body.get("sdk")}')
    print(f'[HEALTH FIELDS] milvus    : {body.get("milvus")}')
    print(f'[HEALTH FIELDS] database  : {body.get("database")}')

    valid_pairs = {'f500': 460, 'f200': 768}
    algo = body.get('algorithm')
    dim  = body.get('vectorDim')
    if algo in valid_pairs:
        assert dim == valid_pairs[algo], \
            f'Expected vectorDim={valid_pairs[algo]} for algorithm={algo}, got {dim}'


if __name__ == '__main__':
    test_health()
    test_health_response_fields()