# -*- coding: utf-8 -*-
"""
test_delete_enrollments.py — Enroll 20 images then delete them all.

Flow:
  DEL-01  Create isolated gallery  del_20_<timestamp>
  DEL-02  Submit async job         POST /facematch/admin/jobs  (20 items)
  DEL-03  Poll job until complete  GET  /facematch/admin/jobs/{jobId}
  DEL-04  Delete all 20 enrollments one by one
          DELETE /facematch/galleries/{gallery}/enrollments/{id}  → 204 each
  DEL-05  Verify gallery is empty — search returns none of the deleted IDs
          Gallery itself is deleted at the end of this step.
"""

import time
import requests
import pytest
from config import BASE_URL, HEADERS
from tests.data.image_loader import load_manifest

GALLERY_PREFIX    = 'del_20'
ENROLL_COUNT      = 20
JOB_POLL_TIMEOUT  = 120   # seconds — 20 images should complete well within 2 min
JOB_POLL_INTERVAL = 5


# ── Shared state ──────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def state():
    return {}


@pytest.fixture(scope='module', autouse=True)
def manifest_images():
    """Load the first 20 images from the manifest once for the module."""
    m = load_manifest()
    images = m.first(ENROLL_COUNT)
    assert len(images) == ENROLL_COUNT, (
        f'Manifest has only {len(images)} images — need {ENROLL_COUNT}. '
        f'Re-run: python scripts/generate_image_manifest.py --count {ENROLL_COUNT}'
    )
    return images


# ── DEL-01  Create gallery ────────────────────────────────────────────────────

def test_del01_create_gallery(state):
    gallery = f'{GALLERY_PREFIX}_{int(time.time())}'
    url     = f'{BASE_URL}/facematch/galleries'

    r = requests.post(url, headers=HEADERS, json={'name': gallery})

    print(f'\n[DEL-01] URL     : {url}')
    print(f'[DEL-01] Gallery : {gallery}')
    print(f'[DEL-01] Status  : {r.status_code}')
    print(f'[DEL-01] Response: {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'
    state['gallery'] = gallery


# ── DEL-02  Submit enrollment job ─────────────────────────────────────────────

def test_del02_submit_job(state, manifest_images):
    gallery = state.get('gallery')
    assert gallery, 'DEL-01 must pass first (gallery not set)'

    items = [
        {'identifier': img['id'], 'image': img['base64']}
        for img in manifest_images
    ]

    url = f'{BASE_URL}/facematch/admin/jobs'
    r   = requests.post(url, headers=HEADERS, json={
        'items':   items,
        'gallery': gallery,
    })

    print(f'\n[DEL-02] URL     : {url}')
    print(f'[DEL-02] Gallery : {gallery}')
    print(f'[DEL-02] Items   : {len(items)}')
    print(f'[DEL-02] Status  : {r.status_code}')
    print(f'[DEL-02] Response: {r.text}')

    assert r.status_code == 200, f'Expected 200, got {r.status_code}: {r.text}'

    job_id = r.json().get('jobId')
    assert job_id, f'Expected jobId in response: {r.text}'

    state['job_id']       = job_id
    state['enrolled_ids'] = [img['id'] for img in manifest_images]
    state['probe_b64']    = manifest_images[0]['base64']
    print(f'[DEL-02] Job submitted: {job_id}  ({len(items)} items)')


# ── DEL-03  Poll until complete ───────────────────────────────────────────────

def test_del03_poll_job(state):
    job_id = state.get('job_id')
    assert job_id, 'DEL-02 must pass first (job_id not set)'

    url      = f'{BASE_URL}/facematch/admin/jobs/{job_id}'
    deadline = time.time() + JOB_POLL_TIMEOUT
    last_pct = -1

    print(f'\n[DEL-03] Polling job {job_id} (timeout={JOB_POLL_TIMEOUT}s)')

    while time.time() < deadline:
        r = requests.get(url, headers=HEADERS)
        assert r.status_code == 200, f'Poll failed: {r.status_code}: {r.text}'

        body   = r.json()
        status = body.get('status', '').lower()
        pct    = body.get('progressPercent', 0)

        if pct != last_pct:
            print(f'[DEL-03]   {pct:>3}%  status={status}')
            last_pct = pct

        if status in ('completed', 'complete', 'done', 'finished'):
            print(f'[DEL-03] Job completed: {body}')
            return

        if status in ('failed', 'error', 'cancelled'):
            pytest.fail(f'Job ended in terminal state "{status}": {body}')

        time.sleep(JOB_POLL_INTERVAL)

    pytest.fail(
        f'Job {job_id} did not complete within {JOB_POLL_TIMEOUT}s. '
        f'Last status: {body}'
    )


# ── DEL-04  Delete all enrollments ───────────────────────────────────────────

def test_del04_delete_all_enrollments(state):
    gallery      = state.get('gallery')
    enrolled_ids = state.get('enrolled_ids', [])
    assert gallery,      'DEL-01 must pass first (gallery not set)'
    assert enrolled_ids, 'DEL-02 must pass first (enrolled_ids not set)'

    print(f'\n[DEL-04] Gallery             : {gallery}')
    print(f'[DEL-04] Enrollments to delete: {len(enrolled_ids)}')
    print(f'[DEL-04] {"identifier":<40} {"status":>6}')
    print(f'[DEL-04] {"-"*40} {"------":>6}')

    failed = []
    for ident in enrolled_ids:
        url = f'{BASE_URL}/facematch/galleries/{gallery}/enrollments/{ident}'
        r   = requests.delete(url, headers=HEADERS)
        if r.status_code == 204:
            print(f'[DEL-04]   {ident:<40} 204 OK')
        else:
            failed.append(f'{ident}: expected 204, got {r.status_code} ({r.text})')
            print(f'[DEL-04]   {ident:<40} {r.status_code} FAIL')

    assert not failed, (
        f'{len(failed)}/{len(enrolled_ids)} deletion(s) failed:\n'
        + '\n'.join(failed)
    )
    print(f'\n[DEL-04] All {len(enrolled_ids)} enrollments deleted successfully.')


# ── DEL-05  Verify gallery is empty ──────────────────────────────────────────

def test_del05_verify_gallery_empty(state):
    gallery      = state.get('gallery')
    enrolled_ids = state.get('enrolled_ids', [])
    probe_b64    = state.get('probe_b64')
    assert gallery,   'DEL-01 must pass first (gallery not set)'
    assert probe_b64, 'DEL-02 must pass first (probe_b64 not set)'

    # Brief wait for index consistency after bulk deletes
    time.sleep(3)

    r = requests.post(
        f'{BASE_URL}/facematch/search',
        headers=HEADERS,
        json={
            'probe':         {'image': probe_b64},
            'gallery':       gallery,
            'maxCandidates': 50,
            'threshold':     0.0,
        },
    )
    assert r.status_code == 200, f'Search failed: {r.status_code}: {r.text}'

    candidates    = r.json().get('candidates', [])
    candidate_ids = {c.get('id') for c in candidates}
    lingering     = candidate_ids & set(enrolled_ids)

    print(f'\n[DEL-05] Gallery          : {gallery}')
    print(f'[DEL-05] Candidates found : {len(candidates)}')
    print(f'[DEL-05] Deleted IDs still present: {len(lingering)}')
    for lid in sorted(lingering):
        print(f'[DEL-05]   Still present : {lid}')

    # Always clean up the gallery regardless of assertion outcome
    del_r = requests.delete(f'{BASE_URL}/facematch/galleries/{gallery}', headers=HEADERS)
    print(f'[DEL-05] Gallery deleted  : {gallery}  ({del_r.status_code})')

    assert not lingering, (
        f'{len(lingering)} enrollment(s) still visible after deletion:\n'
        + '\n'.join(sorted(lingering))
    )
