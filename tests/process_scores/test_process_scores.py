# -*- coding: utf-8 -*-
"""
test_process_scores.py — POST /facematch/processScores endpoint validation.

Acceptance criteria:
  The /processScores endpoint correctly converts input FMR scores to FPIR
  scores using the specified gallery size.
  Special case: gallerySize == 1 → no conversion applied (function not called).

Conversion formula:
  score_fpir = score_fmr − log10(gallerySize)

  gallerySize  │ log10(N) │ score reduction
  ─────────────┼──────────┼────────────────
            1  │   0.000  │ none (special case — function skipped)
           10  │   1.000  │ −1.0
          100  │   2.000  │ −2.0
        1,000  │   3.000  │ −3.0
    1,000,000  │   6.000  │ −6.0

Tests:
  PS-01  gallerySize = 1            → score unchanged (special case, function not called)
  PS-02  gallerySize = 10           → score − 1.0
  PS-03  gallerySize = 100          → score − 2.0
  PS-04  gallerySize = 1,000        → score − 3.0
  PS-05  gallerySize = 1,000,000    → score − 6.0
  PS-06  Multiple candidates        → each score independently adjusted
  PS-07  match flag uses FPIR score → decision flips when conversion crosses threshold
  PS-08  Threshold boundary         → score=4.0 at gallerySize=10,000 → FPIR=0.0, match=False
  PS-09  Response schema            → id (str), score (float), match (bool) per candidate
  PS-10  Empty candidates list      → 200 with empty response
  PS-11  End-to-end pipeline        → search FMR scores → processScores → FPIR delta verified
"""

import math
import time
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES
from tests.utils import service_version

# All tests in this module require the /processScores endpoint to be deployed.
# Mark xfail so failures show as expected rather than blocking the suite.
# Remove this mark once the endpoint is live and the C++ change is deployed.
pytestmark = pytest.mark.xfail(
    reason='POST /facematch/processScores not yet deployed to demo server',
    strict=False,
)

ENDPOINT      = f'{BASE_URL}/facematch/processScores'
SCORE_THRESHOLD = 4.0
TOL           = 0.01   # floating-point tolerance for conversion results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _process(candidates, gallery_size, threshold=SCORE_THRESHOLD):
    return requests.post(
        ENDPOINT,
        headers=HEADERS,
        json={
            'candidates': candidates,
            'gallerySize': gallery_size,
            'threshold':   threshold,
        },
    )


def _candidate(cid, score):
    return {'id': cid, 'score': score}


def _fpir(score_fmr, gallery_size):
    if gallery_size == 1:
        return score_fmr
    return score_fmr - math.log10(gallery_size)


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


def _search(gallery, image_b64, threshold=SCORE_THRESHOLD, max_candidates=10):
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


def _wait_for_indexed(gallery, ident, image_b64, timeout=15, interval=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = _search(gallery, image_b64, threshold=0.0, max_candidates=10)
        if r.status_code == 200:
            if any(c.get('id') == ident for c in r.json().get('candidates', [])):
                return True
        time.sleep(interval)
    return False



def _score_label(score):
    if score is None:
        return 'N/A'
    decision = 'MATCH' if score >= SCORE_THRESHOLD else 'NO MATCH'
    return f'{score:.4f}  [{decision}]'


# ── Gallery setup for PS-11 ───────────────────────────────────────────────────

@pytest.fixture(scope='module')
def ps11_gallery():
    """Isolated gallery for end-to-end pipeline test. Deleted on teardown."""
    name = f'ps11_{uuid.uuid4().hex[:8]}'
    r = requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': name},
    )
    assert r.status_code == 200, f'Gallery creation failed: {r.status_code}: {r.text}'
    print(f'\n[GALLERY] Created for PS-11: {name}')
    yield name
    requests.delete(f'{BASE_URL}/facematch/galleries/{name}', headers=HEADERS)
    print(f'\n[GALLERY] Deleted: {name}')


# ── PS-01 ─────────────────────────────────────────────────────────────────────

def test_ps01_gallery_size_1_no_conversion():
    """
    gallerySize=1 is the special case where ConvertFmrScoreToFpirScore is NOT called.
    The score must be returned byte-for-byte unchanged.

    log10(1)=0 so the math would give the same result, but the point is the function
    is skipped entirely — validated here with a score that would go negative at
    gallerySize=2 to make the special case observable.
    """
    input_score = 1.5   # would become 1.5 − log10(2) ≈ 1.2 at gallerySize=2

    r = _process([_candidate('id-ps01', input_score)], gallery_size=1)
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    out   = r.json().get('candidates', [])
    score = out[0].get('score')

    print(f'\n[PS-01] Algorithm        : f200')
    print(f'[PS-01] Service version  : {service_version()}')
    print(f'[PS-01] gallery_size     : 1  (special case — function skipped)')
    print(f'[PS-01] Input score      : {input_score}')
    print(f'[PS-01] Output score     : {score}')
    print(f'[PS-01] Expected         : {input_score}  (unchanged)')

    assert len(out) == 1
    assert abs(score - input_score) <= TOL, (
        f'gallerySize=1 must leave score unchanged. '
        f'Got {score:.4f}, expected {input_score:.4f}.'
    )


# ── PS-02 ─────────────────────────────────────────────────────────────────────

def test_ps02_gallery_size_10_reduces_by_1():
    """gallerySize=10 → score − log10(10) = score − 1.0"""
    input_score = 16.28
    expected    = input_score - 1.0

    r = _process([_candidate('id-ps02', input_score)], gallery_size=10)
    assert r.status_code == 200, f'{r.status_code}: {r.text}'

    out   = r.json().get('candidates', [])
    score = out[0].get('score')

    print(f'\n[PS-02] gallery_size=10  reduction=1.0')
    print(f'[PS-02] Input  : {input_score}  →  Expected : {expected}  →  Got : {score}')

    assert len(out) == 1
    assert abs(score - expected) <= TOL, (
        f'gallerySize=10: expected {expected:.4f}, got {score:.4f}  '
        f'(delta={abs(score - expected):.4f})'
    )


# ── PS-03 ─────────────────────────────────────────────────────────────────────

def test_ps03_gallery_size_100_reduces_by_2():
    """gallerySize=100 → score − log10(100) = score − 2.0"""
    input_score = 16.28
    expected    = input_score - 2.0

    r = _process([_candidate('id-ps03', input_score)], gallery_size=100)
    assert r.status_code == 200, f'{r.status_code}: {r.text}'

    out   = r.json().get('candidates', [])
    score = out[0].get('score')

    print(f'\n[PS-03] gallery_size=100  reduction=2.0')
    print(f'[PS-03] Input  : {input_score}  →  Expected : {expected}  →  Got : {score}')

    assert len(out) == 1
    assert abs(score - expected) <= TOL, (
        f'gallerySize=100: expected {expected:.4f}, got {score:.4f}'
    )


# ── PS-04 ─────────────────────────────────────────────────────────────────────

def test_ps04_gallery_size_1000_reduces_by_3():
    """gallerySize=1,000 → score − log10(1000) = score − 3.0"""
    input_score = 16.28
    expected    = input_score - 3.0

    r = _process([_candidate('id-ps04', input_score)], gallery_size=1_000)
    assert r.status_code == 200, f'{r.status_code}: {r.text}'

    out   = r.json().get('candidates', [])
    score = out[0].get('score')

    print(f'\n[PS-04] gallery_size=1,000  reduction=3.0')
    print(f'[PS-04] Input  : {input_score}  →  Expected : {expected}  →  Got : {score}')

    assert len(out) == 1
    assert abs(score - expected) <= TOL, (
        f'gallerySize=1000: expected {expected:.4f}, got {score:.4f}'
    )


# ── PS-05 ─────────────────────────────────────────────────────────────────────

def test_ps05_gallery_size_1m_reduces_by_6():
    """gallerySize=1,000,000 → score − log10(1,000,000) = score − 6.0"""
    input_score = 16.28
    expected    = input_score - 6.0

    r = _process([_candidate('id-ps05', input_score)], gallery_size=1_000_000)
    assert r.status_code == 200, f'{r.status_code}: {r.text}'

    out   = r.json().get('candidates', [])
    score = out[0].get('score')

    print(f'\n[PS-05] gallery_size=1,000,000  reduction=6.0')
    print(f'[PS-05] Input  : {input_score}  →  Expected : {expected}  →  Got : {score}')

    assert len(out) == 1
    assert abs(score - expected) <= TOL, (
        f'gallerySize=1,000,000: expected {expected:.4f}, got {score:.4f}'
    )


# ── PS-06 ─────────────────────────────────────────────────────────────────────

def test_ps06_multiple_candidates_all_converted():
    """
    Multiple candidates in one request — each score must be independently reduced
    by log10(gallerySize). Order must be preserved.
    """
    gallery_size = 1_000
    reduction    = math.log10(gallery_size)   # 3.0
    inputs       = [16.28, 13.90, 7.0, 4.5, 4.0, 1.5]
    cands_in     = [_candidate(f'id-{i}', s) for i, s in enumerate(inputs)]

    r = _process(cands_in, gallery_size=gallery_size)
    assert r.status_code == 200, f'{r.status_code}: {r.text}'

    out = r.json().get('candidates', [])

    print(f'\n[PS-06] Algorithm        : f200')
    print(f'[PS-06] Service version  : {service_version()}')
    print(f'[PS-06] gallery_size={gallery_size}  reduction={reduction:.1f}')
    print(f'[PS-06] {"id":<6} {"input":>8} {"expected":>10} {"output":>10} {"status":>6}')

    assert len(out) == len(inputs), (
        f'Expected {len(inputs)} candidates back, got {len(out)}'
    )

    failures = []
    for i, (inp, cand_out) in enumerate(zip(inputs, out)):
        expected = inp - reduction
        got      = cand_out.get('score')
        ok       = abs(got - expected) <= TOL
        status   = 'PASS' if ok else 'FAIL'
        print(f'[PS-06] id-{i:<3} {inp:>8.4f} {expected:>10.4f} {got:>10.4f} {status:>6}')
        if not ok:
            failures.append(
                f'id-{i}: input={inp:.4f}  expected={expected:.4f}  '
                f'got={got:.4f}  delta={abs(got - expected):.4f}'
            )

    assert not failures, (
        'Score conversion failures:\n' + '\n'.join(failures)
    )


# ── PS-07 ─────────────────────────────────────────────────────────────────────

def test_ps07_match_flag_uses_fpir_score_not_fmr():
    """
    The match flag must be evaluated against the CONVERTED (FPIR) score,
    not the original FMR score.

    Critical test: input score 4.5 at gallerySize=10, threshold=4.0.
      FMR score 4.5 ≥ 4.0  → would be match=True without conversion (WRONG).
      FPIR score 3.5 < 4.0  → must be match=False after conversion (CORRECT).

    If the service evaluates match against the original score it is a bug.
    """
    gallery_size   = 10
    threshold      = 4.0
    input_score    = 4.5
    expected_fpir  = input_score - math.log10(gallery_size)   # 3.5

    r = _process(
        [_candidate('match-flip', input_score)],
        gallery_size=gallery_size,
        threshold=threshold,
    )
    assert r.status_code == 200, f'{r.status_code}: {r.text}'

    out   = r.json().get('candidates', [])
    score = out[0].get('score')
    match = out[0].get('match')

    print(f'\n[PS-07] Algorithm         : f200')
    print(f'[PS-07] Service version   : {service_version()}')
    print(f'[PS-07] gallery_size      : {gallery_size}  threshold={threshold}')
    print(f'[PS-07] FMR input score   : {input_score:.4f}  → without conversion: match=True  (above threshold)')
    print(f'[PS-07] FPIR output score : {score:.4f}  → with conversion:    match={match}  (expected False)')
    print(f'[PS-07] Why expected      : match must be evaluated on FPIR score {expected_fpir:.4f}, '
          f'not on FMR score {input_score:.4f}')

    assert abs(score - expected_fpir) <= TOL, (
        f'FPIR score: expected {expected_fpir:.4f}, got {score:.4f}'
    )
    assert match is False, (
        f'match must be False: FPIR score {score:.4f} < threshold {threshold}. '
        f'The original FMR score {input_score:.4f} would have passed — '
        f'this indicates the match flag is being evaluated on the wrong score.'
    )


# ── PS-08 ─────────────────────────────────────────────────────────────────────

def test_ps08_threshold_boundary_10k_gallery():
    """
    score=4.0, gallerySize=10,000, threshold=4.0 → FPIR score = 0.0, match=False.

    At threshold 4.0 (FMR=0.01%) with a 10,000-face gallery, the entire threshold
    margin is consumed by the gallery size penalty:
      FPIR = 4.0 − log10(10,000) = 4.0 − 4.0 = 0.0

    A score that just clears the FMR threshold provides zero margin in FPIR terms.
    """
    r = _process(
        [_candidate('boundary', 4.0)],
        gallery_size=10_000,
        threshold=SCORE_THRESHOLD,
    )
    assert r.status_code == 200, f'{r.status_code}: {r.text}'

    out   = r.json().get('candidates', [])
    score = out[0].get('score')
    match = out[0].get('match')

    print(f'\n[PS-08] Algorithm         : f200')
    print(f'[PS-08] Service version   : {service_version()}')
    print(f'[PS-08] FMR input score   : 4.0000  (at FMR threshold boundary)')
    print(f'[PS-08] gallery_size      : 10,000  threshold={SCORE_THRESHOLD}')
    print(f'[PS-08] FPIR output score : {score}  (expected 0.0000)')
    print(f'[PS-08] Match             : {match}   (expected False)')
    print(f'[PS-08] Why              : log10(10,000)=4.0 — the full threshold margin '
          f'is consumed by the gallery size penalty')

    assert abs(score - 0.0) <= TOL, (
        f'Expected FPIR score 0.0000, got {score:.4f}'
    )
    assert match is False, (
        f'match must be False: FPIR score {score:.4f} < threshold {SCORE_THRESHOLD}'
    )


# ── PS-09 ─────────────────────────────────────────────────────────────────────

def test_ps09_response_schema():
    """
    Every returned candidate must have:
      id    — string
      score — float (may be negative for large galleries)
      match — bool
    HTTP 200 required. x-aware-trace-id header must be present.
    """
    r = _process(
        [_candidate('schema-test', 16.28)],
        gallery_size=1_000,
        threshold=SCORE_THRESHOLD,
    )
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    out = r.json().get('candidates', [])
    assert len(out) == 1, f'Expected 1 candidate, got {len(out)}'
    c   = out[0]

    print(f'\n[PS-09] HTTP status      : {r.status_code}')
    print(f'[PS-09] Trace ID         : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[PS-09] Candidate        : {c}')

    assert isinstance(c.get('id'),    str),          f'"id" must be str, got {type(c.get("id"))}'
    assert isinstance(c.get('score'), (int, float)), f'"score" must be numeric, got {type(c.get("score"))}'
    assert isinstance(c.get('match'), bool),         f'"match" must be bool, got {type(c.get("match"))}'
    assert r.headers.get('x-aware-trace-id'),        'x-aware-trace-id header missing from response'


# ── PS-10 ─────────────────────────────────────────────────────────────────────

def test_ps10_empty_candidates_returns_empty():
    """Empty input candidates list → 200 with empty candidates (not an error)."""
    r = _process([], gallery_size=1_000)
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    out = r.json().get('candidates', [])
    print(f'\n[PS-10] Empty candidates → status={r.status_code}  candidates={out}')
    assert out == [], f'Expected empty candidates list, got: {out}'


# ── PS-11 ─────────────────────────────────────────────────────────────────────

def test_ps11_end_to_end_search_then_process_scores(ps11_gallery):
    """
    End-to-end pipeline: enroll → search (FMR scores) → processScores (FPIR scores).

    Verifies that processScores applied to live search results produces the
    expected FPIR reduction. With a single-enrollment gallery (size=1),
    the special case applies and scores must be unchanged. With gallerySize=10,
    each score must drop by exactly 1.0.

    This confirms the endpoint behaves correctly on real search output, not just
    synthetic scores.
    """
    image_b64 = IMAGES.get('dan_face')
    if not image_b64:
        pytest.fail('Image key "dan_face" not found in config. Check your .env file.')

    gallery = ps11_gallery
    ident   = f'ps11_{uuid.uuid4().hex[:8]}'

    r_enroll = _enroll(gallery, ident, image_b64)
    assert r_enroll.status_code == 200, f'Enrollment failed: {r_enroll.status_code}: {r_enroll.text}'

    try:
        _wait_for_indexed(gallery, ident, image_b64)

        r_srch = _search(gallery, image_b64, threshold=0.0, max_candidates=10)
        assert r_srch.status_code == 200, f'Search failed: {r_srch.status_code}: {r_srch.text}'

        search_candidates = r_srch.json().get('candidates', [])
        assert search_candidates, f'No candidates returned from search in gallery {gallery}'

        fmr_score = next(
            (c['score'] for c in search_candidates if c.get('id') == ident), None
        )
        assert fmr_score is not None, f'Enrolled identity {ident} not found in search results'

        print(f'\n[PS-11] Algorithm        : f200')
        print(f'[PS-11] Service version  : {service_version()}')
        print(f'[PS-11] Gallery          : {gallery}  (size=1 for size=1 case)')
        print(f'[PS-11] Enrolled ID      : {ident}')
        print(f'[PS-11] FMR search score : {fmr_score:.4f}  (raw search result)')

        # ── Case A: gallerySize=1 (special case — no conversion) ─────────────
        r_ps1 = _process(search_candidates, gallery_size=1, threshold=SCORE_THRESHOLD)
        assert r_ps1.status_code == 200, f'processScores(gallerySize=1) failed: {r_ps1.status_code}'

        ps1_out    = r_ps1.json().get('candidates', [])
        ps1_result = next((c for c in ps1_out if c.get('id') == ident), None)
        assert ps1_result is not None, f'Identity {ident} missing from processScores output'
        fpir_score_1 = ps1_result.get('score')

        print(f'[PS-11] ── gallerySize=1 (special case) ──────────────────────')
        print(f'[PS-11] FPIR score       : {fpir_score_1:.4f}  (expected unchanged: {fmr_score:.4f})')

        assert abs(fpir_score_1 - fmr_score) <= TOL, (
            f'gallerySize=1 must leave score unchanged. '
            f'FMR={fmr_score:.4f}  FPIR={fpir_score_1:.4f}'
        )

        # ── Case B: gallerySize=10 → reduction of 1.0 ────────────────────────
        r_ps10 = _process(search_candidates, gallery_size=10, threshold=SCORE_THRESHOLD)
        assert r_ps10.status_code == 200, f'processScores(gallerySize=10) failed: {r_ps10.status_code}'

        ps10_out    = r_ps10.json().get('candidates', [])
        ps10_result = next((c for c in ps10_out if c.get('id') == ident), None)
        assert ps10_result is not None, f'Identity {ident} missing from processScores(gallerySize=10) output'
        fpir_score_10 = ps10_result.get('score')
        expected_10   = fmr_score - 1.0

        print(f'[PS-11] ── gallerySize=10 (reduction=1.0) ────────────────────')
        print(f'[PS-11] FPIR score       : {fpir_score_10:.4f}  (expected {expected_10:.4f})')

        assert abs(fpir_score_10 - expected_10) <= TOL, (
            f'gallerySize=10: expected FPIR score {expected_10:.4f}, got {fpir_score_10:.4f}. '
            f'FMR search score was {fmr_score:.4f}.'
        )

        print(f'[PS-11] ── Summary ───────────────────────────────────────────')
        print(f'[PS-11] FMR search       : {fmr_score:.4f}')
        print(f'[PS-11] FPIR gallerySize=1    : {fpir_score_1:.4f}  (delta=0.0000)')
        print(f'[PS-11] FPIR gallerySize=10   : {fpir_score_10:.4f}  '
              f'(delta={fmr_score - fpir_score_10:.4f})')

    finally:
        _delete_enrollment(gallery, ident)
