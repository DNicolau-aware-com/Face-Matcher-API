# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

GALLERY_NAME  = 'duplicate_gallery_test'   # fallback for standalone run
IMAGE_KEY     = 'two_spoof'   # maps to IMAGE_TWO_SPOOF in .env

def test_enroll_twospoof_into_a_gallery(session_gallery, random_uuid):
    # PRE-REQUEST: session_gallery is the shared gallery.
    # A unique identifier is generated per run so this never conflicts.
    gallery = session_gallery
    ident   = f'twospoof_{random_uuid[:8]}'

    # POST {{BASE_URL}}/facematch/galleries/{galleryName}/enrollments/{identifier}
    url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}'

    image_base64 = IMAGES.get(IMAGE_KEY)
    if not image_base64:
        print(f'[ENROLL TWOSPOOF] ERROR: IMAGE_TWO_SPOOF not found in config. Check your .env file.')
        pytest.fail(f'[SKIP] IMAGE_TWO_SPOOF not found in config. Check your .env file.')

    payload = {'image': image_base64}

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[ENROLL TWOSPOOF] URL        : {url}')
    print(f'[ENROLL TWOSPOOF] Gallery    : {gallery}')
    print(f'[ENROLL TWOSPOOF] Identifier : {ident}')
    print(f'[ENROLL TWOSPOOF] Status     : {r.status_code}')
    print(f'[ENROLL TWOSPOOF] Trace ID   : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[ENROLL TWOSPOOF] Success    : {body.get("success")}')
        print(f'[ENROLL TWOSPOOF] Identifier : {body.get("identifier")}')
        print(f'[ENROLL TWOSPOOF] Gallery    : {body.get("gallery")}')
    elif r.status_code == 400:
        body = r.json()
        print(f'[ENROLL TWOSPOOF] Error      : {body.get("error")}')
        print(f'[ENROLL TWOSPOOF] Message    : {body.get("message")}')
    else:
        print(f'[ENROLL TWOSPOOF] Response   : {r.text}')
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_enroll_twospoof_into_a_gallery()
