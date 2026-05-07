# -*- coding: utf-8 -*-
"""
test_1to1_score.py — 1:1 Compare score behaviour validation.

TC-C01  Self-compare (same image) returns score > baseline (> 10.0)
TC-C02  Genuine pair via enrolled template returns score >= threshold
TC-C03  Impostor pair via enrolled template returns score < threshold
TC-C04  Partial face scores lower than full-face self-compare
TC-C05  Symmetry: score(A→B) ≈ score(B→A), delta < 0.1 — within 1:1 only
TC-C06  Score is deterministic: same pair always returns identical score
TC-C07  Threshold changes match flag only — score value is unchanged
TC-C08  Response schema: score is float >= 0, match is bool, trace ID present

Important:
- Scores are NOT cross-asserted with 1:N Search results.
- Maintain separate baselines for compare vs search.
"""

import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES
from tests.utils import service_version, service_algorithm

# ── Configuration ─────────────────────────────────────────────────────────────
GALLERY           = 'today2'   # genuine enrollments — created if not found, never deleted
IMPOSTOR_GALLERY  = 'today01'  # impostor enrollments — created if not found, never deleted
SCORE_THRESHOLD   = 4.0
THRESHOLD_EXTREME = 999.0
COMPARE_SELF_MIN  = 15.0       # floor for compare(A,A): observed 16.28 (test_baseline_consistency)
ALGORITHM = service_algorithm()

PROBE_KEY    = 'dan_face'
IMPOSTOR_KEY = 'john_face'  # genuinely different person — scores low against dan_face probe
PARTIAL_KEY  = 'part_face'
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


def _compare_images(probe_b64, candidate_b64, threshold=SCORE_THRESHOLD):
    """1:1 compare using two raw images (no gallery lookup)."""
    return requests.post(
        f'{BASE_URL}/facematch/compare',
        headers=HEADERS,
        json={
            'probe':     {'image': probe_b64},
            'candidate': {'image': candidate_b64},
            'threshold': threshold,
        },
    )


def _compare_enrolled(probe_b64, ident, gallery, threshold=SCORE_THRESHOLD):
    """1:1 compare using a probe image against an enrolled template."""
    return requests.post(
        f'{BASE_URL}/facematch/compare',
        headers=HEADERS,
        json={
            'probe':     {'image': probe_b64},
            'candidate': {'id': ident, 'gallery': gallery},
            'threshold': threshold,
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


def _score_verdict(score, threshold):
    """Return a human-readable explanation of the score value."""
    if score is None:
        return 'N/A'
    fmr_exp  = -score
    fmr_pct  = 10 ** fmr_exp * 100
    decision = 'MATCH' if score >= threshold else 'NO MATCH'
    return (
        f'{score:.4f}  →  FMR ≈ 1 in 10^{score:.1f}  '
        f'({fmr_pct:.4f}% false match rate)  [{decision}]'
    )


def _log(tag, threshold, status, score, match, trace_id):
    print(f'\n[{tag}] Algorithm       : {ALGORITHM}')
    print(f'[{tag}] Service version : {service_version()}')
    print(f'[{tag}] Gallery         : {GALLERY}')
    print(f'[{tag}] Threshold       : {threshold}  (FMR = 1 in 10^{threshold:.0f} = {10**-threshold*100:.4f}%)')
    print(f'[{tag}] HTTP status     : {status}')
    print(f'[{tag}] Score verdict   : {_score_verdict(score, threshold)}')
    print(f'[{tag}] Match           : {match}')
    print(f'[{tag}] Trace ID        : {trace_id}')


# ── TC-C01 ────────────────────────────────────────────────────────────────────

def test_compare_self_match_high_score():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r     = _compare_images(image_b64, image_b64, SCORE_THRESHOLD)
    body  = r.json() if r.status_code == 200 else {}
    score = body.get('score')
    match = body.get('match')

    _log('TC-C01', SCORE_THRESHOLD, r.status_code, score, match,
         r.headers.get('x-aware-trace-id', 'not returned'))
    print(f'[TC-C01] Baseline min   : > {COMPARE_SELF_MIN}  '
          f'(same image must score very high — near-certain identity)')
    print(f'[TC-C01] Why expected   : comparing an image to itself is the upper bound; '
          f'score > 10 means FMR < 1 in 10 billion')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert isinstance(score, (int, float)), f'score is not numeric: {score!r}'
    assert score > COMPARE_SELF_MIN, (
        f'Self-compare score {score:.4f} is below floor {COMPARE_SELF_MIN}. '
        f'Observed baseline for this system: 16.2800 (test_baseline_consistency). '
        f'A same-image comparison must produce a very high score — possible feature extraction regression or wrong image.'
    )
    assert match is True, f'Expected match=True for self-compare, got {match}'


# ── TC-C02 ────────────────────────────────────────────────────────────────────

def test_compare_genuine_enrolled_above_threshold():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    ident    = f'genuine_c02_{uuid.uuid4().hex[:8]}'
    r_enroll = _enroll(GALLERY, ident, image_b64)
    assert r_enroll.status_code == 200, f'Enrollment failed: {r_enroll.status_code}: {r_enroll.text}'

    r     = _compare_enrolled(image_b64, ident, GALLERY, SCORE_THRESHOLD)
    body  = r.json() if r.status_code == 200 else {}
    score = body.get('score')
    match = body.get('match')

    _log('TC-C02', SCORE_THRESHOLD, r.status_code, score, match,
         r.headers.get('x-aware-trace-id', 'not returned'))
    print(f'[TC-C02] Enrolled ID    : {ident}')
    print(f'[TC-C02] Mode           : probe image vs enrolled template (same person)')
    print(f'[TC-C02] Why expected   : same identity — score must be >= {SCORE_THRESHOLD} '
          f'(FMR <= {10**-SCORE_THRESHOLD*100:.4f}%)')

    _delete_enrollment(GALLERY, ident)

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert score >= SCORE_THRESHOLD, (
        f'Genuine pair score {score:.4f} < threshold {SCORE_THRESHOLD}. '
        f'The probe and enrolled template are the same person — score should clear the threshold. '
        f'FMR at this score: {10**-score*100:.4f}%  (threshold allows up to {10**-SCORE_THRESHOLD*100:.4f}%)'
    )
    assert match is True, f'Expected match=True for genuine pair, got {match}'


# ── TC-C03 ────────────────────────────────────────────────────────────────────

def test_compare_impostor_below_threshold():
    probe_b64    = IMAGES.get(PROBE_KEY)
    impostor_b64 = IMAGES.get(IMPOSTOR_KEY)
    if not probe_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')
    if not impostor_b64:
        pytest.fail(f'Image key "{IMPOSTOR_KEY}" not found in config. Check your .env file.')

    ident    = f'impostor_c03_{uuid.uuid4().hex[:8]}'
    r_enroll = _enroll(IMPOSTOR_GALLERY, ident, impostor_b64)
    assert r_enroll.status_code == 200, f'Enrollment failed: {r_enroll.status_code}: {r_enroll.text}'

    try:
        r     = _compare_enrolled(probe_b64, ident, IMPOSTOR_GALLERY, SCORE_THRESHOLD)
        body  = r.json() if r.status_code == 200 else {}
        score = body.get('score')
        match = body.get('match')

        _log('TC-C03', SCORE_THRESHOLD, r.status_code, score, match,
             r.headers.get('x-aware-trace-id', 'not returned'))
        print(f'[TC-C03] Probe key      : {PROBE_KEY}')
        print(f'[TC-C03] Impostor key   : {IMPOSTOR_KEY}')
        print(f'[TC-C03] Enrolled ID    : {ident}')
        print(f'[TC-C03] Why expected   : different people — score must be < {SCORE_THRESHOLD}. '
              f'A high score here would mean the matcher falsely identifies them as the same person.')
    finally:
        _delete_enrollment(IMPOSTOR_GALLERY, ident)

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert score < SCORE_THRESHOLD, (
        f'Impostor score {score:.4f} >= threshold {SCORE_THRESHOLD}. '
        f'This is a FALSE MATCH — the matcher incorrectly identified two different people as the same. '
        f'FMR at threshold {SCORE_THRESHOLD}: {10**-SCORE_THRESHOLD*100:.4f}%  '
        f'Actual score implies FMR of {10**-score*100:.4f}%'
    )
    assert match is False, f'Expected match=False for impostor pair, got {match}'


# ── TC-C04 ────────────────────────────────────────────────────────────────────

def test_compare_partial_face_lower_score():
    full_b64    = IMAGES.get(PROBE_KEY)
    partial_b64 = IMAGES.get(PARTIAL_KEY)
    if not full_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')
    if not partial_b64:
        pytest.fail(f'Image key "{PARTIAL_KEY}" not found in config. Check your .env file.')

    r_self    = _compare_images(full_b64, full_b64, SCORE_THRESHOLD)
    r_partial = _compare_images(partial_b64, full_b64, SCORE_THRESHOLD)

    score_self    = r_self.json().get('score')    if r_self.status_code    == 200 else None
    score_partial = r_partial.json().get('score') if r_partial.status_code == 200 else None

    print(f'\n[TC-C04] Algorithm       : {ALGORITHM}')
    print(f'[TC-C04] Service version : {service_version()}')
    print(f'[TC-C04] Gallery         : {GALLERY}')
    print(f'[TC-C04] Full-face key   : {PROBE_KEY}')
    print(f'[TC-C04] Partial key     : {PARTIAL_KEY}')
    print(f'[TC-C04] Score full      : {_score_verdict(score_self, SCORE_THRESHOLD)}')
    print(f'[TC-C04] Score partial   : {_score_verdict(score_partial, SCORE_THRESHOLD)}')
    print(f'[TC-C04] Why expected    : reduced image quality (partial face) must produce a '
          f'lower confidence score — the matcher has less facial data to work with')

    assert r_self.status_code    == 200, f'Self compare failed: {r_self.status_code}: {r_self.text}'
    assert r_partial.status_code == 200, f'Partial compare failed: {r_partial.status_code}: {r_partial.text}'
    assert score_partial < score_self, (
        f'Partial face score {score_partial:.4f} should be < full-face score {score_self:.4f}. '
        f'A partial/occluded face must score lower than a clear full-face image of the same person.'
    )


# ── TC-C05 ────────────────────────────────────────────────────────────────────

def test_compare_symmetry():
    """Symmetry is asserted within 1:1 only — not cross-endpoint."""
    a_b64 = IMAGES.get(PROBE_KEY)
    b_b64 = IMAGES.get(IMPOSTOR_KEY)
    if not a_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')
    if not b_b64:
        pytest.fail(f'Image key "{IMPOSTOR_KEY}" not found in config. Check your .env file.')

    r_ab = _compare_images(a_b64, b_b64, SCORE_THRESHOLD)
    r_ba = _compare_images(b_b64, a_b64, SCORE_THRESHOLD)

    score_ab = r_ab.json().get('score') if r_ab.status_code == 200 else None
    score_ba = r_ba.json().get('score') if r_ba.status_code == 200 else None
    delta    = abs(score_ab - score_ba) if (score_ab is not None and score_ba is not None) else None

    print(f'\n[TC-C05] Algorithm       : {ALGORITHM}')
    print(f'[TC-C05] Service version : {service_version()}')
    print(f'[TC-C05] Gallery         : {GALLERY}')
    print(f'[TC-C05] Probe A key     : {PROBE_KEY}')
    print(f'[TC-C05] Probe B key     : {IMPOSTOR_KEY}')
    print(f'[TC-C05] Score A→B       : {_score_verdict(score_ab, SCORE_THRESHOLD)}')
    print(f'[TC-C05] Score B→A       : {_score_verdict(score_ba, SCORE_THRESHOLD)}')
    print(f'[TC-C05] Delta           : {delta:.4f}' if delta is not None else '[TC-C05] Delta : N/A')
    print(f'[TC-C05] Why expected    : similarity is a symmetric metric — '
          f'comparing A to B must give the same confidence as comparing B to A. '
          f'A large asymmetry would indicate a bug in feature extraction ordering.')

    assert r_ab.status_code == 200, f'A→B compare failed: {r_ab.status_code}: {r_ab.text}'
    assert r_ba.status_code == 200, f'B→A compare failed: {r_ba.status_code}: {r_ba.text}'
    assert delta is not None, 'Could not compute delta — one or both scores missing'
    assert delta < 0.1, (
        f'Symmetry violation: |score(A→B) - score(B→A)| = {delta:.4f} >= 0.1. '
        f'The matcher should produce equal confidence regardless of probe/candidate order.'
    )


# ── TC-C06 ────────────────────────────────────────────────────────────────────

def test_compare_score_deterministic():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r1 = _compare_images(image_b64, image_b64, SCORE_THRESHOLD)
    r2 = _compare_images(image_b64, image_b64, SCORE_THRESHOLD)

    score1 = r1.json().get('score') if r1.status_code == 200 else None
    score2 = r2.json().get('score') if r2.status_code == 200 else None

    print(f'\n[TC-C06] Algorithm       : {ALGORITHM}')
    print(f'[TC-C06] Service version : {service_version()}')
    print(f'[TC-C06] Gallery         : {GALLERY}')
    print(f'[TC-C06] Run 1 score     : {_score_verdict(score1, SCORE_THRESHOLD)}')
    print(f'[TC-C06] Run 2 score     : {_score_verdict(score2, SCORE_THRESHOLD)}')
    print(f'[TC-C06] Delta           : {abs(score1 - score2):.6f}' if (score1 and score2) else '[TC-C06] Delta : N/A')
    print(f'[TC-C06] Why expected    : 1:1 compare is a direct exact computation — '
          f'same inputs must always produce bit-for-bit identical output. '
          f'Any difference indicates non-determinism in feature extraction or the matcher.')

    assert r1.status_code == 200, f'Run 1 failed: {r1.status_code}: {r1.text}'
    assert r2.status_code == 200, f'Run 2 failed: {r2.status_code}: {r2.text}'
    assert score1 == score2, (
        f'1:1 compare is not deterministic: run1={score1}  run2={score2}. '
        f'This should never happen — the exact matcher must be fully deterministic.'
    )


# ── TC-C07 ────────────────────────────────────────────────────────────────────

def test_compare_threshold_changes_match_not_score():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r_low  = _compare_images(image_b64, image_b64, SCORE_THRESHOLD)
    r_high = _compare_images(image_b64, image_b64, THRESHOLD_EXTREME)

    body_low  = r_low.json()  if r_low.status_code  == 200 else {}
    body_high = r_high.json() if r_high.status_code == 200 else {}

    score_low  = body_low.get('score')
    score_high = body_high.get('score')
    match_low  = body_low.get('match')
    match_high = body_high.get('match')

    print(f'\n[TC-C07] Algorithm       : {ALGORITHM}')
    print(f'[TC-C07] Service version : {service_version()}')
    print(f'[TC-C07] Gallery         : {GALLERY}')
    print(f'[TC-C07] Low  threshold={SCORE_THRESHOLD:<6}  '
          f'score={_score_verdict(score_low, SCORE_THRESHOLD)}  match={match_low}')
    print(f'[TC-C07] High threshold={THRESHOLD_EXTREME:<6}  '
          f'score={_score_verdict(score_high, THRESHOLD_EXTREME)}  match={match_high}')
    print(f'[TC-C07] Why expected    : the threshold is a post-score decision boundary. '
          f'The matcher computes the score first, then compares it to the threshold. '
          f'Changing the threshold must not alter the underlying similarity score — '
          f'only the match=True/False verdict changes.')

    assert r_low.status_code  == 200, f'Low-threshold compare failed: {r_low.status_code}'
    assert r_high.status_code == 200, f'High-threshold compare failed: {r_high.status_code}'
    assert score_low == score_high, (
        f'Score changed when only threshold changed: '
        f'low={score_low}  high={score_high}. '
        f'Threshold must not affect score computation.'
    )
    assert match_low  is True,  f'Expected match=True  at threshold {SCORE_THRESHOLD}'
    assert match_high is False, f'Expected match=False at threshold {THRESHOLD_EXTREME}'


# ── TC-C08 ────────────────────────────────────────────────────────────────────

def test_compare_response_schema():
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    r    = _compare_images(image_b64, image_b64, SCORE_THRESHOLD)
    body = r.json() if r.status_code == 200 else {}

    score = body.get('score')

    print(f'\n[TC-C08] Algorithm       : {ALGORITHM}')
    print(f'[TC-C08] Service version : {service_version()}')
    print(f'[TC-C08] Gallery         : {GALLERY}')
    print(f'[TC-C08] HTTP status     : {r.status_code}')
    print(f'[TC-C08] Trace ID        : {r.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[TC-C08] Score           : {_score_verdict(score, SCORE_THRESHOLD)}')
    print(f'[TC-C08] Match           : {body.get("match")}')
    print(f'[TC-C08] Full body       : {body}')
    print(f'[TC-C08] Why expected    : API contract validation — '
          f'"score" must be a non-negative float, "match" must be a bool, '
          f'and the trace ID header must be present for request tracing.')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    assert 'score' in body,  '"score" key missing from response'
    assert 'match' in body,  '"match" key missing from response'
    assert isinstance(body.get('score'), (int, float)), (
        f'"score" must be numeric, got {type(body.get("score"))!r}'
    )
    assert isinstance(body.get('match'), bool), (
        f'"match" must be bool, got {type(body.get("match"))!r}'
    )
    assert body.get('score') >= 0.0, (
        f'"score" must be >= 0, got {body.get("score")}'
    )
    assert r.headers.get('x-aware-trace-id'), 'x-aware-trace-id header missing from response'
