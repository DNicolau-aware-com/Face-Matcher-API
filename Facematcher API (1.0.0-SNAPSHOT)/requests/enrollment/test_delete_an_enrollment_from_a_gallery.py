# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

def test_delete_an_enrollment_from_a_gallery(session_gallery, shared_state):
    # PRE-REQUEST: use enrollment_id captured by a previous enroll test when available.
    # When running standalone (no prior enroll), enroll a temporary face first so there
    # is always a valid identifier to delete.
    gallery = session_gallery
    ident   = shared_state.get('enrollment_id')

    if not ident:
        ident = 'delete_test_id'
        image_base64 = IMAGES.get('dan_face') or next((v for v in IMAGES.values() if v), None)
        enroll_url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}'
        r_enroll = requests.post(enroll_url, headers=HEADERS, json={'image': image_base64})
        print(f'[DELETE ENROLLMENT] Pre-enroll    : {ident} → {r_enroll.status_code}')

    # DELETE {{BASE_URL}}/facematch/galleries/{galleryName}/enrollments/{identifier}
    url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}'

    r = requests.delete(url, headers=HEADERS)

    print(f'[DELETE ENROLLMENT] URL           : {url}')
    print(f'[DELETE ENROLLMENT] Gallery       : {gallery}')
    print(f'[DELETE ENROLLMENT] Identifier    : {ident}')
    print(f'[DELETE ENROLLMENT] Status        : {r.status_code}')
    print(f'[DELETE ENROLLMENT] Trace ID      : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 204:
        print('[DELETE ENROLLMENT] Response      : Enrollment deleted (no body)')
    elif r.status_code == 404:
        print('[DELETE ENROLLMENT] Response      : Enrollment not found')
    else:
        print(f'[DELETE ENROLLMENT] Response      : {r.text}')

    assert r.status_code == 204, f'Expected 204, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_delete_an_enrollment_from_a_gallery()
