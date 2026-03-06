# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def test_list_galleries():
    # GET {{BASE_URL}}/facematch/galleries
    url = f'{BASE_URL}/facematch/galleries'
    params = {
        'page': 0,
        'size': 20,
        'sort': 'createdAt,desc',
    }

    r = requests.get(url, headers=HEADERS, params=params)

    print(f'[LIST GALLERIES] URL         : {r.url}')
    print(f'[LIST GALLERIES] Params      : {params}')
    print(f'[LIST GALLERIES] Status      : {r.status_code}')
    print(f'[LIST GALLERIES] Trace ID    : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        content     = body.get('content', [])
        total_items = body.get('totalItems')
        prev_page   = body.get('prev')
        next_page   = body.get('next')

        print(f'[LIST GALLERIES] Total Items : {total_items}')
        print(f'[LIST GALLERIES] Prev Page   : {prev_page}')
        print(f'[LIST GALLERIES] Next Page   : {next_page}')
        print(f'[LIST GALLERIES] Galleries   : {len(content)} returned on this page')

        for i, gallery in enumerate(content, start=1):
            print(f'  [{i}] name={gallery.get("name")} | '
                  f'createdAt={gallery.get("createdAt")} | '
                  f'faceCount={gallery.get("faceCount")}')
    else:
        print(f'[LIST GALLERIES] Response    : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_list_galleries()
