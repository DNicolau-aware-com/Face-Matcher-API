# -*- coding: utf-8 -*-
import requests
import pytest
import base64
import sys, os
from config import BASE_URL, HEADERS, IMAGES

IMAGE_KEY     = 'jane_face'
ENROLLMENT_ID = 'upload_enroll_test'

# Multipart uploads must not have a hard-coded Content-Type header —
# requests sets it automatically (including the multipart boundary).
UPLOAD_HEADERS = {k: v for k, v in HEADERS.items() if k.lower() != 'content-type'}


def test_upload_enroll(session_gallery):
    gallery      = session_gallery
    image_base64 = IMAGES.get(IMAGE_KEY)

    if not image_base64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    image_bytes = base64.b64decode(image_base64)

    # POST /facematch/upload/galleries/{gallery}/enrollments/{id}
    url = f'{BASE_URL}/facematch/upload/galleries/{gallery}/enrollments/{ENROLLMENT_ID}'

    r = requests.post(
        url,
        headers=UPLOAD_HEADERS,
        files={'image': ('image.jpg', image_bytes, 'image/jpeg')},
    )

    print(f'[UPLOAD ENROLL] URL        : {url}')
    print(f'[UPLOAD ENROLL] Gallery    : {gallery}')
    print(f'[UPLOAD ENROLL] Identifier : {ENROLLMENT_ID}')
    print(f'[UPLOAD ENROLL] Status     : {r.status_code}')
    print(f'[UPLOAD ENROLL] Trace ID   : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[UPLOAD ENROLL] Success    : {body.get("success")}')
        print(f'[UPLOAD ENROLL] Identifier : {body.get("identifier")}')
        print(f'[UPLOAD ENROLL] Gallery    : {body.get("gallery")}')
    else:
        print(f'[UPLOAD ENROLL] Response   : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    # Cleanup — remove the enrollment so session_gallery stays clean
    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ENROLLMENT_ID}',
        headers=UPLOAD_HEADERS,
    )


if __name__ == '__main__':
    test_upload_enroll()
