# -*- coding: utf-8 -*-
"""
test_response_schema.py — Full response-body schema validation for every endpoint.

Each test makes a real request and validates the body against a JSON Schema
defined in tests/schemas.py. A failure means a field is missing, has the wrong
type, or is out of range — not just that the status code was wrong.

Tests:
  SCHEMA-01  GET  /facematch/health
  SCHEMA-02  GET  /facematch/version
  SCHEMA-03  POST /facematch/compare  (image vs image)
  SCHEMA-04  POST /facematch/compare  (image vs enrolled)  ← checks candidateId + candidateGallery
  SCHEMA-05  POST /facematch/search
  SCHEMA-06  POST /facematch/galleries/{g}/enrollments/{id}

SCHEMA-04 is currently expected to FAIL: the live service does not return
candidateId or candidateGallery in compare responses, so audit logs cannot
capture which enrolled template was compared. The test is marked xfail so
the suite stays green while the gap is tracked. Remove the xfail marker once
the server is fixed.
"""

import time
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES
from tests.schemas import (
    assert_schema,
    HEALTH_SCHEMA,
    VERSION_SCHEMA,
    COMPARE_IMAGE_SCHEMA,
    COMPARE_ENROLLED_SCHEMA,
    SEARCH_SCHEMA,
    ENROLL_SCHEMA,
)

GALLERY   = 'today2'
IMAGE_KEY = 'dan_face'


def _image():
    img = IMAGES.get(IMAGE_KEY)
    if not img:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config.')
    return img


# ── SCHEMA-01  Health ─────────────────────────────────────────────────────────

def test_schema01_health():
    """
    GET /facematch/health must return all six system-status fields.
    Fields: status, algorithm, vectorDim, sdk, milvus, database.
    No extra fields allowed (additionalProperties: false).
    """
    r = requests.get(f'{BASE_URL}/facematch/health', headers=HEADERS)
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body = r.json()
    print(f'\n[SCHEMA-01] {body}')
    assert_schema(body, HEALTH_SCHEMA, label='GET /facematch/health')


# ── SCHEMA-02  Version ────────────────────────────────────────────────────────

def test_schema02_version():
    """
    GET /facematch/version must return {"version": "<string>"}.
    """
    r = requests.get(f'{BASE_URL}/facematch/version', headers=HEADERS)
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body = r.json()
    print(f'\n[SCHEMA-02] {body}')
    assert_schema(body, VERSION_SCHEMA, label='GET /facematch/version')


# ── SCHEMA-03  Compare — image vs image ──────────────────────────────────────

def test_schema03_compare_image_vs_image():
    """
    POST /facematch/compare with two anonymous images.
    Required: score (number >= 0), match (boolean).
    No candidateId/candidateGallery expected — probe and candidate are both inline images.
    """
    image_b64 = _image()
    r = requests.post(
        f'{BASE_URL}/facematch/compare',
        headers=HEADERS,
        json={
            'probe':     {'image': image_b64},
            'candidate': {'image': image_b64},
            'threshold': 4.0,
        },
    )
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body = r.json()
    print(f'\n[SCHEMA-03] score={body.get("score")}  match={body.get("match")}')
    assert_schema(body, COMPARE_IMAGE_SCHEMA, label='POST /facematch/compare (image vs image)')


# ── SCHEMA-04  Compare — image vs enrolled ────────────────────────────────────

@pytest.mark.xfail(
    strict=True,
    reason=(
        'POST /facematch/compare (image vs enrolled) does not return candidateId or '
        'candidateGallery. Audit logs cannot record which enrolled template was '
        'compared. Remove xfail when the server echoes these fields back.'
    ),
)
def test_schema04_compare_image_vs_enrolled():
    """
    POST /facematch/compare with an enrolled candidate (id + gallery).
    Expected: score, match, candidateId, candidateGallery.

    CURRENTLY FAILING: response only contains {score, match, timing}.
    candidateId and candidateGallery are absent — audit logs cannot capture
    the full transaction context for Compare requests run via Benchmark.
    """
    image_b64 = _image()
    ident     = f'schema04_{uuid.uuid4().hex[:8]}'

    requests.post(f'{BASE_URL}/facematch/galleries', headers=HEADERS, json={'name': GALLERY})
    enroll_r = requests.post(
        f'{BASE_URL}/facematch/galleries/{GALLERY}/enrollments/{ident}',
        headers=HEADERS,
        json={'image': image_b64},
    )
    assert enroll_r.status_code == 200, f'Enroll failed: {enroll_r.status_code}: {enroll_r.text}'

    try:
        time.sleep(2)  # allow index propagation
        r = requests.post(
            f'{BASE_URL}/facematch/compare',
            headers=HEADERS,
            json={
                'probe':     {'image': image_b64},
                'candidate': {'id': ident, 'gallery': GALLERY},
                'threshold': 4.0,
            },
        )
        assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

        body = r.json()
        print(f'\n[SCHEMA-04] Response: {body}')
        print(f'[SCHEMA-04] Missing fields audit check:')
        print(f'[SCHEMA-04]   candidateId      : {"PRESENT" if "candidateId" in body else "MISSING ← BUG"}')
        print(f'[SCHEMA-04]   candidateGallery : {"PRESENT" if "candidateGallery" in body else "MISSING ← BUG"}')

        assert_schema(body, COMPARE_ENROLLED_SCHEMA, label='POST /facematch/compare (image vs enrolled)')

    finally:
        requests.delete(
            f'{BASE_URL}/facematch/galleries/{GALLERY}/enrollments/{ident}',
            headers=HEADERS,
        )


# ── SCHEMA-05  Search ─────────────────────────────────────────────────────────

def test_schema05_search():
    """
    POST /facematch/search must return candidates array where every item
    has id (string), score (number >= 0), and match (boolean).
    """
    image_b64 = _image()
    r = requests.post(
        f'{BASE_URL}/facematch/search',
        headers=HEADERS,
        json={
            'probe':         {'image': image_b64},
            'gallery':       GALLERY,
            'maxCandidates': 5,
            'threshold':     4.0,
        },
    )
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body       = r.json()
    candidates = body.get('candidates', [])
    print(f'\n[SCHEMA-05] candidates={len(candidates)}')
    for c in candidates:
        print(f'[SCHEMA-05]   id={c.get("id")}  score={c.get("score")}  match={c.get("match")}')

    assert_schema(body, SEARCH_SCHEMA, label='POST /facematch/search')


# ── SCHEMA-06  Enroll ─────────────────────────────────────────────────────────

def test_schema06_enroll():
    """
    POST /facematch/galleries/{g}/enrollments/{id} must return
    success (boolean), identifier (string), gallery (string).
    Enrollment is deleted after validation.
    """
    image_b64 = _image()
    ident     = f'schema06_{uuid.uuid4().hex[:8]}'

    requests.post(f'{BASE_URL}/facematch/galleries', headers=HEADERS, json={'name': GALLERY})

    r = requests.post(
        f'{BASE_URL}/facematch/galleries/{GALLERY}/enrollments/{ident}',
        headers=HEADERS,
        json={'image': image_b64},
    )
    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    body = r.json()
    print(f'\n[SCHEMA-06] {body}')

    try:
        assert_schema(body, ENROLL_SCHEMA, label='POST /facematch/galleries/{g}/enrollments/{id}')
        assert body['identifier'] == ident,  f'identifier echoed incorrectly: {body["identifier"]}'
        assert body['gallery']    == GALLERY, f'gallery echoed incorrectly: {body["gallery"]}'
        assert body['success']    is True,    f'success should be True: {body["success"]}'
    finally:
        requests.delete(
            f'{BASE_URL}/facematch/galleries/{GALLERY}/enrollments/{ident}',
            headers=HEADERS,
        )
