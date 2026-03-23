# -*- coding: utf-8 -*-
import requests
import pytest
import base64
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

PROBE_KEY  = 'dan_face'
ENROLL_ID  = 'upload_compare_candidate'
THRESHOLD  = 4.0

UPLOAD_HEADERS = {k: v for k, v in HEADERS.items() if k.lower() != 'content-type'}


def test_upload_compare(session_gallery):
    gallery     = session_gallery
    probe_image = IMAGES.get(PROBE_KEY)

    if not probe_image:
        pytest.fail(f'Probe image key "{PROBE_KEY}" not found in config. Check your .env file.')

    # Enroll the candidate so there is something to compare against.
    enroll_r = requests.post(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ENROLL_ID}',
        headers=HEADERS,
        json={'image': probe_image},
    )
    print(f'[UPLOAD COMPARE] Pre-enroll status : {enroll_r.status_code}')
    assert enroll_r.status_code == 200, f'Pre-enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    probe_bytes = base64.b64decode(probe_image)

    # POST /facematch/upload/compare
    url = f'{BASE_URL}/facematch/upload/compare'

    r = requests.post(
        url,
        headers=UPLOAD_HEADERS,
        files={'probe_image': ('probe.jpg', probe_bytes, 'image/jpeg')},
        data={
            'candidate_id':      ENROLL_ID,
            'candidate_gallery': gallery,
            'threshold':        THRESHOLD,
        },
    )

    print(f'[UPLOAD COMPARE] URL              : {url}')
    print(f'[UPLOAD COMPARE] Probe            : {PROBE_KEY}')
    print(f'[UPLOAD COMPARE] Candidate ID     : {ENROLL_ID}')
    print(f'[UPLOAD COMPARE] Gallery          : {gallery}')
    print(f'[UPLOAD COMPARE] Threshold        : {THRESHOLD}')
    print(f'[UPLOAD COMPARE] Status           : {r.status_code}')
    print(f'[UPLOAD COMPARE] Trace ID         : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        print(f'[UPLOAD COMPARE] Score            : {body.get("score")}')
        print(f'[UPLOAD COMPARE] Match            : {body.get("match")}')
    else:
        print(f'[UPLOAD COMPARE] Response         : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    # Cleanup
    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ENROLL_ID}',
        headers=HEADERS,
    )


if __name__ == '__main__':
    test_upload_compare()
