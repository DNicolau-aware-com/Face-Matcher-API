# -*- coding: utf-8 -*-
"""
test_benchmark.py — Throughput and latency benchmark matching the /benchmark UI page.

The UI runs N iterations of one operation and reports:
  avg / median / p95 / min / max latency (ms)  +  throughput (req/s)

Three operations, each run ITERATIONS times:
  BM-01  Search  — POST /facematch/search         (maxCandidates=10, threshold=4)
  BM-02  Compare — POST /facematch/compare        (image vs image,   threshold=4)
  BM-03  Enroll  — POST /facematch/galleries/{g}/enrollments/{id}  (+cleanup)

UI defaults replicated: maxCandidates=10, threshold=4.0.
ITERATIONS defaults to 10 for CI speed; set to 20+ to match the UI default.
"""

import time
import uuid
import requests
import pytest
from config import BASE_URL, HEADERS, IMAGES

GALLERY        = 'today2'
IMAGE_KEY      = 'dan_face'
ITERATIONS     = 10
THRESHOLD      = 4.0
MAX_CANDIDATES = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_stats(latencies, total_wall_ms):
    sorted_l = sorted(latencies)
    n        = len(sorted_l)
    return {
        'avg':        sum(latencies) / n,
        'median':     sorted_l[n // 2],
        'p95':        sorted_l[max(0, int(n * 0.95) - 1)],
        'min':        sorted_l[0],
        'max':        sorted_l[-1],
        'throughput': round(n / total_wall_ms * 1000, 2),
    }


def _print_report(tag, latencies, total_wall_ms, successes, failures):
    s = _compute_stats(latencies, total_wall_ms)
    print(f'\n[{tag}] Iterations={len(latencies)}  successes={successes}  failures={len(failures)}')
    print(f'[{tag}] {"Metric":<12} {"Value":>12}')
    print(f'[{tag}] {"-"*12} {"-"*12}')
    print(f'[{tag}] {"avg":<12} {s["avg"]:>10.1f} ms')
    print(f'[{tag}] {"median":<12} {s["median"]:>10.1f} ms')
    print(f'[{tag}] {"p95":<12} {s["p95"]:>10.1f} ms')
    print(f'[{tag}] {"min":<12} {s["min"]:>10.1f} ms')
    print(f'[{tag}] {"max":<12} {s["max"]:>10.1f} ms')
    print(f'[{tag}] {"throughput":<12} {s["throughput"]:>10.2f} req/s')


# ── BM-01  Search throughput ──────────────────────────────────────────────────

def test_bm01_search_throughput():
    """
    Run ITERATIONS search requests back-to-back.
    Mirrors UI: search(gallery, image, maxCandidates=10, threshold=4).
    All requests must return 200. Latency stats are reported.
    """
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config.')

    url     = f'{BASE_URL}/facematch/search'
    payload = {
        'probe':         {'image': image_b64},
        'gallery':       GALLERY,
        'maxCandidates': MAX_CANDIDATES,
        'threshold':     THRESHOLD,
    }

    latencies  = []
    successes  = 0
    failures   = []
    wall_start = time.perf_counter()

    print(f'\n[BM-01] Search  gallery={GALLERY}  iterations={ITERATIONS}  threshold={THRESHOLD}')

    for i in range(ITERATIONS):
        t0 = time.perf_counter()
        r  = requests.post(url, headers=HEADERS, json=payload)
        ms = (time.perf_counter() - t0) * 1000
        latencies.append(ms)
        if r.status_code == 200:
            successes += 1
            candidates = r.json().get('candidates', [])
            print(f'[BM-01]   iter {i+1:>3}  {ms:>8.1f} ms  candidates={len(candidates)}')
        else:
            failures.append(f'iter {i+1}: status={r.status_code} body={r.text[:100]}')
            print(f'[BM-01]   iter {i+1:>3}  {ms:>8.1f} ms  FAIL {r.status_code}')

    total_wall_ms = (time.perf_counter() - wall_start) * 1000
    _print_report('BM-01', latencies, total_wall_ms, successes, failures)

    assert not failures, 'Search iteration(s) failed:\n' + '\n'.join(failures)


# ── BM-02  Compare throughput ─────────────────────────────────────────────────

def test_bm02_compare_throughput():
    """
    Run ITERATIONS compare requests back-to-back (same image vs itself).
    Mirrors UI: compareImages(image, image, threshold=4).
    All requests must return 200. Latency stats are reported.
    """
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config.')

    url     = f'{BASE_URL}/facematch/compare'
    payload = {
        'probe':     {'image': image_b64},
        'candidate': {'image': image_b64},
        'threshold': THRESHOLD,
    }

    latencies  = []
    successes  = 0
    failures   = []
    wall_start = time.perf_counter()

    print(f'\n[BM-02] Compare  image-vs-image  iterations={ITERATIONS}  threshold={THRESHOLD}')

    for i in range(ITERATIONS):
        t0 = time.perf_counter()
        r  = requests.post(url, headers=HEADERS, json=payload)
        ms = (time.perf_counter() - t0) * 1000
        latencies.append(ms)
        if r.status_code == 200:
            successes += 1
            score = r.json().get('score')
            match = r.json().get('match')
            print(f'[BM-02]   iter {i+1:>3}  {ms:>8.1f} ms  score={score}  match={match}')
        else:
            failures.append(f'iter {i+1}: status={r.status_code} body={r.text[:100]}')
            print(f'[BM-02]   iter {i+1:>3}  {ms:>8.1f} ms  FAIL {r.status_code}')

    total_wall_ms = (time.perf_counter() - wall_start) * 1000
    _print_report('BM-02', latencies, total_wall_ms, successes, failures)

    assert not failures, 'Compare iteration(s) failed:\n' + '\n'.join(failures)


# ── BM-03  Enroll throughput ──────────────────────────────────────────────────

def test_bm03_enroll_throughput():
    """
    Run ITERATIONS enroll requests back-to-back, then delete all bench identities.
    Mirrors UI: enroll(gallery, bench_<ts>_<i>, image).
    All requests must return 200. Cleanup always runs (try/finally).
    """
    image_b64 = IMAGES.get(IMAGE_KEY)
    if not image_b64:
        pytest.fail(f'Image key "{IMAGE_KEY}" not found in config.')

    requests.post(f'{BASE_URL}/facematch/galleries', headers=HEADERS, json={'name': GALLERY})

    run_tag    = uuid.uuid4().hex[:8]
    idents     = [f'bench_{run_tag}_{i}' for i in range(ITERATIONS)]
    latencies  = []
    successes  = 0
    failures   = []
    wall_start = time.perf_counter()

    print(f'\n[BM-03] Enroll  gallery={GALLERY}  iterations={ITERATIONS}  tag={run_tag}')

    try:
        for i, ident in enumerate(idents):
            url = f'{BASE_URL}/facematch/galleries/{GALLERY}/enrollments/{ident}'
            t0  = time.perf_counter()
            r   = requests.post(url, headers=HEADERS, json={'image': image_b64})
            ms  = (time.perf_counter() - t0) * 1000
            latencies.append(ms)
            if r.status_code == 200:
                successes += 1
                print(f'[BM-03]   iter {i+1:>3}  {ms:>8.1f} ms  enrolled={ident}')
            else:
                failures.append(f'iter {i+1} ({ident}): status={r.status_code} body={r.text[:100]}')
                print(f'[BM-03]   iter {i+1:>3}  {ms:>8.1f} ms  FAIL {r.status_code}')
    finally:
        for ident in idents:
            requests.delete(
                f'{BASE_URL}/facematch/galleries/{GALLERY}/enrollments/{ident}',
                headers=HEADERS,
            )
        print(f'[BM-03] Cleanup: deleted {len(idents)} bench enrollments.')

    total_wall_ms = (time.perf_counter() - wall_start) * 1000
    _print_report('BM-03', latencies, total_wall_ms, successes, failures)

    assert not failures, 'Enroll iteration(s) failed:\n' + '\n'.join(failures)
