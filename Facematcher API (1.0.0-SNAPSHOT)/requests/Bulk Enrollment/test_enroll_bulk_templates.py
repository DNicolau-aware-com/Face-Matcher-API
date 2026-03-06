# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

def test_enroll_bulk_templates(session_gallery):
    # PRE-REQUEST: session_gallery is used so the gallery always exists.
    gallery    = session_gallery
    part_image = IMAGES.get('part_face')
    jane_image = IMAGES.get('jane_face')

    # POST {{BASE_URL}}/facematch/admin/enroll/batch-images
    url = f'{BASE_URL}/facematch/admin/enroll/batch-images'

    items = [
        {'identifier': 'template_part', 'image': part_image},
        {'identifier': 'template_jane', 'image': jane_image},
    ]

    payload = {
        'items':       items,
        'gallery':     gallery,
        'storeImages': False,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[ENROLL BULK TEMPLATES] URL      : {url}')
    print(f'[ENROLL BULK TEMPLATES] Gallery  : {gallery}')
    print(f'[ENROLL BULK TEMPLATES] Items    : {len(items)}')
    print(f'[ENROLL BULK TEMPLATES] Status   : {r.status_code}')
    print(f'[ENROLL BULK TEMPLATES] Trace ID : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[ENROLL BULK TEMPLATES] Response : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_enroll_bulk_templates()
