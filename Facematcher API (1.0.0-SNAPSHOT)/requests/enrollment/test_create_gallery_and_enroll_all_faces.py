# -*- coding: utf-8 -*-
import requests
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

GALLERY_NAME = 'testtoday'  # fallback for standalone run

def test_create_gallery_and_enroll_all_faces(session_gallery):
    # PRE-REQUEST: session_gallery was already created by the fixture —
    # this test just enrolls all available images into it.
    gallery = session_gallery

    # Enroll each image from IMAGES
    available = {k: v for k, v in IMAGES.items() if v}
    missing   = [k for k, v in IMAGES.items() if not v]

    if missing:
        print(f'[ENROLL] Skipping (not in .env): {", ".join(missing)}')

    print(f'[ENROLL] Enrolling {len(available)} face(s) into "{gallery}"')
    print()

    results = []
    for identifier, image_base64 in available.items():
        enroll_url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{identifier}'
        payload    = {'image': image_base64}

        r = requests.post(enroll_url, headers=HEADERS, json=payload)
        results.append((identifier, r.status_code))

        print(f'[ENROLL] Identifier : {identifier}')
        print(f'[ENROLL] Status     : {r.status_code}')
        print(f'[ENROLL] Trace ID   : {r.headers.get("x-aware-trace-id", "not returned")}')

        if r.status_code == 200:
            body = r.json()
            print(f'[ENROLL] Success    : {body.get("success")}')
            print(f'[ENROLL] Gallery    : {body.get("gallery")}')
        else:
            print(f'[ENROLL] Response   : {r.text}')
        print()

    # Summary
    print('--- Summary ---')
    for identifier, status in results:
        print(f'  {identifier:<12} : {status}')

    # 200 = enrolled, 409 = already enrolled (e.g. by bulk enroll test) — both are acceptable
    failed = [(i, s) for i, s in results if s not in (200, 409)]
    assert not failed, f'Some enrollments failed: {failed}'

if __name__ == '__main__':
    test_create_gallery_and_enroll_all_faces()
