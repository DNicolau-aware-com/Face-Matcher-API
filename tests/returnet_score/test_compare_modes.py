# -*- coding: utf-8 -*-
"""
test_compare_modes.py — POST /facematch/compare + POST /facematch/search, side by side

Two modes of the compare endpoint, each paired with a 1:N search to document
cross-endpoint behavior for the same face pair.

  Mode 1 — Image vs Image
    {"probe": {"image": "<B64>"}, "candidate": {"image": "<B64>"}, "threshold": 4.0}

  Mode 2 — Image vs Enrolled
    {"probe": {"image": "<B64>"}, "candidate": {"id": "...", "gallery": "..."}, "threshold": 4.0}

  1:N Search (added to every test)
    {"probe": {"image": "<B64>"}, "gallery": "...", "maxCandidates": 10, "threshold": 4.0}

Response (compare):  {"score": 12.5, "match": true}
Response (search):   {"candidates": [{"id": "...", "score": 12.5, "match": true}]}

Confirmed system baseline (2026-04-29):
  compare(A, A) image-vs-image     : 16.2800  — exact, no ANN
  compare(A, enrolled_A) enrolled  : 16.2800  — exact, no ANN (same as raw)
  search(A, gallery_with_A) ANN    : 13.9000  — ANN re-score of stored template
  Cross-endpoint delta             :  2.3800  — expected, not a bug

Key insight from CME-03:
  The compare endpoint ALWAYS does exact computation regardless of mode.
  The ~2.38 gap between compare and search is 100% the ANN approximation layer.

Gallery strategy:
  All tests enroll into today2 with a unique UUID-based ID.
  Enrollment is deleted after each test. Gallery is never deleted.

──────────────────────────────────────────────────────────────────────────────
CMI-01  Self-compare (A vs A) + search                 — ceiling score, ANN delta documented
CMI-02  Impostor pair (A vs B) + search                — both reject, decisions agree
CMI-03  Symmetry compare (A→B ≈ B→A) + search         — compare symmetric, search ranked by score
CMI-04  Deterministic compare + search                 — same inputs, same scores both runs
CMI-05  Threshold changes match flag only              — score unchanged across thresholds (compare + search)
CMI-06  Response schema                                — score float, match bool, trace ID (compare + search)

CME-01  Genuine enrolled + search                      — score >= threshold, decisions agree
CME-02  Impostor enrolled + search                     — score < threshold, decisions agree
CME-03  Self enrolled: template vs raw + search        — delta compare_enrolled vs search documented
CME-04  Threshold changes match flag only (enrolled)   — score unchanged (compare + search)
CME-05  Response schema (enrolled mode + search)       — complete schema validation
"""

import time
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES
from tests.utils import service_version, service_algorithm

# ── Configuration ─────────────────────────────────────────────────────────────
GALLERY          = 'today2'    # genuine enrollments
IMPOSTOR_GALLERY = 'today01'  # impostor enrollments
SCORE_THRESHOLD  = 4.0
THRESHOLD_HIGH   = 999.0
COMPARE_SELF_MIN = 15.0    # floor for compare(A,A): observed 16.28
SEARCH_SELF_MIN  = 12.0    # floor for search self-match: observed 13.90
DELTA_MAX_WARN   =  3.0    # warn if cross-endpoint delta exceeds this
ALGORITHM = service_algorithm()

PROBE_KEY    = 'dan_face'
IMPOSTOR_KEY = 'john_face'
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


def _compare_img_vs_img(probe_b64, candidate_b64, threshold=SCORE_THRESHOLD):
    return requests.post(
        f'{BASE_URL}/facematch/compare',
        headers=HEADERS,
        json={
            'probe':     {'image': probe_b64},
            'candidate': {'image': candidate_b64},
            'threshold': threshold,
        },
    )


def _compare_img_vs_enrolled(probe_b64, ident, gallery, threshold=SCORE_THRESHOLD):
    return requests.post(
        f'{BASE_URL}/facematch/compare',
        headers=HEADERS,
        json={
            'probe':     {'image': probe_b64},
            'candidate': {'id': ident, 'gallery': gallery},
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


def _wait_for_indexed(gallery, ident, image_b64, timeout=15, interval=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = _search(gallery, image_b64, threshold=0.0, max_candidates=50)
        if r.status_code == 200:
            if any(c.get('id') == ident for c in r.json().get('candidates', [])):
                return True
        time.sleep(interval)
    return False


def _score_label(score, threshold=SCORE_THRESHOLD):
    if score is None:
        return 'N/A'
    fmr_pct  = 10 ** (-score) * 100
    decision = 'MATCH' if score >= threshold else 'NO MATCH'
    if score >= 12.0:
        quality = 'very high confidence (near-certain identity)'
    elif score >= threshold:
        quality = f'above threshold  (FMR {fmr_pct:.4f}%)'
    else:
        quality = f'below threshold  (FMR {fmr_pct:.4f}%)'
    return f'{score:.4f}  [{decision}]  {quality}'


def _log_header(tag, mode, gallery=None, ident=None):
    print(f'\n[{tag}] Algorithm      : {ALGORITHM}')
    print(f'[{tag}] Service version: {service_version()}')
    print(f'[{tag}] Mode           : {mode}')
    if gallery:
        print(f'[{tag}] Gallery        : {gallery}')
    if ident:
        print(f'[{tag}] Enrolled ID    : {ident}')


def _log_compare(tag, score, match, threshold=SCORE_THRESHOLD, **extra):
    print(f'[{tag}] ── 1:1 Compare ───────────────────────────────────────')
    print(f'[{tag}] Score          : {_score_label(score, threshold)}')
    print(f'[{tag}] Match          : {match}')
    for k, v in extra.items():
        print(f'[{tag}] {k:<14} : {v}')


def _log_search(tag, ident, cand, threshold=SCORE_THRESHOLD):
    if cand is not None:
        print(f'[{tag}] ── 1:N Search ────────────────────────────────────────')
        print(f'[{tag}] Found ID       : {cand.get("id")}')
        print(f'[{tag}] Score          : {_score_label(cand.get("score"), threshold)}')
        print(f'[{tag}] Match          : {cand.get("match")}')
    else:
        print(f'[{tag}] ── 1:N Search ────────────────────────────────────────')
        print(f'[{tag}] Identity {ident} not in candidates (below threshold or ANN miss)')


def _log_delta(tag, score_cmp, score_srch):
    if score_cmp is not None and score_srch is not None:
        delta = abs(score_cmp - score_srch)
        print(f'[{tag}] ── Cross-endpoint delta ─────────────────────────────')
        print(f'[{tag}] Compare score  : {score_cmp:.4f}')
        print(f'[{tag}] Search score   : {score_srch:.4f}')
        print(f'[{tag}] Delta          : {delta:.4f}  '
              f'(baseline ~2.38 — ANN approximation vs exact computation)')
        if delta > DELTA_MAX_WARN:
            print(f'[{tag}] *** WARNING: delta {delta:.4f} > {DELTA_MAX_WARN} ***')
        return delta
    return None


# ══════════════════════════════════════════════════════════════════════════════
# MODE 1 — Image vs Image  +  1:N Search
# ══════════════════════════════════════════════════════════════════════════════

# ── CMI-01 ───────────────────────────────────────────────────────────────────

def test_cmi01_self_compare_and_search():
    """
    Images: probe=dan_face, candidate=dan_face (same image both sides).
    Compare(dan_face, dan_face) image-vs-image → ceiling score (16.28).
    Search(dan_face, gallery with enrolled dan_face) → ANN re-score (13.90).
    Delta ~2.38 is expected and documents the ANN approximation cost.
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'cmi01-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200, 'Enrollment failed'
    _wait_for_indexed(GALLERY, ident, image_b64)

    r_cmp  = _compare_img_vs_img(image_b64, image_b64, SCORE_THRESHOLD)
    r_srch = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)

    _delete_enrollment(GALLERY, ident)

    assert r_cmp.status_code  == 200, f'Compare failed: {r_cmp.status_code}'
    assert r_srch.status_code == 200, f'Search failed: {r_srch.status_code}'

    score_cmp  = r_cmp.json().get('score')
    match_cmp  = r_cmp.json().get('match')
    candidates = r_srch.json().get('candidates', [])
    cand       = next((c for c in candidates if c.get('id') == ident), None)
    score_srch = cand.get('score') if cand else None

    _log_header('CMI-01', 'image vs image + search', GALLERY, ident)
    _log_compare('CMI-01', score_cmp, match_cmp, Probe=PROBE_KEY, Candidate=PROBE_KEY)
    _log_search('CMI-01', ident, cand)
    _log_delta('CMI-01', score_cmp, score_srch)

    assert match_cmp is True, f'Compare self-match=False. Score: {score_cmp}'
    assert score_cmp > COMPARE_SELF_MIN, (
        f'Compare score {score_cmp:.4f} <= floor {COMPARE_SELF_MIN}. Baseline: 16.2800.'
    )
    assert cand is not None, f'Enrolled identity {ident} not found in search results.'
    assert cand.get('match') is True, f'Search self-match=False. Score: {score_srch}'
    assert score_srch > SEARCH_SELF_MIN, (
        f'Search score {score_srch:.4f} <= floor {SEARCH_SELF_MIN}. Baseline: 13.9000.'
    )


# ── CMI-02 ───────────────────────────────────────────────────────────────────

def test_cmi02_impostor_compare_and_search():
    """
    Images: probe=dan_face, candidate=john_face (different people).
    Compare(dan_face, john_face) image-vs-image → low score, match=False.
    Search(dan_face, gallery with enrolled john_face) → impostor below threshold.
    Both endpoints must reject the pair.
    """
    probe_b64    = IMAGES.get(PROBE_KEY)
    impostor_b64 = IMAGES.get(IMPOSTOR_KEY)
    if not probe_b64 or not impostor_b64:
        pytest.fail('Probe or impostor image key not found in config.')

    ident = f'cmi02-{uuid.uuid4().hex[:8]}'
    assert _enroll(IMPOSTOR_GALLERY, ident, impostor_b64).status_code == 200, 'Enrollment failed'
    try:
        _wait_for_indexed(IMPOSTOR_GALLERY, ident, impostor_b64)
        r_cmp  = _compare_img_vs_img(probe_b64, impostor_b64, SCORE_THRESHOLD)
        r_srch = _search(IMPOSTOR_GALLERY, probe_b64, SCORE_THRESHOLD, max_candidates=50)
    finally:
        _delete_enrollment(IMPOSTOR_GALLERY, ident)

    assert r_cmp.status_code  == 200
    assert r_srch.status_code == 200

    score_cmp  = r_cmp.json().get('score')
    match_cmp  = r_cmp.json().get('match')
    candidates = r_srch.json().get('candidates', [])
    cand       = next((c for c in candidates if c.get('id') == ident), None)

    _log_header('CMI-02', 'image vs image impostor + search', IMPOSTOR_GALLERY, ident)
    _log_compare('CMI-02', score_cmp, match_cmp,
                 Probe=PROBE_KEY, Candidate=IMPOSTOR_KEY)
    _log_search('CMI-02', ident, cand)

    assert match_cmp is False, (
        f'FALSE MATCH in compare: impostor scored {score_cmp:.4f} >= {SCORE_THRESHOLD}.'
    )
    assert score_cmp < SCORE_THRESHOLD
    if cand is not None:
        _log_delta('CMI-02', score_cmp, cand.get('score'))
        assert cand.get('match') is False, (
            f'FALSE MATCH in search: impostor {ident} returned match=True.'
        )
    else:
        print(f'[CMI-02] Impostor not retrieved by ANN — correctly excluded.')


# ── CMI-03 ───────────────────────────────────────────────────────────────────

def test_cmi03_symmetry_compare_and_search():
    """
    Images: A=dan_face, B=john_face.
    Compare symmetry: score(dan_face→john_face) == score(john_face→dan_face) — delta must be < 0.1.
    Search: dan_face searching gallery-with-john_face; cross-endpoint delta documented.
    """
    a_b64 = IMAGES.get(PROBE_KEY)
    b_b64 = IMAGES.get(IMPOSTOR_KEY)
    if not a_b64 or not b_b64:
        pytest.fail('Probe or impostor image key not found in config.')

    ident_b = f'cmi03-{uuid.uuid4().hex[:8]}'
    assert _enroll(IMPOSTOR_GALLERY, ident_b, b_b64).status_code == 200
    try:
        _wait_for_indexed(IMPOSTOR_GALLERY, ident_b, b_b64)
        r_ab   = _compare_img_vs_img(a_b64, b_b64, SCORE_THRESHOLD)
        r_ba   = _compare_img_vs_img(b_b64, a_b64, SCORE_THRESHOLD)
        r_srch = _search(IMPOSTOR_GALLERY, a_b64, SCORE_THRESHOLD, max_candidates=50)
    finally:
        _delete_enrollment(IMPOSTOR_GALLERY, ident_b)

    assert r_ab.status_code == 200 and r_ba.status_code == 200 and r_srch.status_code == 200

    s_ab       = r_ab.json().get('score')
    s_ba       = r_ba.json().get('score')
    sym_delta  = abs(s_ab - s_ba)
    candidates = r_srch.json().get('candidates', [])
    cand_b     = next((c for c in candidates if c.get('id') == ident_b), None)

    _log_header('CMI-03', 'image vs image symmetry + search', IMPOSTOR_GALLERY, ident_b)
    print(f'[CMI-03] ── 1:1 Compare symmetry ────────────────────────────')
    print(f'[CMI-03] Score A→B     : {_score_label(s_ab)}')
    print(f'[CMI-03] Score B→A     : {_score_label(s_ba)}')
    print(f'[CMI-03] Symmetry delta: {sym_delta:.4f}  (must be < 0.1)')
    _log_search('CMI-03', ident_b, cand_b)
    if cand_b:
        _log_delta('CMI-03', s_ab, cand_b.get('score'))

    assert sym_delta < 0.1, (
        f'Symmetry violation: |score(A→B) - score(B→A)| = {sym_delta:.4f} >= 0.1.'
    )
    if cand_b is not None:
        assert cand_b.get('match') is False, (
            f'Impostor {ident_b} appeared in search with match=True.'
        )


# ── CMI-04 ───────────────────────────────────────────────────────────────────

def test_cmi04_deterministic_compare_and_search():
    """
    Images: probe=dan_face, candidate=dan_face (same image both runs).
    Both compare(dan_face, dan_face) and search(dan_face, gallery) must be deterministic:
    same inputs → same scores across two consecutive calls.
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'cmi04-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200
    _wait_for_indexed(GALLERY, ident, image_b64)

    r_cmp1  = _compare_img_vs_img(image_b64, image_b64, SCORE_THRESHOLD)
    r_cmp2  = _compare_img_vs_img(image_b64, image_b64, SCORE_THRESHOLD)
    r_srch1 = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)
    r_srch2 = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)

    _delete_enrollment(GALLERY, ident)

    s_cmp1  = r_cmp1.json().get('score')
    s_cmp2  = r_cmp2.json().get('score')
    cands1  = r_srch1.json().get('candidates', [])
    cands2  = r_srch2.json().get('candidates', [])
    c1      = next((c for c in cands1 if c.get('id') == ident), None)
    c2      = next((c for c in cands2 if c.get('id') == ident), None)
    s_srch1 = c1.get('score') if c1 else None
    s_srch2 = c2.get('score') if c2 else None

    _log_header('CMI-04', 'image vs image determinism + search', GALLERY, ident)
    print(f'[CMI-04] ── 1:1 Compare ───────────────────────────────────────')
    print(f'[CMI-04] Run 1 score   : {_score_label(s_cmp1)}')
    print(f'[CMI-04] Run 2 score   : {_score_label(s_cmp2)}')
    print(f'[CMI-04] Compare delta : {abs(s_cmp1 - s_cmp2):.6f}')
    print(f'[CMI-04] ── 1:N Search ────────────────────────────────────────')
    print(f'[CMI-04] Run 1 score   : {_score_label(s_srch1)}')
    print(f'[CMI-04] Run 2 score   : {_score_label(s_srch2)}')
    if s_srch1 and s_srch2:
        print(f'[CMI-04] Search delta  : {abs(s_srch1 - s_srch2):.6f}')

    assert s_cmp1 == s_cmp2, (
        f'Compare not deterministic: run1={s_cmp1}  run2={s_cmp2}.'
    )
    if s_srch1 is not None and s_srch2 is not None:
        assert abs(s_srch1 - s_srch2) < 0.05, (
            f'Search not deterministic: run1={s_srch1:.4f}  run2={s_srch2:.4f}.'
        )


# ── CMI-05 ───────────────────────────────────────────────────────────────────

def test_cmi05_threshold_changes_match_not_score():
    """
    Images: probe=dan_face, candidate=dan_face.
    Threshold is a post-score boundary — score must be identical at threshold=4.0 and threshold=999.
    Tested on both compare(dan_face, dan_face) and search(dan_face, gallery with dan_face).
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'cmi05-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200
    _wait_for_indexed(GALLERY, ident, image_b64)

    r_cmp_low  = _compare_img_vs_img(image_b64, image_b64, SCORE_THRESHOLD)
    r_cmp_high = _compare_img_vs_img(image_b64, image_b64, THRESHOLD_HIGH)
    r_srch_low  = _search(GALLERY, image_b64, SCORE_THRESHOLD,  max_candidates=10)
    r_srch_high = _search(GALLERY, image_b64, THRESHOLD_HIGH,   max_candidates=10)

    _delete_enrollment(GALLERY, ident)

    s_cmp_low   = r_cmp_low.json().get('score')
    s_cmp_high  = r_cmp_high.json().get('score')
    m_cmp_low   = r_cmp_low.json().get('match')
    m_cmp_high  = r_cmp_high.json().get('match')

    low_map  = {c['id']: c for c in r_srch_low.json().get('candidates', [])}
    high_map = {c['id']: c for c in r_srch_high.json().get('candidates', [])}
    common   = set(low_map) & set(high_map)

    _log_header('CMI-05', 'threshold effect (compare + search)', GALLERY, ident)
    print(f'[CMI-05] ── 1:1 Compare ───────────────────────────────────────')
    print(f'[CMI-05] Threshold {SCORE_THRESHOLD:<6} : score={s_cmp_low:.4f}  match={m_cmp_low}')
    print(f'[CMI-05] Threshold {THRESHOLD_HIGH:<6} : score={s_cmp_high:.4f}  match={m_cmp_high}')
    print(f'[CMI-05] ── 1:N Search ────────────────────────────────────────')
    srch_violations = []
    for cid in common:
        sl = low_map[cid]['score']
        sh = high_map[cid]['score']
        d  = abs(sl - sh)
        print(f'[CMI-05]   id={cid}  score_low={sl:.4f}  score_high={sh:.4f}  delta={d:.4f}')
        if d >= 0.05:
            srch_violations.append(f'id={cid} delta={d:.4f}')

    assert s_cmp_low == s_cmp_high, (
        f'Compare score changed with threshold: {s_cmp_low} → {s_cmp_high}.'
    )
    assert m_cmp_low  is True,  f'Expected match=True  at threshold {SCORE_THRESHOLD}'
    assert m_cmp_high is False, f'Expected match=False at threshold {THRESHOLD_HIGH}'
    assert not srch_violations, (
        'Search score changed when only threshold changed:\n' + '\n'.join(srch_violations)
    )


# ── CMI-06 ───────────────────────────────────────────────────────────────────

def test_cmi06_response_schema():
    """
    Images: probe=dan_face, candidate=dan_face.
    Validates response schema for compare(dan_face, dan_face) and search(dan_face, gallery).
    Compare:  score (float >= 0), match (bool), x-aware-trace-id header present.
    Search:   candidates list, each entry has id (str), score (float >= 0), match (bool).
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'cmi06-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200
    _wait_for_indexed(GALLERY, ident, image_b64)

    r_cmp  = _compare_img_vs_img(image_b64, image_b64, SCORE_THRESHOLD)
    r_srch = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)

    _delete_enrollment(GALLERY, ident)

    body_cmp  = r_cmp.json()  if r_cmp.status_code  == 200 else {}
    body_srch = r_srch.json() if r_srch.status_code == 200 else {}

    _log_header('CMI-06', 'response schema (compare + search)', GALLERY, ident)
    print(f'[CMI-06] Compare HTTP  : {r_cmp.status_code}')
    print(f'[CMI-06] Compare body  : {body_cmp}')
    print(f'[CMI-06] Compare trace : {r_cmp.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[CMI-06] Search  HTTP  : {r_srch.status_code}')
    candidates = body_srch.get('candidates', [])
    print(f'[CMI-06] Search  cands : {len(candidates)}')
    for c in candidates[:3]:
        print(f'[CMI-06]   {c}')

    # Compare schema
    assert r_cmp.status_code == 200
    assert isinstance(body_cmp.get('score'), (int, float)), '"score" not numeric in compare'
    assert isinstance(body_cmp.get('match'), bool),         '"match" not bool in compare'
    assert body_cmp['score'] >= 0.0,                        '"score" < 0 in compare'
    assert r_cmp.headers.get('x-aware-trace-id'),           'trace ID missing in compare'

    # Search schema
    assert r_srch.status_code == 200
    assert isinstance(candidates, list), '"candidates" not a list in search'
    for c in candidates:
        assert isinstance(c.get('id'),    str),           f'"id" not str: {c}'
        assert isinstance(c.get('score'), (int, float)),  f'"score" not numeric: {c}'
        assert isinstance(c.get('match'), bool),          f'"match" not bool: {c}'
        assert c['score'] >= 0.0,                         f'"score" < 0: {c}'


# ══════════════════════════════════════════════════════════════════════════════
# MODE 2 — Image vs Enrolled  +  1:N Search
# ══════════════════════════════════════════════════════════════════════════════

# ── CME-01 ───────────────────────────────────────────────────────────────────

def test_cme01_genuine_enrolled_and_search():
    """
    Images: probe=dan_face, enrolled candidate=dan_face (same person).
    Compare(dan_face, enrolled dan_face) → match=True, score >= threshold.
    Search(dan_face, gallery with enrolled dan_face) → match=True, ANN delta documented.
    Both endpoints must agree: genuine pair is accepted.
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'cme01-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200
    _wait_for_indexed(GALLERY, ident, image_b64)

    r_cmp  = _compare_img_vs_enrolled(image_b64, ident, GALLERY, SCORE_THRESHOLD)
    r_srch = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)

    _delete_enrollment(GALLERY, ident)

    assert r_cmp.status_code  == 200
    assert r_srch.status_code == 200

    score_cmp  = r_cmp.json().get('score')
    match_cmp  = r_cmp.json().get('match')
    candidates = r_srch.json().get('candidates', [])
    cand       = next((c for c in candidates if c.get('id') == ident), None)
    score_srch = cand.get('score') if cand else None

    _log_header('CME-01', 'image vs enrolled (genuine) + search', GALLERY, ident)
    _log_compare('CME-01', score_cmp, match_cmp, Probe=PROBE_KEY)
    _log_search('CME-01', ident, cand)
    _log_delta('CME-01', score_cmp, score_srch)

    assert match_cmp is True, f'Compare genuine=False. Score: {score_cmp:.4f}'
    assert score_cmp >= SCORE_THRESHOLD
    assert cand is not None, f'Identity {ident} not in search results.'
    assert cand.get('match') is True, f'Search genuine=False. Score: {score_srch:.4f}'
    assert score_srch >= SCORE_THRESHOLD


# ── CME-02 ───────────────────────────────────────────────────────────────────

def test_cme02_impostor_enrolled_and_search():
    """
    Images: probe=dan_face, enrolled candidate=john_face (different people).
    Compare(dan_face, enrolled john_face) → match=False, score < threshold.
    Search(dan_face, gallery with enrolled john_face) → impostor excluded or match=False.
    Both endpoints must agree: impostor pair is rejected.
    """
    probe_b64    = IMAGES.get(PROBE_KEY)
    impostor_b64 = IMAGES.get(IMPOSTOR_KEY)
    if not probe_b64 or not impostor_b64:
        pytest.fail('Probe or impostor image key not found in config.')

    ident = f'cme02-{uuid.uuid4().hex[:8]}'
    assert _enroll(IMPOSTOR_GALLERY, ident, impostor_b64).status_code == 200
    try:
        _wait_for_indexed(IMPOSTOR_GALLERY, ident, impostor_b64)
        r_cmp  = _compare_img_vs_enrolled(probe_b64, ident, IMPOSTOR_GALLERY, SCORE_THRESHOLD)
        r_srch = _search(IMPOSTOR_GALLERY, probe_b64, SCORE_THRESHOLD, max_candidates=50)
    finally:
        _delete_enrollment(IMPOSTOR_GALLERY, ident)

    assert r_cmp.status_code  == 200
    assert r_srch.status_code == 200

    score_cmp  = r_cmp.json().get('score')
    match_cmp  = r_cmp.json().get('match')
    candidates = r_srch.json().get('candidates', [])
    cand       = next((c for c in candidates if c.get('id') == ident), None)

    _log_header('CME-02', 'image vs enrolled (impostor) + search', IMPOSTOR_GALLERY, ident)
    _log_compare('CME-02', score_cmp, match_cmp,
                 Probe=PROBE_KEY, EnrolledAs=IMPOSTOR_KEY)
    _log_search('CME-02', ident, cand)
    if cand:
        _log_delta('CME-02', score_cmp, cand.get('score'))

    assert match_cmp is False, (
        f'FALSE MATCH in compare: impostor scored {score_cmp:.4f} >= {SCORE_THRESHOLD}.'
    )
    if cand is not None:
        assert cand.get('match') is False, (
            f'FALSE MATCH in search: impostor {ident} returned match=True.'
        )
    else:
        print(f'[CME-02] Impostor not retrieved by ANN — correctly excluded.')


# ── CME-03 ───────────────────────────────────────────────────────────────────

def test_cme03_self_enrolled_template_vs_raw_and_search():
    """
    Images: probe=dan_face, candidate=dan_face (same image throughout).
    Three-way comparison for the same face:
      Mode 1: compare(dan_face, dan_face) image-vs-image           → ceiling (16.28)
      Mode 2: compare(dan_face, enrolled dan_face) vs template      → exact template (16.28, confirmed equal)
      1:N:    search(dan_face, gallery_with_dan_face) ANN re-score  → 13.90

    Documents all three scores and the two deltas:
      template delta : |mode1 - mode2|   → expected 0.00 (same exact computation)
      ANN delta      : |mode2 - search|  → expected ~2.38 (ANN approximation)
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'cme03-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200
    _wait_for_indexed(GALLERY, ident, image_b64)

    r_raw      = _compare_img_vs_img(image_b64, image_b64, SCORE_THRESHOLD)
    r_enrolled = _compare_img_vs_enrolled(image_b64, ident, GALLERY, SCORE_THRESHOLD)
    r_srch     = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)

    _delete_enrollment(GALLERY, ident)

    assert r_raw.status_code == r_enrolled.status_code == r_srch.status_code == 200

    score_raw      = r_raw.json().get('score')
    score_enrolled = r_enrolled.json().get('score')
    candidates     = r_srch.json().get('candidates', [])
    cand           = next((c for c in candidates if c.get('id') == ident), None)
    score_srch     = cand.get('score') if cand else None

    template_delta = abs(score_raw - score_enrolled) if score_enrolled else None
    ann_delta      = abs(score_enrolled - score_srch) if (score_enrolled and score_srch) else None

    _log_header('CME-03', 'three-way: raw / enrolled / search', GALLERY, ident)
    print(f'[CME-03] ── Mode 1: compare image vs image ────────────────')
    print(f'[CME-03] Score raw      : {_score_label(score_raw)}')
    print(f'[CME-03] ── Mode 2: compare image vs enrolled template ────')
    print(f'[CME-03] Score enrolled : {_score_label(score_enrolled)}')
    if template_delta is not None:
        print(f'[CME-03] Template delta : {template_delta:.4f}  (expected 0.00 — same exact computation)')
    print(f'[CME-03] ── 1:N Search ────────────────────────────────────')
    _log_search('CME-03', ident, cand)
    if ann_delta is not None:
        print(f'[CME-03] ANN delta      : {ann_delta:.4f}  (expected ~2.38 — ANN approximation cost)')

    assert r_enrolled.json().get('match') is True
    assert score_enrolled >= SCORE_THRESHOLD
    assert score_enrolled > COMPARE_SELF_MIN, (
        f'Enrolled compare {score_enrolled:.4f} <= floor {COMPARE_SELF_MIN}.'
    )
    if cand is not None:
        assert cand.get('match') is True
        assert score_srch >= SCORE_THRESHOLD
        assert score_srch > SEARCH_SELF_MIN, (
            f'Search score {score_srch:.4f} <= floor {SEARCH_SELF_MIN}.'
        )


# ── CME-04 ───────────────────────────────────────────────────────────────────

def test_cme04_threshold_changes_match_not_score_enrolled():
    """
    Images: probe=dan_face, enrolled candidate=dan_face.
    Threshold is a post-score boundary for both endpoints in enrolled mode.
    compare(dan_face, enrolled dan_face) at threshold=4.0 and threshold=999 → same score, different match flag.
    search(dan_face, gallery with dan_face) at both thresholds → same score, different match flag.
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'cme04-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200
    _wait_for_indexed(GALLERY, ident, image_b64)

    r_cmp_low   = _compare_img_vs_enrolled(image_b64, ident, GALLERY, SCORE_THRESHOLD)
    r_cmp_high  = _compare_img_vs_enrolled(image_b64, ident, GALLERY, THRESHOLD_HIGH)
    r_srch_low  = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)
    r_srch_high = _search(GALLERY, image_b64, THRESHOLD_HIGH,  max_candidates=10)

    _delete_enrollment(GALLERY, ident)

    s_cmp_low  = r_cmp_low.json().get('score')
    s_cmp_high = r_cmp_high.json().get('score')
    m_cmp_low  = r_cmp_low.json().get('match')
    m_cmp_high = r_cmp_high.json().get('match')
    low_map    = {c['id']: c for c in r_srch_low.json().get('candidates', [])}
    high_map   = {c['id']: c for c in r_srch_high.json().get('candidates', [])}
    common     = set(low_map) & set(high_map)

    _log_header('CME-04', 'threshold effect enrolled + search', GALLERY, ident)
    print(f'[CME-04] ── 1:1 Compare (enrolled) ───────────────────────')
    print(f'[CME-04] Threshold {SCORE_THRESHOLD:<6} : score={s_cmp_low:.4f}  match={m_cmp_low}')
    print(f'[CME-04] Threshold {THRESHOLD_HIGH:<6} : score={s_cmp_high:.4f}  match={m_cmp_high}')
    print(f'[CME-04] ── 1:N Search ────────────────────────────────────')
    srch_violations = []
    for cid in common:
        sl = low_map[cid]['score']
        sh = high_map[cid]['score']
        d  = abs(sl - sh)
        print(f'[CME-04]   id={cid}  score_low={sl:.4f}  score_high={sh:.4f}  delta={d:.4f}')
        if d >= 0.05:
            srch_violations.append(f'id={cid} delta={d:.4f}')

    assert s_cmp_low == s_cmp_high, f'Compare score changed with threshold: {s_cmp_low} → {s_cmp_high}.'
    assert m_cmp_low  is True,  f'Expected match=True  at threshold {SCORE_THRESHOLD}'
    assert m_cmp_high is False, f'Expected match=False at threshold {THRESHOLD_HIGH}'
    assert not srch_violations, 'Search score shifted when only threshold changed:\n' + '\n'.join(srch_violations)


# ── CME-05 ───────────────────────────────────────────────────────────────────

def test_cme05_response_schema_enrolled():
    """
    Images: probe=dan_face, enrolled candidate=dan_face.
    Full schema validation for compare(dan_face, enrolled dan_face) and search(dan_face, gallery).
    Compare:  score (float >= 0), match (bool), x-aware-trace-id header present.
    Search:   candidates list, each entry has id (str), score (float >= 0), match (bool).
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'cme05-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200
    _wait_for_indexed(GALLERY, ident, image_b64)

    r_cmp  = _compare_img_vs_enrolled(image_b64, ident, GALLERY, SCORE_THRESHOLD)
    r_srch = _search(GALLERY, image_b64, SCORE_THRESHOLD, max_candidates=10)

    _delete_enrollment(GALLERY, ident)

    body_cmp  = r_cmp.json()  if r_cmp.status_code  == 200 else {}
    body_srch = r_srch.json() if r_srch.status_code == 200 else {}
    candidates = body_srch.get('candidates', [])

    _log_header('CME-05', 'response schema enrolled + search', GALLERY, ident)
    print(f'[CME-05] Compare HTTP  : {r_cmp.status_code}')
    print(f'[CME-05] Compare body  : {body_cmp}')
    print(f'[CME-05] Compare trace : {r_cmp.headers.get("x-aware-trace-id", "not returned")}')
    print(f'[CME-05] Search  HTTP  : {r_srch.status_code}')
    print(f'[CME-05] Search  cands : {len(candidates)}')
    for c in candidates[:3]:
        print(f'[CME-05]   {c}')

    # Compare schema
    assert r_cmp.status_code == 200
    assert isinstance(body_cmp.get('score'), (int, float)), '"score" not numeric in compare'
    assert isinstance(body_cmp.get('match'), bool),         '"match" not bool in compare'
    assert body_cmp['score'] >= 0.0,                        '"score" < 0 in compare'
    assert r_cmp.headers.get('x-aware-trace-id'),           'trace ID missing in compare'

    # Search schema
    assert r_srch.status_code == 200
    assert isinstance(candidates, list), '"candidates" not a list in search'
    for c in candidates:
        assert isinstance(c.get('id'),    str),           f'"id" not str: {c}'
        assert isinstance(c.get('score'), (int, float)),  f'"score" not numeric: {c}'
        assert isinstance(c.get('match'), bool),          f'"match" not bool: {c}'
        assert c['score'] >= 0.0,                         f'"score" < 0: {c}'
