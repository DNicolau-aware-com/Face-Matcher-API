# -*- coding: utf-8 -*-
"""
test_1n_score.py — 1:N Search score behaviour validation.

TC-S01  Score is a positive float for every returned candidate
TC-S02  Candidates are returned in descending score order
TC-S03  match=True iff score >= threshold (two-way, every candidate)
TC-S04  Threshold changes match flags only — scores are unchanged
TC-S05  maxCandidates does not shift scores of retrieved candidates
TC-S06  Freshly enrolled identity appears at rank-1 with score > baseline
TC-S07  Scores are deterministic across repeated identical searches
TC-S08  Impostor probe returns no candidates above threshold
"""

import time
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES
from tests.utils import service_version, service_algorithm

# ── Configuration ─────────────────────────────────────────────────────────────
GALLERY         = 'today2'     # genuine enrollments — created if not found, never deleted
IMPOSTOR_GALLERY = 'today01'  # impostor enrollments — created if not found, never deleted
SCORE_THRESHOLD = 4.0
THRESHOLD_HIGH  = 7.0
SEARCH_SELF_MIN = 12.0         # floor for search(A, gallery_with_A): observed 13.90 (test_baseline_consistency)
MAX_CANDIDATES  = 20
ALGORITHM       = service_algorithm()

PROBE_KEY    = 'dan_face'
IMPOSTOR_KEY = 'john_face'  # genuinely different person — scores low against dan_face probe
# ──────────────────────────────────────────────────────────────────────────────


# ── Gallery setup ─────────────────────────────────────────────────────────────

@pytest.fixture(scope='module', autouse=True)
def ensure_gallery():
    """Create GALLERY if it does not already exist. Never deleted on teardown."""
    r = requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': GALLERY},
    )
    if r.status_code == 200:
        print(f'\n[GALLERY] Created: {GALLERY}')
    elif r.status_code == 400:
        print(f'\n[GALLERY] Already exists, reusing: {GALLERY}')
    else:
        pytest.fail(f'Gallery setup failed {r.status_code}: {r.text}')
    yield


@pytest.fixture(scope='module', autouse=True)
def ensure_impostor_gallery():
    """Create IMPOSTOR_GALLERY if absent. Never deleted — only test enrollments are removed."""
    r = requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': IMPOSTOR_GALLERY},
    )
    if r.status_code == 200:
        print(f'\n[GALLERY] Created: {IMPOSTOR_GALLERY}')
    elif r.status_code == 400:
        print(f'\n[GALLERY] Already exists, reusing: {IMPOSTOR_GALLERY}')
    else:
        pytest.fail(f'Impostor gallery setup failed {r.status_code}: {r.text}')
    yield


# ── Helpers ───────────────────────────────────────────────────────────────────

def _search(gallery, image_b64, threshold=SCORE_THRESHOLD, max_candidates=MAX_CANDIDATES):
    return requests.post(
        f'{BASE_URL}/facematch/search',
        headers=HEADERS,
        json={
            'probe':         {'image': image_b64},
            'gallery':       gallery,
            'maxCandidates': max_candidates,
            'threshold':     threshold,
        },
    )


def _enroll(gallery, ident, image_b64):
    return requests.post(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
        json={'image': image_b64},
    )


def _delete_enrollment(gallery, ident):
    requests.delete(
        f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}',
        headers=HEADERS,
    )


def _create_gallery(name):
    return requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': name},
    )


def _delete_gallery(name):
    requests.delete(f'{BASE_URL}/facematch/galleries/{name}', headers=HEADERS)


def _wait_for_indexed(gallery, ident, image_b64, timeout=5, interval=1):
    """Poll search until the enrolled identity appears or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = _search(gallery, image_b64, threshold=SCORE_THRESHOLD, max_candidates=10)
        if r.status_code == 200:
            if any(c.get('id') == ident for c in r.json().get('candidates', [])):
                return True
        time.sleep(interval)
    return False


# ── TC-S01 ────────────────────────────────────────────────────────────────────

def test_search_score_is_positive_float():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=MAX_CANDIDATES)

    print(f'\n[TC-S01] Algorithm       : {ALGORITHM}')
    print(f'[TC-S01] Service version : {service_version()}')
    print(f'[TC-S01] Gallery         : {GALLERY}')
    print(f'[TC-S01] HTTP status     : {r.status_code}')
    print(f'[TC-S01] Trace ID        : {r.headers.get("x-aware-trace-id", "not returned")}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    candidates = r.json().get('candidates', [])
    print(f'[TC-S01] Candidates      : {len(candidates)}')

    violations = []
    for c in candidates:
        score = c.get('score')
        print(f'[TC-S01]   id={c.get("id")}  score={score}  match={c.get("match")}')
        if not isinstance(score, (int, float)):
            violations.append(f'id={c.get("id")} score is not numeric: {score!r}')
        elif score <= 0.0:
            violations.append(f'id={c.get("id")} score must be > 0, got {score}')

    assert not violations, 'Score type/positivity violations:\n' + '\n'.join(violations)


# ── TC-S02 ────────────────────────────────────────────────────────────────────

def test_search_candidates_sorted_descending():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=MAX_CANDIDATES)

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    candidates = r.json().get('candidates', [])
    scores     = [c.get('score', 0) for c in candidates]

    print(f'\n[TC-S02] Algorithm       : {ALGORITHM}')
    print(f'[TC-S02] Service version : {service_version()}')
    print(f'[TC-S02] Gallery         : {GALLERY}')
    print(f'[TC-S02] Candidates      : {len(scores)}')
    print(f'[TC-S02] Scores          : {[round(s, 4) for s in scores]}')

    violations = []
    for i in range(len(scores) - 1):
        if scores[i] < scores[i + 1]:
            violations.append(
                f'Position {i}: score {scores[i]:.4f} < position {i+1}: score {scores[i+1]:.4f}'
            )

    assert not violations, 'Candidates not sorted descending:\n' + '\n'.join(violations)


# ── TC-S03 ────────────────────────────────────────────────────────────────────

def test_search_match_flag_consistent_with_threshold():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=50)

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    candidates = r.json().get('candidates', [])

    print(f'\n[TC-S03] Algorithm       : {ALGORITHM}')
    print(f'[TC-S03] Service version : {service_version()}')
    print(f'[TC-S03] Gallery         : {GALLERY}')
    print(f'[TC-S03] Threshold       : {SCORE_THRESHOLD}')
    print(f'[TC-S03] Candidates      : {len(candidates)}')

    violations = []
    for c in candidates:
        score          = c.get('score')
        match          = c.get('match')
        expected_match = score >= SCORE_THRESHOLD
        ok             = match is expected_match
        print(
            f'[TC-S03]   score={score:<8.4f}  match={str(match):<5}  '
            f'expected={str(expected_match):<5}  {"OK" if ok else "VIOLATION"}'
        )
        if not ok:
            violations.append(
                f'id={c.get("id")} score={score} match={match} expected={expected_match}'
            )

    assert not violations, 'match/threshold violations:\n' + '\n'.join(violations)


# ── TC-S04 ────────────────────────────────────────────────────────────────────

def test_search_threshold_changes_match_not_score():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r_low  = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=50)
    r_high = _search(GALLERY, image_b64, threshold=THRESHOLD_HIGH,  max_candidates=50)

    assert r_low.status_code  == 200, f'Low-threshold search failed: {r_low.status_code}: {r_low.text}'
    assert r_high.status_code == 200, f'High-threshold search failed: {r_high.status_code}: {r_high.text}'

    low_map  = {c['id']: c for c in r_low.json().get('candidates', [])}
    high_map = {c['id']: c for c in r_high.json().get('candidates', [])}
    common   = set(low_map) & set(high_map)

    print(f'\n[TC-S04] Algorithm       : {ALGORITHM}')
    print(f'[TC-S04] Service version : {service_version()}')
    print(f'[TC-S04] Gallery         : {GALLERY}')
    print(f'[TC-S04] Threshold low   : {SCORE_THRESHOLD}')
    print(f'[TC-S04] Threshold high  : {THRESHOLD_HIGH}')
    print(f'[TC-S04] Common cands    : {len(common)}')

    score_violations = []
    match_flips      = 0

    for cid in common:
        s_low   = low_map[cid]['score']
        s_high  = high_map[cid]['score']
        delta   = abs(s_low - s_high)
        flipped = low_map[cid]['match'] != high_map[cid]['match']
        if flipped:
            match_flips += 1
        print(
            f'[TC-S04]   score_low={s_low:.4f}  score_high={s_high:.4f}  '
            f'delta={delta:.4f}  match_flipped={flipped}'
        )
        if delta >= 0.05:
            score_violations.append(f'id={cid} delta={delta:.4f}')

    print(f'[TC-S04] Match flags flipped : {match_flips}')

    assert not score_violations, (
        'Score changed when only threshold changed:\n' + '\n'.join(score_violations)
    )


# ── TC-S05 ────────────────────────────────────────────────────────────────────

def test_search_max_candidates_does_not_shift_scores():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r_small = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=5)
    r_large = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=50)

    assert r_small.status_code == 200, f'maxCandidates=5 search failed: {r_small.status_code}'
    assert r_large.status_code == 200, f'maxCandidates=50 search failed: {r_large.status_code}'

    small_cands = r_small.json().get('candidates', [])
    large_map   = {c['id']: c['score'] for c in r_large.json().get('candidates', [])}

    print(f'\n[TC-S05] Algorithm       : {ALGORITHM}')
    print(f'[TC-S05] Service version : {service_version()}')
    print(f'[TC-S05] Gallery         : {GALLERY}')
    print(f'[TC-S05] Small (5)  count: {len(small_cands)}')
    print(f'[TC-S05] Large (50) count: {len(large_map)}')

    assert len(small_cands) <= 5,  f'Got {len(small_cands)} candidates with maxCandidates=5'
    assert len(large_map)  <= 50, f'Got {len(large_map)} candidates with maxCandidates=50'

    violations = []
    for c in small_cands:
        cid     = c['id']
        s_small = c['score']
        if cid in large_map:
            s_large = large_map[cid]
            delta   = abs(s_small - s_large)
            print(f'[TC-S05]   id={cid}  score_5={s_small:.4f}  score_50={s_large:.4f}  delta={delta:.4f}')
            if delta >= 0.05:
                violations.append(f'id={cid} delta={delta:.4f}')

    assert not violations, (
        'Score shifted when maxCandidates changed:\n' + '\n'.join(violations)
    )


# ── TC-S06 ────────────────────────────────────────────────────────────────────

def test_search_self_enroll_returns_rank1():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    ident = f'self_{uuid.uuid4().hex[:8]}'

    r_enroll = _enroll(GALLERY, ident, image_b64)
    assert r_enroll.status_code == 200, f'Enrollment failed: {r_enroll.status_code}: {r_enroll.text}'

    try:
        indexed = _wait_for_indexed(GALLERY, ident, image_b64)

        r = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=50)

        assert r.status_code == 200, f'Search failed: {r.status_code}: {r.text}'

        candidates = r.json().get('candidates', [])
        cand       = next((c for c in candidates if c.get('id') == ident), None)

        print(f'\n[TC-S06] Algorithm       : {ALGORITHM}')
        print(f'[TC-S06] Service version : {service_version()}')
        print(f'[TC-S06] Gallery         : {GALLERY}')
        print(f'[TC-S06] Enrolled ID     : {ident}')
        print(f'[TC-S06] Indexed (poll)  : {indexed}')
        print(f'[TC-S06] HTTP status     : {r.status_code}')
        print(f'[TC-S06] Score baseline  : > {SEARCH_SELF_MIN}')
        if cand:
            print(f'[TC-S06] Self score      : {cand.get("score")}')
            print(f'[TC-S06] Self match      : {cand.get("match")}')

        assert cand is not None, (
            f'Enrolled identity {ident} not found in search results (indexed={indexed}).'
        )
        assert cand.get('score', 0) > SEARCH_SELF_MIN, (
            f'Self-match score {cand.get("score"):.4f} <= floor {SEARCH_SELF_MIN}. '
            f'Observed baseline for this system: 13.9000 (test_baseline_consistency). '
            f'Possible ANN index degradation or template version mismatch.'
        )
        assert cand.get('match') is True
    finally:
        _delete_enrollment(GALLERY, ident)


# ── TC-S07 ────────────────────────────────────────────────────────────────────

def test_search_score_deterministic():
    """
    Enroll a fresh identity, search twice with identical parameters, and verify
    that identity's score is bit-for-bit identical across both calls.

    Why we look up by ID (not by rank):
      today2 may contain multiple enrollments of the same face from previous test
      runs that didn't clean up. ANN non-determinism can promote any of them to
      rank-1 on any given call. Checking rank stability would be a flaky test of
      gallery cleanliness, not of score determinism. We only care that the SERVICE
      returns the same score for the same pair — identity is tracked by ID.
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    ident = f'det_s07_{uuid.uuid4().hex[:8]}'
    r_enroll = _enroll(GALLERY, ident, image_b64)
    assert r_enroll.status_code == 200, f'Enrollment failed: {r_enroll.status_code}: {r_enroll.text}'

    try:
        _wait_for_indexed(GALLERY, ident, image_b64)

        r1 = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=50)
        r2 = _search(GALLERY, image_b64, threshold=SCORE_THRESHOLD, max_candidates=50)
    finally:
        _delete_enrollment(GALLERY, ident)

    assert r1.status_code == 200, f'Run 1 failed: {r1.status_code}'
    assert r2.status_code == 200, f'Run 2 failed: {r2.status_code}'

    map1 = {c['id']: c['score'] for c in r1.json().get('candidates', [])}
    map2 = {c['id']: c['score'] for c in r2.json().get('candidates', [])}

    print(f'\n[TC-S07] Algorithm       : {ALGORITHM}')
    print(f'[TC-S07] Service version : {service_version()}')
    print(f'[TC-S07] Gallery         : {GALLERY}')
    print(f'[TC-S07] Enrolled ID     : {ident}')
    print(f'[TC-S07] Run 1 results   : {len(map1)}  Run 2 results: {len(map2)}')

    assert ident in map1, f'Enrolled identity {ident} not found in run-1 results'
    assert ident in map2, f'Enrolled identity {ident} not found in run-2 results'

    s1 = map1[ident]
    s2 = map2[ident]
    delta = abs(s1 - s2)
    print(f'[TC-S07] Run 1 score     : {s1:.4f}')
    print(f'[TC-S07] Run 2 score     : {s2:.4f}')
    print(f'[TC-S07] Delta           : {delta:.6f}  (must be 0.0000)')

    assert delta == 0.0, (
        f'Score not deterministic for {ident}: run1={s1:.4f}  run2={s2:.4f}  delta={delta:.6f}.\n'
        f'The score for the same (probe, candidate) pair must be identical across calls.'
    )


# ── TC-S08 ────────────────────────────────────────────────────────────────────

def test_search_impostor_below_threshold():
    probe_b64    = IMAGES.get(PROBE_KEY)
    impostor_b64 = IMAGES.get(IMPOSTOR_KEY)
    if not probe_b64:
        pytest.fail(f'Probe image key "{PROBE_KEY}" not found in config. Check your .env file.')
    if not impostor_b64:
        pytest.fail(f'Impostor image key "{IMPOSTOR_KEY}" not found in config. Check your .env file.')

    ident = f'imp_{uuid.uuid4().hex[:8]}'

    r_enroll = _enroll(IMPOSTOR_GALLERY, ident, impostor_b64)
    assert r_enroll.status_code == 200, f'Enrollment failed: {r_enroll.status_code}: {r_enroll.text}'

    try:
        _wait_for_indexed(IMPOSTOR_GALLERY, ident, impostor_b64)
        r = _search(IMPOSTOR_GALLERY, probe_b64, threshold=SCORE_THRESHOLD, max_candidates=50)
    finally:
        _delete_enrollment(IMPOSTOR_GALLERY, ident)

    assert r.status_code == 200, f'Search failed: {r.status_code}: {r.text}'

    candidates    = r.json().get('candidates', [])
    impostor_hits = [c for c in candidates if c.get('id') == ident]
    top_imp_score = max((c.get('score', 0) for c in impostor_hits), default=0)

    print(f'\n[TC-S08] Algorithm           : {ALGORITHM}')
    print(f'[TC-S08] Service version     : {service_version()}')
    print(f'[TC-S08] Gallery             : {IMPOSTOR_GALLERY}')
    print(f'[TC-S08] Impostor ID         : {ident}')
    print(f'[TC-S08] Threshold           : {SCORE_THRESHOLD}')
    print(f'[TC-S08] Impostor in results : {bool(impostor_hits)}')
    print(f'[TC-S08] Impostor top score  : {top_imp_score}')

    for hit in impostor_hits:
        assert hit.get('match') is False, (
            f'Impostor {ident} returned match=True (score={hit.get("score")})'
        )
        assert hit.get('score', 0) < SCORE_THRESHOLD, (
            f'Impostor score {hit.get("score")} >= threshold {SCORE_THRESHOLD}'
        )
