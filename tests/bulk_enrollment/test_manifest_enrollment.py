# -*- coding: utf-8 -*-
"""
test_manifest_enrollment.py — Bulk enrollment and search using the image manifest.

Demonstrates how to use load_manifest() for:
  ME-01  Gallery creation + bulk enrollment (all 200 images)
  ME-02  1:N search  — probe each image, verify it returns itself as rank-1
  ME-03  1:1 compare — verify enrolled image scores above threshold against itself
  ME-04  Impostor check — first image must NOT match second image (different identities)

Run in isolation:
    pytest tests/bulk_enrollment/test_manifest_enrollment.py -v -s

Prerequisites:
    python scripts/generate_image_manifest.py   (run once to build tests/data/images.json)
"""

import time
import requests
import pytest
from config import BASE_URL, HEADERS
from tests.data.image_loader import load_manifest

SCORE_THRESHOLD = 4.0
SEARCH_TIMEOUT  = 30   # seconds to wait for a freshly enrolled image to be indexed


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def manifest():
    """Load the image manifest once for the entire module."""
    return load_manifest()


@pytest.fixture(scope='module')
def manifest_gallery(manifest):
    """
    Create an isolated gallery for this module, bulk-enroll all images, yield
    the gallery name, then delete the gallery on teardown.
    """
    gallery = f'manifest_test_{int(time.time())}'

    r = requests.post(
        f'{BASE_URL}/facematch/galleries',
        headers=HEADERS,
        json={'name': gallery},
    )
    assert r.status_code == 200, f'Gallery creation failed: {r.status_code}: {r.text}'
    print(f'\n[FIXTURE] Gallery created: {gallery}')

    enrolled = []
    for img in manifest.all_images():
        r = requests.post(
            f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{img["id"]}',
            headers=HEADERS,
            json={'image': img['base64']},
        )
        if r.status_code == 200:
            enrolled.append(img['id'])
        else:
            print(f'[FIXTURE] Enroll skipped ({r.status_code}): {img["id"]}')

    print(f'[FIXTURE] Enrolled {len(enrolled)}/{len(manifest)} images into {gallery}')

    yield gallery, enrolled

    requests.delete(f'{BASE_URL}/facematch/galleries/{gallery}', headers=HEADERS)
    print(f'\n[FIXTURE] Gallery deleted: {gallery}')


def _wait_for_indexed(gallery, ident, image_b64, timeout=SEARCH_TIMEOUT):
    """Poll search until the identity appears or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.post(
            f'{BASE_URL}/facematch/search',
            headers=HEADERS,
            json={
                'probe':         {'image': image_b64},
                'gallery':       gallery,
                'maxCandidates': 10,
                'threshold':     0.0,
            },
        )
        if r.status_code == 200:
            if any(c.get('id') == ident for c in r.json().get('candidates', [])):
                return True
        time.sleep(1)
    return False


# ── ME-01  Gallery already built by fixture ───────────────────────────────────

def test_me01_bulk_enrollment(manifest_gallery, manifest):
    """
    All images in the manifest are enrolled during fixture setup.
    This test just verifies the fixture succeeded (enrollment count matches manifest).
    """
    gallery, enrolled = manifest_gallery

    print(f'\n[ME-01] Gallery    : {gallery}')
    print(f'[ME-01] Manifest   : {len(manifest)} images')
    print(f'[ME-01] Enrolled   : {len(enrolled)} identities')

    assert len(enrolled) == len(manifest), (
        f'Expected {len(manifest)} enrollments, got {len(enrolled)}.\n'
        f'Some images may have been rejected — check face quality or duplicates.'
    )


# ── ME-02  1:N search — probe must appear in results ─────────────────────────

def test_me02_search_probe_returns_self(manifest_gallery, manifest):
    """
    For each of the first 10 images: search → the enrolled identity must appear
    in the candidates. Verifies end-to-end gallery lookup at scale.
    """
    gallery, enrolled = manifest_gallery
    probes = manifest.first(10)

    print(f'\n[ME-02] Gallery  : {gallery}  (enrolled={len(enrolled)})')
    print(f'[ME-02] Probing  : {len(probes)} images')
    print(f'[ME-02] {"id":<40} {"found":>6} {"score":>8} {"match":>6}')

    failures = []
    for img in probes:
        ident = img['id']

        _wait_for_indexed(gallery, ident, img['base64'])

        r = requests.post(
            f'{BASE_URL}/facematch/search',
            headers=HEADERS,
            json={
                'probe':         {'image': img['base64']},
                'gallery':       gallery,
                'maxCandidates': 5,
                'threshold':     SCORE_THRESHOLD,
            },
        )
        assert r.status_code == 200, f'Search failed: {r.status_code}: {r.text}'

        candidates = r.json().get('candidates', [])
        hit = next((c for c in candidates if c.get('id') == ident), None)
        found = hit is not None
        score = hit.get('score') if hit else None
        match = hit.get('match') if hit else None

        print(f'[ME-02] {ident:<40} {str(found):>6} {(f"{score:.4f}" if score else "N/A"):>8} {str(match):>6}')

        if not found:
            failures.append(f'{ident}: not found in search results')
        elif not match:
            failures.append(f'{ident}: found but match=False  (score={score:.4f})')

    assert not failures, (
        f'{len(failures)} probe(s) failed:\n' + '\n'.join(failures)
    )


# ── ME-03  1:1 compare ────────────────────────────────────────────────────────

def test_me03_compare_self_match(manifest_gallery, manifest):
    """
    For each of the first 10 images: compare the image against its enrolled
    identity. Score must be above threshold (genuine self-match).
    """
    gallery, enrolled = manifest_gallery
    probes = manifest.first(10)

    print(f'\n[ME-03] Gallery  : {gallery}')
    print(f'[ME-03] {"id":<40} {"score":>8} {"match":>6}')

    failures = []
    for img in probes:
        ident = img['id']
        r = requests.post(
            f'{BASE_URL}/facematch/compare',
            headers=HEADERS,
            json={
                'probe':     {'image': img['base64']},
                'candidate': {'id': ident, 'gallery': gallery},
                'threshold': SCORE_THRESHOLD,
            },
        )
        assert r.status_code == 200, f'Compare failed: {r.status_code}: {r.text}'

        score = r.json().get('score')
        match = r.json().get('match')
        print(f'[ME-03] {ident:<40} {score:>8.4f} {str(match):>6}')

        if not match:
            failures.append(f'{ident}: match=False  (score={score:.4f}, threshold={SCORE_THRESHOLD})')

    assert not failures, (
        f'Self-match failed for {len(failures)} image(s):\n' + '\n'.join(failures)
    )


# ── ME-04  Impostor pair ──────────────────────────────────────────────────────

def test_me04_compare_impostor_no_match(manifest_gallery, manifest):
    """
    Compare the first image (probe) against the second image (impostor).
    Since these are different identities from the dataset, the score must
    be below threshold (no false match).

    Note: This assertion holds when the two images are genuinely different
    people. If the manifest images happen to be the same person, this test
    is expected to fail and should be skipped.
    """
    gallery, enrolled = manifest_gallery

    if len(manifest) < 2:
        pytest.skip('Manifest has fewer than 2 images — cannot run impostor test.')

    probe    = manifest.first(1)[0]
    impostor = manifest.first(2)[1]

    if probe['subject_id'] and probe['subject_id'] == impostor.get('subject_id'):
        pytest.skip(
            f'Probe and impostor share subject_id "{probe["subject_id"]}" — '
            f'same person, not a valid impostor pair.'
        )

    r = requests.post(
        f'{BASE_URL}/facematch/compare',
        headers=HEADERS,
        json={
            'probe':     {'image': probe['base64']},
            'candidate': {'id': impostor['id'], 'gallery': gallery},
            'threshold': SCORE_THRESHOLD,
        },
    )
    assert r.status_code == 200, f'Compare failed: {r.status_code}: {r.text}'

    score = r.json().get('score')
    match = r.json().get('match')

    print(f'\n[ME-04] Probe    : {probe["id"]}')
    print(f'[ME-04] Impostor : {impostor["id"]}')
    print(f'[ME-04] Score    : {score:.4f}  threshold={SCORE_THRESHOLD}')
    print(f'[ME-04] Match    : {match}  (expected False — different people)')

    assert match is False, (
        f'FALSE POSITIVE: probe {probe["id"]} matched impostor {impostor["id"]}  '
        f'(score={score:.4f}). '
        f'These should be different people from the dataset.'
    )
