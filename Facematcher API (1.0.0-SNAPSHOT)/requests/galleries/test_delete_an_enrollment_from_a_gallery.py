# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

ENROLLMENT_ID = 'delete_test_jane'
IMAGE_KEY     = 'jane_face'

def test_delete_an_enrollment_from_a_gallery(session_gallery, shared_state):
    gallery = session_gallery

    # Enroll a fresh face so this test is self-contained and always has something to delete.
    image_base64 = IMAGES.get(IMAGE_KEY)
    assert image_base64, f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.'

    enroll_url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ENROLLMENT_ID}'
    enroll_r = requests.post(enroll_url, headers=HEADERS, json={'image': image_base64})
    print(f'[DELETE ENROLLMENT] Pre-enroll status : {enroll_r.status_code}')
    assert enroll_r.status_code == 200, f'Pre-enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    # DELETE {{BASE_URL}}/facematch/galleries/{galleryName}/enrollments/{identifier}
    url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ENROLLMENT_ID}'
    r = requests.delete(url, headers=HEADERS)

    print(f'[DELETE ENROLLMENT] URL           : {url}')
    print(f'[DELETE ENROLLMENT] Gallery       : {gallery}')
    print(f'[DELETE ENROLLMENT] Identifier    : {ENROLLMENT_ID}')
    print(f'[DELETE ENROLLMENT] Status        : {r.status_code}')
    print(f'[DELETE ENROLLMENT] Trace ID      : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 204:
        print('[DELETE ENROLLMENT] Response      : Enrollment deleted (no body)')
    else:
        print(f'[DELETE ENROLLMENT] Response      : {r.text}')

    assert r.status_code == 204, f'Expected 204, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_delete_an_enrollment_from_a_gallery()
