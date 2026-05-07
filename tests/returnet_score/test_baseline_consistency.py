# -*- coding: utf-8 -*-
"""
test_baseline_consistency.py — Controlled baseline: Enroll → Compare(A,A) → Search(A,G)

Purpose:
  Establish and document the observed score ceiling for this deployment by running
  both endpoints against the same identity in a controlled, clean way.

Why today2 is used (not an isolated gallery):
  Milvus ANN requires a minimum populated gallery to build its index. A brand-new
  single-enrollment gallery is never searchable — ANN returns 0 candidates regardless
  of wait time. today2 already has an active ANN index; adding one enrollment and
  removing it afterwards leaves no permanent state.

Flow:
  1. Ensure today2 exists (create if absent, never delete)
  2. Enroll image A with a unique UUID-based ID → confirm 200
  3. Poll until A is indexed in the ANN (up to 15 s)
  4. Compare(A, A) — raw image vs image, exact 1:1, no gallery lookup
  5. Search(A, today2) — probe vs gallery, ANN retrieval + re-score
  6. Delete enrollment (today2 remains, only the test enrollment is removed)
  7. Assert both endpoints return match=True
  8. Assert scores differ (different pipelines — expected by design)
  9. Assert both scores >= threshold
 10. Assert compare score >= observed ceiling baseline
 11. Assert search score >= observed ANN re-score baseline
 12. Log delta as system baseline documentation

Observed baseline (ROC F200 / Milvus, demo service, 2026-04-29):
  Compare (image vs image, exact)  : 16.2800
  Search  (ANN re-score via Milvus): 13.9000
  Delta                            : 2.3800
"""

import time
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES
from tests.utils import service_version, service_algorithm

# ── Configuration ─────────────────────────────────────────────────────────────
GALLERY         = 'today2'
SCORE_THRESHOLD = 4.0
ALGORITHM = service_algorithm()
PROBE_KEY       = 'dan_face'

# Observed baseline values — update when service version changes
BASELINE_COMPARE_SCORE = 16.28   # compare(A, A) image-vs-image ceiling
BASELINE_SEARCH_SCORE  = 13.90   # search(A, G)  ANN re-score of same face
BASELINE_DELTA         =  2.38   # expected endpoint divergence for same-image pair

# Hard floors — test fails if observed scores drop below these
COMPARE_MIN    = 15.0   # compare(A,A) must be at least this
SEARCH_MIN     = 12.0   # search rank-1 must be at least this

# Soft ceiling for delta — warning only, not a hard fail
DELTA_MAX_WARN =  3.0
# ──────────────────────────────────────────────────────────────────────────────


# ── Gallery setup ─────────────────────────────────────────────────────────────

@pytest.fixture(scope='module', autouse=True)
def ensure_gallery():
    """Create GALLERY if absent. Never deleted — only test enrollments are removed."""
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


# ── Helpers ───────────────────────────────────────────────────────────────────


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


def _compare_images(probe_b64, candidate_b64, threshold=SCORE_THRESHOLD):
    """1:1 compare — raw image vs image, no gallery, no stored template lookup."""
    return requests.post(
        f'{BASE_URL}/facematch/compare',
        headers=HEADERS,
        json={
            'probe':     {'image': probe_b64},
            'candidate': {'image': candidate_b64},
            'threshold': threshold,
        },
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
    """Poll until the enrolled identity appears in search results or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = _search(gallery, image_b64, threshold=0.0, max_candidates=50)
        if r.status_code == 200:
            if any(c.get('id') == ident for c in r.json().get('candidates', [])):
                return True
        time.sleep(interval)
    return False


def _score_label(score):
    if score is None:
        return 'N/A'
    fmr_pct  = 10 ** (-score) * 100
    decision = 'MATCH' if score >= SCORE_THRESHOLD else 'NO MATCH'
    if score >= 12.0:
        quality = 'very high confidence (near-certain identity)'
    elif score >= SCORE_THRESHOLD:
        quality = f'above threshold  (FMR {fmr_pct:.4f}%)'
    else:
        quality = f'below threshold  (FMR {fmr_pct:.4f}%)'
    return f'{score:.4f}  [{decision}]  {quality}'


# ── Baseline test ─────────────────────────────────────────────────────────────

def test_enroll_compare_search_consistency():
    """
    Controlled baseline: enroll A into today2, compare(A,A), search(A, today2),
    document the score delta, assert both endpoints agree on match=True, cleanup.

    The 1:1 compare is image-vs-image (ceiling score, no stored template).
    The 1:N search retrieves the enrolled template via ANN then re-scores.
    These pipelines are fundamentally different — the delta is expected and documented.
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config. Check your .env file.')

    ident = f'baseline-{uuid.uuid4().hex[:8]}'

    # Step 1: Enroll
    r_enroll = _enroll(GALLERY, ident, image_b64)
    assert r_enroll.status_code == 200, (
        f'Enrollment failed: {r_enroll.status_code}: {r_enroll.text}'
    )

    # Step 2: Wait for ANN index to include the new enrollment
    indexed = _wait_for_indexed(GALLERY, ident, image_b64)

    # Step 3: Run both endpoints
    r_cmp  = _compare_images(image_b64, image_b64, SCORE_THRESHOLD)
    r_srch = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)

    # Step 4: Cleanup — remove only this enrollment, leave gallery intact
    _delete_enrollment(GALLERY, ident)

    assert r_cmp.status_code  == 200, f'Compare failed: {r_cmp.status_code}: {r_cmp.text}'
    assert r_srch.status_code == 200, f'Search failed: {r_srch.status_code}: {r_srch.text}'

    score_cmp  = r_cmp.json().get('score')
    match_cmp  = r_cmp.json().get('match')
    candidates = r_srch.json().get('candidates', [])
    top        = next((c for c in candidates if c.get('id') == ident), None)

    assert top is not None, (
        f'Enrolled identity {ident} not found in 1:N results (indexed={indexed}).\n'
        f'Candidates returned: {[c.get("id") for c in candidates]}'
    )

    score_srch = top.get('score')
    match_srch = top.get('match')
    delta      = abs(score_cmp - score_srch)

    # ── Logging ───────────────────────────────────────────────────────────────
    print(f'\n[BASELINE] Algorithm                 : {ALGORITHM}')
    print(f'[BASELINE] Service version           : {service_version()}')
    print(f'[BASELINE] Gallery                   : {GALLERY}')
    print(f'[BASELINE] Enrolled ID               : {ident}')
    print(f'[BASELINE] Indexed (poll ≤15 s)      : {indexed}')
    print(f'[BASELINE]')
    print(f'[BASELINE] ── 1:1 Compare (image vs image, exact) ──────────────')
    print(f'[BASELINE] Score observed            : {_score_label(score_cmp)}')
    print(f'[BASELINE] Score baseline            : {BASELINE_COMPARE_SCORE:.4f}  (documented ceiling)')
    print(f'[BASELINE] Match                     : {match_cmp}')
    print(f'[BASELINE]')
    print(f'[BASELINE] ── 1:N Search (ANN retrieval + re-score) ────────────')
    print(f'[BASELINE] Rank-1 ID                 : {top.get("id")}')
    print(f'[BASELINE] Score observed            : {_score_label(score_srch)}')
    print(f'[BASELINE] Score baseline            : {BASELINE_SEARCH_SCORE:.4f}  (documented ANN re-score)')
    print(f'[BASELINE] Match                     : {match_srch}')
    print(f'[BASELINE]')
    print(f'[BASELINE] ── Cross-endpoint delta ─────────────────────────────')
    print(f'[BASELINE] Delta observed            : {delta:.4f}')
    print(f'[BASELINE] Delta baseline            : {BASELINE_DELTA:.4f}  (expected for same-image pair)')
    if delta > DELTA_MAX_WARN:
        print(f'[BASELINE] *** WARNING: delta {delta:.4f} > {DELTA_MAX_WARN} — '
              f'ANN quantization or model version mismatch suspected ***')
    print(f'[BASELINE]')
    print(f'[BASELINE] ── Why scores differ ────────────────────────────────')
    print(f'[BASELINE] Compare: raw image→image exact computation, no stored template.')
    print(f'[BASELINE] Search : stored (quantized) enrolled template, ANN retrieval.')
    print(f'[BASELINE] A delta of ~{delta:.1f} is expected and normal for this system.')

    # ── Assertions ────────────────────────────────────────────────────────────

    assert match_cmp is True, (
        f'1:1 compare returned match=False for a same-image pair.\n'
        f'  Score: {score_cmp:.4f}  Threshold: {SCORE_THRESHOLD}'
    )
    assert match_srch is True, (
        f'1:N search returned match=False for the enrolled identity.\n'
        f'  Score: {score_srch:.4f}  Threshold: {SCORE_THRESHOLD}'
    )
    assert score_cmp >= SCORE_THRESHOLD, (
        f'Compare score {score_cmp:.4f} below threshold {SCORE_THRESHOLD}.'
    )
    assert score_srch >= SCORE_THRESHOLD, (
        f'Search score {score_srch:.4f} below threshold {SCORE_THRESHOLD}.'
    )
    assert score_cmp != score_srch, (
        f'Both endpoints returned identical scores ({score_cmp:.4f}).\n'
        f'  Compare is exact image-vs-image; search uses the stored ANN template.\n'
        f'  These pipelines must produce different scores.'
    )
    assert score_cmp >= COMPARE_MIN, (
        f'Compare score {score_cmp:.4f} dropped below floor {COMPARE_MIN}.\n'
        f'  Documented baseline: {BASELINE_COMPARE_SCORE:.4f}\n'
        f'  Possible cause: feature extraction regression or wrong image.'
    )
    assert score_srch >= SEARCH_MIN, (
        f'Search score {score_srch:.4f} dropped below floor {SEARCH_MIN}.\n'
        f'  Documented baseline: {BASELINE_SEARCH_SCORE:.4f}\n'
        f'  Possible cause: ANN index degradation or template version mismatch.'
    )
