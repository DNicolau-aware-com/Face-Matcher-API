#!/usr/bin/env python3
"""
enroll_from_folder.py — Enroll all images from a local folder into an existing gallery.

The gallery is NEVER deleted. If it does not exist it is created.
Credentials are loaded from the project .env via config.py.

Usage:
    python scripts/enroll_from_folder.py

Edit IMAGE_DIR, GALLERY, and WORKERS below if needed.
"""

import base64
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_URL, HEADERS

# ── Configuration ─────────────────────────────────────────────────────────────

IMAGE_DIR      = Path(r"C:\Users\dnicolau\Desktop\images")
GALLERY        = "scale_1m"
WORKERS        = 8
PROGRESS_EVERY = 100
ENROLL_TIMEOUT = 30   # seconds per request
FAILED_CSV     = Path(__file__).resolve().parent.parent / "failed_enrollments_folder.csv"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _url(path: str) -> str:
    return f"{BASE_URL}/facematch{path}"


def ensure_gallery(name: str) -> None:
    r = requests.post(_url("/galleries"), headers=HEADERS, json={"name": name}, timeout=10)
    if r.status_code == 200:
        print(f"  Gallery '{name}' created.")
    elif r.status_code == 400 and ("already" in r.text.lower() or "exists" in r.text.lower()):
        print(f"  Gallery '{name}' already exists — enrolling into it.")
    else:
        raise RuntimeError(f"Gallery setup failed {r.status_code}: {r.text}")


def _enroll(gallery: str, identifier: str, image_path: Path) -> dict:
    try:
        b64 = base64.b64encode(image_path.read_bytes()).decode()
    except Exception as exc:
        return {"success": False, "identifier": identifier, "error": f"read_failed:{exc}", "ms": 0.0}

    t0 = time.time()
    try:
        r = requests.post(
            _url(f"/galleries/{gallery}/enrollments/{identifier}"),
            headers=HEADERS,
            json={"image": b64},
            timeout=ENROLL_TIMEOUT,
        )
        ms = (time.time() - t0) * 1000
        if r.status_code in (200, 201):
            return {"success": True, "identifier": identifier, "error": None, "ms": ms}
        return {"success": False, "identifier": identifier,
                "error": f"http_{r.status_code}:{r.text[:200]}", "ms": ms}
    except requests.Timeout:
        return {"success": False, "identifier": identifier,
                "error": "timeout", "ms": (time.time() - t0) * 1000}
    except Exception as exc:
        return {"success": False, "identifier": identifier,
                "error": str(exc), "ms": (time.time() - t0) * 1000}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Enroll from folder")
    print(f"  Service   : {BASE_URL}")
    print(f"  Gallery   : {GALLERY}")
    print(f"  Image dir : {IMAGE_DIR}")
    print(f"  Workers   : {WORKERS}")

    if not IMAGE_DIR.exists():
        print(f"\nERROR: directory not found: {IMAGE_DIR}", file=sys.stderr)
        sys.exit(1)

    images = sorted(
        p for p in IMAGE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        print(f"\nERROR: no images found in {IMAGE_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"  Images    : {len(images):,}\n")

    # Health check
    try:
        h = requests.get(_url("/health"), headers=HEADERS, timeout=10)
        print(f"  Health    : {h.json().get('status', 'ok')}\n")
    except Exception as exc:
        print(f"  WARN health check failed: {exc}\n", file=sys.stderr)

    ensure_gallery(GALLERY)

    # Enrollment
    total     = len(images)
    enrolled  = failed = attempted = 0
    durations = []
    failures  = []
    t_start   = time.time()

    print(f"\n[Enroll] Starting — {total:,} images, {WORKERS} workers")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_enroll, GALLERY, p.stem, p): p for p in images}
        for fut in as_completed(futures):
            res = fut.result()
            attempted += 1

            if res["success"]:
                enrolled += 1
                durations.append(res["ms"])
            else:
                failed += 1
                failures.append(res)

            if attempted % PROGRESS_EVERY == 0 or attempted == total:
                elapsed = time.time() - t_start
                rate    = attempted / elapsed if elapsed > 0 else 0
                print(f"  {attempted:>6,}/{total:,}  enrolled={enrolled:,}  "
                      f"failed={failed:,}  {rate:.1f} img/sec", flush=True)

    wall_s = time.time() - t_start

    # Save failures
    if failures:
        with open(FAILED_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["identifier", "error", "duration_ms"])
            for r in failures:
                w.writerow([r["identifier"], r["error"], f"{r['ms']:.1f}"])
        print(f"\n  Failed enrollments saved: {FAILED_CSV}")

    # Summary
    avg_ms = sum(durations) / len(durations) if durations else 0
    s      = sorted(durations)
    p95_ms = s[int(0.95 * len(s))] if s else 0

    print(f"\n{'='*52}")
    print(f"  Enrollment Summary")
    print(f"{'='*52}")
    print(f"  Total images   : {total:>8,}")
    print(f"  Enrolled       : {enrolled:>8,}")
    print(f"  Failed         : {failed:>8,}")
    print(f"  Duration       : {wall_s/60:>7.1f} min  ({wall_s:.0f}s)")
    print(f"  Throughput     : {enrolled/wall_s:>7.1f} img/sec" if wall_s > 0 else "")
    print(f"  Avg latency    : {avg_ms:>7.0f} ms")
    print(f"  P95 latency    : {p95_ms:>7.0f} ms")
    print(f"{'='*52}")


if __name__ == "__main__":
    main()
