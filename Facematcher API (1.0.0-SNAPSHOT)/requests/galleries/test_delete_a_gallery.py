# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, ensure_gallery

GALLERY_NAME = 'snow'  # fallback for standalone run

def test_delete_a_gallery(shared_state):
    # PRE-REQUEST: use the gallery created by test_create_a_gallery in this file.
    # 'gallery_create_test' key is set by test_create_a_gallery and is isolated
    # from session_gallery so it doesn't interfere with enrollment/search tests.
    gallery = shared_state.get('gallery_create_test', GALLERY_NAME)

    # Ensure gallery exists before attempting to delete (create if not found)
    ensure_gallery(gallery)

    # DELETE {{BASE_URL}}/facematch/galleries/{galleryName}
    url = f'{BASE_URL}/facematch/galleries/{gallery}'

    r = requests.delete(url, headers=HEADERS)

    print(f'[DELETE GALLERY] URL      : {url}')
    print(f'[DELETE GALLERY] Gallery  : {gallery}')
    print(f'[DELETE GALLERY] Status   : {r.status_code}')
    print(f'[DELETE GALLERY] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 204:
        print('[DELETE GALLERY] Response : Gallery deleted (no body)')
        shared_state.pop('gallery_create_test', None)
    elif r.status_code == 404:
        print('[DELETE GALLERY] Response : Gallery not found')
    else:
        print(f'[DELETE GALLERY] Response : {r.text}')

    assert r.status_code == 204, f'Expected 204, got {r.status_code}: {r.text}'

def test_create_and_delete_gallery(random_uuid):
    gallery_name = f'temp_{random_uuid[:8]}'

    # Step 1 — POST {{BASE_URL}}/facematch/galleries
    create_url = f'{BASE_URL}/facematch/galleries'
    r_create   = requests.post(create_url, headers=HEADERS, json={'name': gallery_name})

    print(f'[CREATE] URL      : {create_url}')
    print(f'[CREATE] Gallery  : {gallery_name}')
    print(f'[CREATE] Status   : {r_create.status_code}')
    print(f'[CREATE] Trace ID : {r_create.headers.get("x-aware-trace-id", "not returned")}')

    if r_create.status_code == 200:
        body = r_create.json()
        print(f'[CREATE] Name     : {body.get("name")}')
        print(f'[CREATE] Created  : {body.get("createdAt")}')
    else:
        print(f'[CREATE] Response : {r_create.text}')

    assert r_create.status_code == 200, f'Create failed — Expected 200, got {r_create.status_code}: {r_create.text}'

    # Step 2 — DELETE {{BASE_URL}}/facematch/galleries/{galleryName}
    delete_url = f'{BASE_URL}/facematch/galleries/{gallery_name}'
    r_delete   = requests.delete(delete_url, headers=HEADERS)

    print(f'[DELETE] URL      : {delete_url}')
    print(f'[DELETE] Gallery  : {gallery_name}')
    print(f'[DELETE] Status   : {r_delete.status_code}')
    print(f'[DELETE] Trace ID : {r_delete.headers.get("x-aware-trace-id", "not returned")}')

    if r_delete.status_code == 204:
        print('[DELETE] Response : Gallery deleted (no body)')
    else:
        print(f'[DELETE] Response : {r_delete.text}')

    assert r_delete.status_code == 204, f'Delete failed — Expected 204, got {r_delete.status_code}: {r_delete.text}'

if __name__ == '__main__':
    test_delete_a_gallery()
    test_create_and_delete_gallery()
