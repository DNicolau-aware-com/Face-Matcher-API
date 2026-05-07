# -*- coding: utf-8 -*-
"""
test_score_thresholds.py — Threshold boundary validation across all standard score levels

ROC F200 score scale (S = -log10(FMR)):

  S=1  FMR = 1/10        =  10.0000%   (very weak)
  S=2  FMR = 1/100       =   1.0000%
  S=3  FMR = 1/1,000     =   0.1000%
  S=4  FMR = 1/10,000    =   0.0100%   ⭐ recommended deployment threshold
  S=5  FMR = 1/100,000   =   0.0010%   (very strict)

Key assertions tested here:
  1. Score is computed independently of threshold — same score at S=1 and S=5.
  2. match flag correctly reflects score >= threshold at every boundary.
  3. Both compare and search agree on the match decision at each threshold level.

Images used:
  Genuine pair : probe=dan_face vs candidate=dan_face  (observed score ~16.28 compare / ~13.90 search)
                 → match=True  at all 5 threshold levels (score >> S=5)
  Impostor pair: probe=dan_face vs candidate=john_face (observed score ~0.39)
                 → match=False at all 5 threshold levels (score < S=1)

Gallery strategy:
  All tests enroll into today2 with a unique UUID-based ID.
  Enrollment is deleted after each test. Gallery is never deleted.

Tests:
  THR-C01  Compare genuine (dan_face vs dan_face) — score constant, match=True across S=1..5
  THR-C02  Compare impostor (dan_face vs john_face) — score constant, match=False across S=1..5
  THR-S01  Search genuine (dan_face in gallery) — score constant, match=True across S=1..5
  THR-S02  Search impostor (dan_face, gallery with john_face) — match=False across S=1..5
  THR-X01  Cross-endpoint: both compare and search agree at every threshold level (genuine)
"""

import time
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

# ── Configuration ─────────────────────────────────────────────────────────────
GALLERY          = 'today2'   # genuine enrollments
IMPOSTOR_GALLERY = 'today01'  # impostor enrollments
PROBE_KEY    = 'dan_face'
IMPOSTOR_KEY = 'john_face'  # genuinely different person — scores low against dan_face probe

# Standard score thresholds from the FMR table
THRESHOLDS = [
    (1, 1 / 10,       '10.0000%',  'very weak'),
    (2, 1 / 100,      ' 1.0000%',  ''),
    (3, 1 / 1_000,    ' 0.1000%',  ''),
    (4, 1 / 10_000,   ' 0.0100%',  'recommended'),
    (5, 1 / 100_000,  ' 0.0010%',  'very strict'),
]

# Observed baselines (2026-04-29, ROC F200, Milvus ANN)
GENUINE_COMPARE_SCORE  = 16.28   # compare(dan_face, dan_face)
GENUINE_SEARCH_SCORE   = 13.90   # search(dan_face, gallery with dan_face)
IMPOSTOR_COMPARE_SCORE =  0.39   # compare(dan_face, john_face)
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

def _compare_img_vs_img(probe_b64, candidate_b64, threshold):
    return requests.post(
        f'{BASE_URL}/facematch/compare',
        headers=HEADERS,
        json={
            'probe':     {'image': probe_b64},
            'candidate': {'image': candidate_b64},
            'threshold': threshold,
        },
    )


def _search(gallery, image_b64, threshold, max_candidates=50):
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


def _fmr_label(s):
    fmr = 10 ** (-s) * 100
    return f'{fmr:.4f}%'


def _print_threshold_table(tag, rows):
    """rows: list of (s, fmr_pct, label, score, match)"""
    print(f'\n[{tag}] S  │ FMR         │ Label        │ Score    │ Match')
    print(f'[{tag}] ───┼─────────────┼──────────────┼──────────┼──────')
    for s, fmr_pct, label, score, match in rows:
        score_str = f'{score:.4f}' if score is not None else 'N/A  '
        match_str = str(match)
        print(f'[{tag}] {s}  │ {fmr_pct:<11} │ {label:<12} │ {score_str} │ {match_str}')


# ══════════════════════════════════════════════════════════════════════════════
# THR-C01 — Compare genuine across all threshold levels
# ══════════════════════════════════════════════════════════════════════════════

def test_thr_c01_compare_genuine_all_thresholds():
    """
    Images: probe=dan_face, candidate=dan_face (same image, same person).
    Runs compare(dan_face, dan_face) at S=1, 2, 3, 4, 5.
    Asserts: score is identical at all threshold levels (threshold does not affect scoring).
    Asserts: match=True at all levels — observed score ~16.28 exceeds even the strictest S=5.
    """
    probe_b64 = IMAGES.get(PROBE_KEY)
    if not probe_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    scores  = []
    matches = []
    rows    = []

    for s, fmr, label, desc in THRESHOLDS:
        r = _compare_img_vs_img(probe_b64, probe_b64, threshold=s)
        assert r.status_code == 200, f'Compare failed at S={s}: {r.status_code} {r.text}'
        score = r.json().get('score')
        match = r.json().get('match')
        scores.append(score)
        matches.append(match)
        rows.append((s, f'{fmr * 100:.4f}%', desc or '—', score, match))

    _print_threshold_table('THR-C01', rows)
    print(f'[THR-C01] Baseline compare score: {GENUINE_COMPARE_SCORE}')

    # Score must be constant across all thresholds
    assert len(set(scores)) == 1, (
        f'Compare score changed across thresholds — scores per level: '
        + ', '.join(f'S={s}: {sc:.4f}' for (s, *_), sc in zip(THRESHOLDS, scores))
    )

    # match=True expected at all levels (score ~16.28 >> S=5)
    for (s, fmr, label, desc), match in zip(THRESHOLDS, matches):
        assert match is True, (
            f'Expected match=True at S={s} (FMR={fmr * 100:.4f}%) for genuine pair. '
            f'Score: {scores[0]:.4f}  Threshold: {s}'
        )


# ══════════════════════════════════════════════════════════════════════════════
# THR-C02 — Compare impostor across all threshold levels
# ══════════════════════════════════════════════════════════════════════════════

def test_thr_c02_compare_impostor_all_thresholds():
    """
    Images: probe=dan_face, candidate=john_face (different people).
    Runs compare(dan_face, john_face) at S=1, 2, 3, 4, 5.
    Asserts: score is identical at all threshold levels.
    Asserts: match=False at all levels — observed score ~0.39 is below even the weakest S=1.
    """
    probe_b64    = IMAGES.get(PROBE_KEY)
    impostor_b64 = IMAGES.get(IMPOSTOR_KEY)
    if not probe_b64 or not impostor_b64:
        pytest.fail('Probe or impostor image key not found in config.')

    scores  = []
    matches = []
    rows    = []

    for s, fmr, label, desc in THRESHOLDS:
        r = _compare_img_vs_img(probe_b64, impostor_b64, threshold=s)
        assert r.status_code == 200, f'Compare failed at S={s}: {r.status_code} {r.text}'
        score = r.json().get('score')
        match = r.json().get('match')
        scores.append(score)
        matches.append(match)
        rows.append((s, f'{fmr * 100:.4f}%', desc or '—', score, match))

    _print_threshold_table('THR-C02', rows)
    print(f'[THR-C02] Baseline impostor score: {IMPOSTOR_COMPARE_SCORE}')

    # Score must be constant across all thresholds
    assert len(set(scores)) == 1, (
        f'Compare score changed across thresholds — scores per level: '
        + ', '.join(f'S={s}: {sc:.4f}' for (s, *_), sc in zip(THRESHOLDS, scores))
    )

    # match=False expected at all levels (score ~0.39 < S=1)
    for (s, fmr, label, desc), match in zip(THRESHOLDS, matches):
        assert match is False, (
            f'FALSE MATCH at S={s} (FMR={fmr * 100:.4f}%) for impostor pair. '
            f'Score: {scores[0]:.4f}  Threshold: {s}'
        )


# ══════════════════════════════════════════════════════════════════════════════
# THR-S01 — Search genuine across all threshold levels
# ══════════════════════════════════════════════════════════════════════════════

def test_thr_s01_search_genuine_all_thresholds():
    """
    Images: probe=dan_face enrolled in today2, searched with probe=dan_face.
    Runs search(dan_face, today2) at S=1, 2, 3, 4, 5.
    Asserts: score is stable across all threshold levels (delta < 0.05 allowed for ANN).
    Asserts: match=True at all levels — observed ANN re-score ~13.90 exceeds S=5.
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'thr-s01-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200, 'Enrollment failed'
    _wait_for_indexed(GALLERY, ident, image_b64)

    scores  = []
    matches = []
    rows    = []

    try:
        for s, fmr, label, desc in THRESHOLDS:
            r = _search(GALLERY, image_b64, threshold=s, max_candidates=50)
            assert r.status_code == 200, f'Search failed at S={s}: {r.status_code} {r.text}'
            cand  = next((c for c in r.json().get('candidates', []) if c.get('id') == ident), None)
            score = cand.get('score') if cand else None
            match = cand.get('match') if cand else None
            scores.append(score)
            matches.append(match)
            rows.append((s, f'{fmr * 100:.4f}%', desc or '—', score, match))
    finally:
        _delete_enrollment(GALLERY, ident)

    _print_threshold_table('THR-S01', rows)
    print(f'[THR-S01] Baseline search score: {GENUINE_SEARCH_SCORE}')

    valid_scores = [sc for sc in scores if sc is not None]
    assert valid_scores, f'Enrolled identity {ident} not found in search results at any threshold.'

    # Score must be stable across thresholds (ANN is deterministic; allow tiny float variance)
    score_min = min(valid_scores)
    score_max = max(valid_scores)
    assert (score_max - score_min) < 0.05, (
        f'Search score drifted across threshold levels: min={score_min:.4f}  max={score_max:.4f}.'
    )

    # match=True expected at all levels (score ~13.90 >> S=5)
    for (s, fmr, label, desc), score, match in zip(THRESHOLDS, scores, matches):
        assert score is not None, (
            f'Identity {ident} missing from search results at S={s}. '
            f'ANN may have filtered it out when threshold was raised.'
        )
        assert match is True, (
            f'Expected match=True at S={s} (FMR={fmr * 100:.4f}%) for genuine pair. '
            f'Score: {score:.4f}  Threshold: {s}'
        )


# ══════════════════════════════════════════════════════════════════════════════
# THR-S02 — Search impostor across all threshold levels
# ══════════════════════════════════════════════════════════════════════════════

def test_thr_s02_search_impostor_all_thresholds():
    """
    Images: enrolled=john_face in today01, probe=dan_face.
    Runs search(dan_face, today01 with enrolled john_face) at S=1, 2, 3, 4, 5.
    Asserts: impostor either absent from results or match=False at every threshold level.
    """
    probe_b64    = IMAGES.get(PROBE_KEY)
    impostor_b64 = IMAGES.get(IMPOSTOR_KEY)
    if not probe_b64 or not impostor_b64:
        pytest.fail('Probe or impostor image key not found in config.')

    ident = f'thr-s02-{uuid.uuid4().hex[:8]}'
    assert _enroll(IMPOSTOR_GALLERY, ident, impostor_b64).status_code == 200, 'Enrollment failed'

    rows = []
    try:
        _wait_for_indexed(IMPOSTOR_GALLERY, ident, impostor_b64)

        for s, fmr, label, desc in THRESHOLDS:
            r = _search(IMPOSTOR_GALLERY, probe_b64, threshold=s, max_candidates=50)
            assert r.status_code == 200, f'Search failed at S={s}: {r.status_code} {r.text}'
            cand  = next((c for c in r.json().get('candidates', []) if c.get('id') == ident), None)
            score = cand.get('score') if cand else None
            match = cand.get('match') if cand else None
            rows.append((s, f'{fmr * 100:.4f}%', desc or '—', score, match))

            if cand is not None:
                assert match is False, (
                    f'FALSE MATCH in search at S={s} (FMR={fmr * 100:.4f}%): '
                    f'impostor {ident} returned match=True. Score: {score:.4f}'
                )
    finally:
        _delete_enrollment(IMPOSTOR_GALLERY, ident)

    _print_threshold_table('THR-S02', rows)
    print(f'[THR-S02] Baseline impostor compare score: {IMPOSTOR_COMPARE_SCORE} '
          f'(score << S=1, ANN may not retrieve at all)')


# ══════════════════════════════════════════════════════════════════════════════
# THR-X01 — Cross-endpoint agreement at every threshold level (genuine)
# ══════════════════════════════════════════════════════════════════════════════

def test_thr_x01_cross_endpoint_agreement_all_thresholds():
    """
    Images: probe=dan_face, enrolled candidate=dan_face in today2.
    Runs both compare(dan_face, dan_face) and search(dan_face, today2) at S=1, 2, 3, 4, 5.
    Asserts: both endpoints return match=True at every threshold level.
    Documents the cross-endpoint score delta (compare ~16.28 vs search ~13.90) at each level.
    This confirms the ANN approximation gap is consistent regardless of the threshold used.
    """
    image_b64 = IMAGES.get(PROBE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{PROBE_KEY}" not found in config.')

    ident = f'thr-x01-{uuid.uuid4().hex[:8]}'
    assert _enroll(GALLERY, ident, image_b64).status_code == 200, 'Enrollment failed'
    _wait_for_indexed(GALLERY, ident, image_b64)

    print(f'\n[THR-X01] Enrolled ID: {ident}')
    print(f'[THR-X01] S  │ Compare score │ Search score │ Delta  │ Both match?')
    print(f'[THR-X01] ───┼───────────────┼──────────────┼────────┼────────────')

    failures = []

    try:
        for s, fmr, label, desc in THRESHOLDS:
            r_cmp  = _compare_img_vs_img(image_b64, image_b64, threshold=s)
            r_srch = _search(GALLERY, image_b64, threshold=s, max_candidates=50)

            assert r_cmp.status_code  == 200, f'Compare failed at S={s}'
            assert r_srch.status_code == 200, f'Search failed at S={s}'

            score_cmp  = r_cmp.json().get('score')
            match_cmp  = r_cmp.json().get('match')
            candidates = r_srch.json().get('candidates', [])
            cand       = next((c for c in candidates if c.get('id') == ident), None)
            score_srch = cand.get('score') if cand else None
            match_srch = cand.get('match') if cand else None

            delta     = abs(score_cmp - score_srch) if (score_cmp and score_srch) else None
            both_ok   = (match_cmp is True) and (match_srch is True)
            delta_str = f'{delta:.4f}' if delta is not None else 'N/A   '
            cmp_str   = f'{score_cmp:.4f}' if score_cmp is not None else 'N/A   '
            srch_str  = f'{score_srch:.4f}' if score_srch is not None else 'N/A   '

            print(f'[THR-X01] {s}  │ {cmp_str:<13} │ {srch_str:<12} │ {delta_str} │ {both_ok}')

            if match_cmp is not True:
                failures.append(f'S={s}: compare match=False (score={score_cmp})')
            if match_srch is not True:
                failures.append(f'S={s}: search match=False or identity missing (score={score_srch})')
    finally:
        _delete_enrollment(GALLERY, ident)

    assert not failures, (
        'Cross-endpoint agreement failed at one or more threshold levels:\n'
        + '\n'.join(failures)
    )
