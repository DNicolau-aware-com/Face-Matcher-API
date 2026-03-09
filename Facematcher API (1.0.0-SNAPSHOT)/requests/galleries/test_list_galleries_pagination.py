# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def test_list_galleries_pagination():
    # GET {{BASE_URL}}/facematch/galleries?page=0&size=1
    # Verifies pagination fields: content, totalItems, prev, next
    url = f'{BASE_URL}/facematch/galleries'
    params = {
        'page': 0,
        'size': 1,
        'sort': 'createdAt,desc',
    }

    r = requests.get(url, headers=HEADERS, params=params)

    print(f'[LIST GALLERIES PAGINATION] URL         : {r.url}')
    print(f'[LIST GALLERIES PAGINATION] Params      : {params}')
    print(f'[LIST GALLERIES PAGINATION] Status      : {r.status_code}')
    print(f'[LIST GALLERIES PAGINATION] Trace ID    : {r.headers.get("x-aware-trace-id", "not returned")}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body        = r.json()
    content     = body.get('content', [])
    total_items = body.get('totalItems')
    prev_page   = body.get('prev')
    next_page   = body.get('next')

    print(f'[LIST GALLERIES PAGINATION] Total Items : {total_items}')
    print(f'[LIST GALLERIES PAGINATION] Returned    : {len(content)} gallery on this page')
    print(f'[LIST GALLERIES PAGINATION] Prev Page   : {prev_page}')
    print(f'[LIST GALLERIES PAGINATION] Next Page   : {next_page}')

    if content:
        g = content[0]
        print(f'[LIST GALLERIES PAGINATION] First Entry : name={g.get("name")} | '
              f'createdAt={g.get("createdAt")} | faceCount={g.get("faceCount")}')

    # Page 0 with size=1: content must have at most 1 item
    assert len(content) <= 1, f'Expected at most 1 item with size=1, got {len(content)}'

    # prev must be null on the first page
    assert prev_page is None, f'Expected prev=null on page 0, got: {prev_page}'

    # If there is more than 1 gallery, next must be present
    if total_items is not None and total_items > 1:
        assert next_page is not None, f'Expected a next link when totalItems={total_items} > 1, got null'
        print(f'[LIST GALLERIES PAGINATION] next link present — pagination working correctly')

if __name__ == '__main__':
    test_list_galleries_pagination()
