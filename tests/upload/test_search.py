# -*- coding: utf-8 -*-
import requests
import pytest
import base64
import sys, os
from config import BASE_URL, HEADERS, IMAGES

PROBE_KEY      = 'dan_face'
MAX_CANDIDATES = 10
THRESHOLD      = 4.0
ENROLL_ID      = 'upload_search_probe'

UPLOAD_HEADERS = {k: v for k, v in HEADERS.items() if k.lower() != 'content-type'}


def test_upload_search(session_gallery):
    gallery     = session_gallery
    probe_image = IMAGES.get(PROBE_KEY)

    if not probe_image:
        pytest.fail(f'Probe image key "{PROBE_KEY}" not found in config. Check your .env file.')

    # Ensure probe face is enrolled so the search returns at least one candidate.
    # (Idempotent — 400 Gallery Exists / duplicate is fine to ignore here.)
    enroll_r = requests.post(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ENROLL_ID}',
        headers=HEADERS,
        json={'image': probe_image},
    )
    print(f'[UPLOAD SEARCH] Pre-enroll status : {enroll_r.status_code}')

    probe_bytes = base64.b64decode(probe_image)

    # POST /facematch/upload/search
    url = f'{BASE_URL}/facematch/upload/search'

    r = requests.post(
        url,
        headers=UPLOAD_HEADERS,
        files={'image': ('probe.jpg', probe_bytes, 'image/jpeg')},
        data={
            'gallery':       gallery,
            'maxCandidates': MAX_CANDIDATES,
            'threshold':     THRESHOLD,
        },
    )

    print(f'[UPLOAD SEARCH] URL             : {url}')
    print(f'[UPLOAD SEARCH] Probe           : {PROBE_KEY}')
    print(f'[UPLOAD SEARCH] Gallery         : {gallery}')
    print(f'[UPLOAD SEARCH] Max Candidates  : {MAX_CANDIDATES}')
    print(f'[UPLOAD SEARCH] Threshold       : {THRESHOLD}')
    print(f'[UPLOAD SEARCH] Status          : {r.status_code}')
    print(f'[UPLOAD SEARCH] Trace ID        : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        candidates = r.json().get('candidates', [])
        print(f'[UPLOAD SEARCH] Candidates      : {len(candidates)} returned')
        for i, c in enumerate(candidates, start=1):
            print(f'  [{i}] id={c.get("id")} | score={c.get("score")} | match={c.get("match")}')
    else:
        print(f'[UPLOAD SEARCH] Response        : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    # Cleanup
    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ENROLL_ID}',
        headers=HEADERS,
    )


if __name__ == '__main__':
    test_upload_search()
