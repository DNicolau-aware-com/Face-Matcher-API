# -*- coding: utf-8 -*-
"""
test_search_timed.py — 1:N search against a specific gallery with full result collection.

Searches a configured probe image against a specific gallery and reports:
  - Response time (ms)
  - HTTP status and trace ID
  - Full candidate list (rank, id, score, match)
  - Summary stats (total candidates, matched, top/avg/min score)

Configure GALLERY, IMAGE_KEY, THRESHOLD, and MAX_CANDIDATES below.
"""

import time
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

# ── Configuration ─────────────────────────────────────────────────────────────
GALLERY        = "scale_1m"             # ← set the gallery name to search against
IMAGE_KEY      = "IMAGE_CHIN"     # image key from config/.env
THRESHOLD      = 7.0            # score threshold for match=true
MAX_CANDIDATES = 100         # max candidates to return
# ──────────────────────────────────────────────────────────────────────────────


def test_search_timed():
    url       = f"{BASE_URL}/facematch/search"
    image_b64 = IMAGES.get(IMAGE_KEY)

    if not GALLERY:
        pytest.fail('GALLERY is not set. Edit GALLERY at the top of this file.')

    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config. Check your .env file.')

    payload = {
        "probe":         {"image": image_b64},
        "gallery":       GALLERY,
        "maxCandidates": MAX_CANDIDATES,
        "threshold":     THRESHOLD,
    }

    # ── Send request ──────────────────────────────────────────────────────────
    t0         = time.perf_counter()
    r          = requests.post(url, headers=HEADERS, json=payload)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    trace_id   = r.headers.get("x-aware-trace-id", "not returned")

    # ── Request info ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  SEARCH REQUEST")
    print(f"{'='*60}")
    print(f"  URL            : {url}")
    print(f"  Gallery        : {GALLERY}")
    print(f"  Image key      : {IMAGE_KEY}")
    print(f"  Threshold      : {THRESHOLD}")
    print(f"  Max candidates : {MAX_CANDIDATES}")
    print(f"  HTTP status    : {r.status_code}")
    print(f"  Trace ID       : {trace_id}")
    print(f"  Response time  : {elapsed_ms:.2f} ms")

    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    body       = r.json()
    candidates = body.get("candidates", [])

    # ── Candidate list ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  CANDIDATES ({len(candidates)} returned)")
    print(f"{'='*60}")
    print(f"  {'Rank':<6} {'ID':<40} {'Score':<10} {'Match'}")
    print(f"  {'-'*6} {'-'*40} {'-'*10} {'-'*5}")
    for rank, c in enumerate(candidates, start=1):
        print(f"  {rank:<6} {str(c.get('id', '')):<40} "
              f"{c.get('score', 0):<10.4f} {c.get('match', False)}")

    # ── Summary stats ─────────────────────────────────────────────────────────
    matched = [c for c in candidates if c.get("match") is True]
    scores  = [float(c.get("score", 0)) for c in candidates]

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Response time      : {elapsed_ms:.2f} ms")
    print(f"  Total candidates   : {len(candidates)}")
    print(f"  Matched (match=T)  : {len(matched)}")
    print(f"  Not matched        : {len(candidates) - len(matched)}")

    if scores:
        print(f"  Top score          : {max(scores):.4f}")
        print(f"  Avg score          : {sum(scores)/len(scores):.4f}")
        print(f"  Min score          : {min(scores):.4f}")
        if len(matched) > 0:
            matched_scores = [float(c.get("score", 0)) for c in matched]
            print(f"  Top matched score  : {max(matched_scores):.4f}")
    else:
        print(f"  No candidates returned.")

    print(f"{'='*60}\n")

    # ── Assertions ────────────────────────────────────────────────────────────
    assert isinstance(candidates, list), "Expected candidates to be a list"
    assert elapsed_ms > 0,               "Response time must be positive"
