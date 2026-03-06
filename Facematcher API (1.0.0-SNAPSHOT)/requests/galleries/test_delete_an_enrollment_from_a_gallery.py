# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS

GALLERY_NAME  = ''     # fallback for standalone run
ENROLLMENT_ID = 'jane_face' # fallback — enrolled by test_create_gallery_and_enroll_all_faces

def test_delete_an_enrollment_from_a_gallery(session_gallery, shared_state):
    # PRE-REQUEST: session_gallery is the shared gallery.
    # Use enrollment_id captured by test_enroll_a_face_into_a_gallery, or
    # fall back to an identifier enrolled by test_create_gallery_and_enroll_all_faces.
    gallery = session_gallery
    ident   = shared_state.get('enrollment_id', ENROLLMENT_ID)

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
