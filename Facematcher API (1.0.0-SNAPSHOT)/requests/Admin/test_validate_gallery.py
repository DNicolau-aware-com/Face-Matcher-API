# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

def test_validate_gallery(session_gallery):
    # PRE-REQUEST: session_gallery is used so the gallery always exists.
    gallery = session_gallery

    # GET {{BASE_URL}}/facematch/admin/validate/{gallery}
    url = f'{BASE_URL}/facematch/admin/validate/{gallery}'

    r = requests.get(url, headers=HEADERS)

    print(f'[VALIDATE GALLERY] URL      : {url}')
    print(f'[VALIDATE GALLERY] Gallery  : {gallery}')
    print(f'[VALIDATE GALLERY] Status   : {r.status_code}')
    print(f'[VALIDATE GALLERY] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[VALIDATE GALLERY] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_validate_gallery()
