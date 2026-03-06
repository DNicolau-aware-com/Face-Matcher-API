# -*- coding: utf-8 -*-
import requests
import pytest
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from config import BASE_URL, HEADERS, IMAGES

GALLERY_NAME   = 'bulk5'  # fallback for standalone run
IMAGE_KEY      = 'part_face'
MAX_CANDIDATES = 1000
THRESHOLD      = 4.0

def test_search(session_gallery):
    # PRE-REQUEST: session_gallery is the shared gallery for this run
    gallery = session_gallery

    # POST {{BASE_URL}}/facematch/search
    url = f'{BASE_URL}/facematch/search'

    image_base64 = IMAGES.get(IMAGE_KEY)
    if not image_base64:
        print(f'[SEARCH] ERROR: Image key "{IMAGE_KEY}" not found in config. Check your .env file.')
        pytest.fail(f'[SKIP] Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    payload = {
        'probe':         {'image': image_base64},
        'gallery':       gallery,
        'maxCandidates': MAX_CANDIDATES,
        'threshold':     THRESHOLD,
    }

    r = requests.post(url, headers=HEADERS, json=payload)

    print(f'[SEARCH] URL            : {url}')
    print(f'[SEARCH] Gallery        : {gallery}')
    print(f'[SEARCH] Max Candidates : {MAX_CANDIDATES}')
    print(f'[SEARCH] Threshold      : {THRESHOLD}')
    print(f'[SEARCH] Status         : {r.status_code}')
    print(f'[SEARCH] Trace ID       : {r.headers.get("x-aware-trace-id", "not returned")}')

    if r.status_code == 200:
        body = r.json()
        candidates = body.get('candidates', [])
        print(f'[SEARCH] Candidates     : {len(candidates)} returned')
        for i, c in enumerate(candidates, start=1):
            # score = scoreFmr (-log10(FMR)), higher = better match
            # match = True if score >= threshold
            print(f'  [{i}] id={c.get("id")} | score={c.get("score")} | match={c.get("match")}')
    else:
        print(f'[SEARCH] Response       : {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

if __name__ == '__main__':
    test_search()
