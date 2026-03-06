# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

IMAGE_KEY    = 'dan_face'
THRESHOLD    = 4.0

VERIFY_IDENT = 'verify_test_id'  # used when running standalone (no prior bulk enroll)

def test_verify_a_face(session_gallery):
    # PRE-REQUEST: when the full suite runs, 'dan_face' is already enrolled by
    # test_create_gallery_and_enroll_all_faces. When running standalone the gallery
    # is empty, so we enroll a temporary identity first and clean it up after.
    gallery      = session_gallery
    image_base64 = IMAGES.get(IMAGE_KEY)

    if not image_base64:
        print(f'[VERIFY] ERROR: Image key "{IMAGE_KEY}" not found in config. Check your .env file.')
        pytest.fail(f'[SKIP] Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    # Check if dan_face is already enrolled (full-suite run)
    candidate_id  = 'dan_face'
    probe_url     = f'{BASE_URL}/facematch/compare'
    check_payload = {
        'probe':     {'image': image_base64},
        'candidate': {'id': candidate_id, 'gallery': gallery},
        'threshold': THRESHOLD,
    }
    check = requests.post(probe_url, headers=HEADERS, json=check_payload)

    if check.status_code == 404:
        # Standalone run — enroll a temporary identity, verify, then remove it
        candidate_id = VERIFY_IDENT
        enroll_url   = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{candidate_id}'
        r_enroll     = requests.post(enroll_url, headers=HEADERS, json={'image': image_base64})
        print(f'[VERIFY] Pre-enroll   : {candidate_id} → {r_enroll.status_code}')
        standalone = True
    else:
        standalone = False

    # POST {{BASE_URL}}/facematch/compare
    url = f'{BASE_URL}/facematch/compare'

    payload = {
        'probe':     {'image': image_base64},
        'candidate': {'id': candidate_id, 'gallery': gallery},
        'threshold': THRESHOLD,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[VERIFY] URL          : {url}')
    print(f'[VERIFY] Probe        : {IMAGE_KEY}')
    print(f'[VERIFY] Candidate ID : {candidate_id}')
    print(f'[VERIFY] Gallery      : {gallery}')
    print(f'[VERIFY] Threshold    : {THRESHOLD}')
    print(f'[VERIFY] Status       : {r.status_code}')
    print(f'[VERIFY] Trace ID     : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[VERIFY] Score        : {body.get("score")}')
        print(f'[VERIFY] Match        : {body.get("match")}')
    else:
        print(f'[VERIFY] Response     : {r.text}')

    if standalone:
        requests.delete(
            f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{candidate_id}',
            headers=HEADERS,
        )

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_verify_a_face()
