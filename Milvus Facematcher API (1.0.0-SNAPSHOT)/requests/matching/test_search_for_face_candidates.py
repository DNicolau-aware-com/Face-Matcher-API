# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

PROBE_KEY      = 'dan_face'
MAX_CANDIDATES = 10
THRESHOLD      = 4.0

def test_search_for_face_candidates(session_gallery):
    # PRE-REQUEST: session_gallery has all faces enrolled by test_create_gallery_and_enroll_all_faces
    gallery = session_gallery

    # POST {{BASE_URL}}/facematch/search
    url = f'{BASE_URL}/facematch/search'

    probe_image = IMAGES.get(PROBE_KEY)
    if not probe_image:
        print(f'[SEARCH] ERROR: Probe image key "{PROBE_KEY}" not found in config.')
        pytest.fail(f'[SKIP] Probe image key "{PROBE_KEY}" not found in config.')

    payload = {
        'probe':         {'image': probe_image},
        'gallery':       gallery,
        'maxCandidates': MAX_CANDIDATES,
        'threshold':     THRESHOLD,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[SEARCH] URL            : {url}')
    print(f'[SEARCH] Probe          : {PROBE_KEY}')
    print(f'[SEARCH] Gallery        : {gallery}')
    print(f'[SEARCH] Max Candidates : {MAX_CANDIDATES}')
    print(f'[SEARCH] Threshold      : {THRESHOLD}')
    print(f'[SEARCH] Status         : {r.status_code}')
    print(f'[SEARCH] Trace ID       : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        candidates = r.json().get('candidates', [])
        print(f'[SEARCH] Candidates     : {len(candidates)} returned')
        for i, c in enumerate(candidates, start=1):
            print(f'  [{i}] id={c.get("id")} | score={c.get("score")} | match={c.get("match")}')
    else:
        print(f'[SEARCH] Response       : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'