# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

IMAGE_KEY      = 'dan_face'
THRESHOLD      = 4.0
VERIFY_IDENT   = 'dan_face_verify'  # isolated identifier for self-contained enroll/verify

def test_verify_image_vs_enrolled_identity(session_gallery, shared_state):
    gallery      = session_gallery
    image_base64 = IMAGES.get(IMAGE_KEY)

    if not image_base64:
        print(f'[VERIFY] ERROR: Image key "{IMAGE_KEY}" not found in config. Check your .env file.')
        pytest.fail(f'[SKIP] Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    # PRE-REQUEST: use enrollment_id from shared_state when enrollment tests have already run.
    # Otherwise enroll a dedicated identity now and clean it up after the assertion.
    if shared_state.get('enrollment_id'):
        candidate_id  = shared_state['enrollment_id']
        enrolled_here = False
    else:
        candidate_id  = VERIFY_IDENT
        enroll_url    = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{candidate_id}'
        r_enroll      = requests.post(enroll_url, headers=HEADERS, json={'image': image_base64})
        print(f'[VERIFY] Pre-enroll   : {candidate_id} → {r_enroll.status_code}')
        if r_enroll.status_code not in (200, 409):
            pytest.fail(f'[VERIFY] Pre-enroll failed: {r_enroll.status_code}: {r_enroll.text}')
        enrolled_here = True

    # POST {{BASE_URL}}/facematch/compare
    url = f'{BASE_URL}/facematch/compare'

    payload = {
        'probe':     {'image': image_base64},
        'candidate': {'id': candidate_id, 'gallery': gallery},
        'threshold': THRESHOLD,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[VERIFY] URL          : {url}')
    print(f'[VERIFY] Mode         : image vs enrolled identity')
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

    # Cleanup inline enrollment before asserting so teardown always runs
    if enrolled_here:
        requests.delete(
            f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{candidate_id}',
            headers=HEADERS,
        )

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_verify_image_vs_enrolled_identity()
