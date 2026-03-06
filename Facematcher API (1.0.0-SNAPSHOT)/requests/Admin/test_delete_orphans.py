# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def test_delete_orphans(session_gallery):
    # PRE-REQUEST: session_gallery is used so the gallery always exists.
    gallery = session_gallery

    # DELETE {{BASE_URL}}/facematch/admin/orphans/{gallery}
    url = f'{BASE_URL}/facematch/admin/orphans/{gallery}'

    r = requests.delete(url, headers=HEADERS)

    print(f'[DELETE ORPHANS] URL      : {url}')
    print(f'[DELETE ORPHANS] Gallery  : {gallery}')
    print(f'[DELETE ORPHANS] Status   : {r.status_code}')
    print(f'[DELETE ORPHANS] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[DELETE ORPHANS] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_delete_orphans()
