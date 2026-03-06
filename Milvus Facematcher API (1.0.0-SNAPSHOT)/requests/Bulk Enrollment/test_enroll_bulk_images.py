# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

STORE_IMAGES = True

def test_enroll_bulk_images(session_gallery):
    # PRE-REQUEST: session_gallery is used so the gallery always exists.
    gallery = session_gallery

    # POST {{BASE_URL}}/facematch/admin/enroll/batch-images
    url = f'{BASE_URL}/facematch/admin/enroll/batch-images'

    dan_image  = IMAGES.get('dan_face')
    john_image = IMAGES.get('john_face')

    if not dan_image:
        print('[ENROLL BULK IMAGES] ERROR: IMAGE_DAN_FACE not found in config. Check your .env file.')
        pytest.fail("Image not found in config. Check your .env file.")
    if not john_image:
        print('[ENROLL BULK IMAGES] ERROR: IMAGE_JOHN_FACE not found in config. Check your .env file.')
        pytest.fail("Image not found in config. Check your .env file.")

    payload = {
        'items': [
            {'identifier': 'dan_face',  'image': dan_image},
            {'identifier': 'john_face', 'image': john_image},
        ],
        'gallery':     gallery,
        'storeImages': STORE_IMAGES,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[ENROLL BULK IMAGES] URL         : {url}')
    print(f'[ENROLL BULK IMAGES] Gallery     : {gallery}')
    print(f'[ENROLL BULK IMAGES] Items       : {len(payload["items"])}')
    print(f'[ENROLL BULK IMAGES] storeImages : {STORE_IMAGES}')
    print(f'[ENROLL BULK IMAGES] Status      : {r.status_code}')
    print(f'[ENROLL BULK IMAGES] Trace ID    : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[ENROLL BULK IMAGES] Response    : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_enroll_bulk_images()
