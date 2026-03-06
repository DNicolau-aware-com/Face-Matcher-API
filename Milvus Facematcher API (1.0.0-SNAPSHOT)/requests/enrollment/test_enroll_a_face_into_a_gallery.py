# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

GALLERY_NAME  = 'duplicate_gallery_test'   # fallback for standalone run
ENROLLMENT_ID = 'jane_face'
IMAGE_KEY     = 'jane_face'    # matches key in IMAGES dict in config.py

def test_enroll_a_face_into_a_gallery(shared_state, session_gallery, unique_identifier):
    # PRE-REQUEST: session_gallery is the shared gallery for this run
    gallery = session_gallery
    ident   = unique_identifier or ENROLLMENT_ID

    # POST {{BASE_URL}}/facematch/galleries/{galleryName}/enrollments/{identifier}
    url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}'

    image_base64 = IMAGES.get(IMAGE_KEY)
    if not image_base64:
        print(f'[ENROLL] ERROR: Image key "{IMAGE_KEY}" not found in config. Check your .env file.')
        pytest.fail(f'[SKIP] Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    payload = {'image': image_base64}

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[ENROLL] URL           : {url}')
    print(f'[ENROLL] Gallery       : {gallery}')
    print(f'[ENROLL] Identifier    : {ident}')
    print(f'[ENROLL] Status        : {r.status_code}')
    print(f'[ENROLL] Trace ID      : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[ENROLL] Success       : {body.get("success")}')
        print(f'[ENROLL] Identifier    : {body.get("identifier")}')
        print(f'[ENROLL] Gallery       : {body.get("gallery")}')

        # TEST SCRIPT: capture enrollment identifier for use by delete-enrollment tests
        shared_state['enrollment_id'] = body.get('identifier', ident)
        print(f'[ENROLL] >> shared_state["enrollment_id"] = {shared_state["enrollment_id"]}')
    else:
        print(f'[ENROLL] Response      : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
