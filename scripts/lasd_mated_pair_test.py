#!/usr/bin/env python3
"""
lasd_mated_pair_test.py — LASD Mated Pair 1:N Search Test

READ-SAFE: creates/enrolls a new gallery. Never touches scale_1m or any
other existing gallery. The --gallery name is created fresh (--fresh resets it).

End-to-end workflow
───────────────────
  Phase 1 — Gallery setup    (create or reset)
  Phase 2 — Enrollment       (41 K gallery-side images, concurrent workers)
  Phase 3 — 1:N Search       (8 K probe images, concurrent workers)
  Phase 4 — Results CSV + summary

Mate linkage
────────────
  Gallery xlsx and Probes xlsx both contain a PersonID column.
  A probe is "found" when any enrolled gallery image for the same PersonID
  appears in the top-100 candidate list.

  Output columns per probe:
    probe_identifier    — UUID stem of the probe image
    person_id
    mate_found          — True/False
    best_mate_rank      — lowest rank (1 = best) of any gallery mate in top-100
    best_mate_id        — gallery UUID at that rank
    best_mate_score     — score at that rank  (-log10(FMR), higher = better)
    num_gallery_mates   — how many gallery images exist for this PersonID
    response_time_ms
    rank_001_id .. rank_100_id      — full candidate list IDs
    rank_001_score .. rank_100_score

Usage examples
──────────────
  Full run (enroll + search):
    python scripts/lasd_mated_pair_test.py --fresh

  Enroll only:
    python scripts/lasd_mated_pair_test.py --fresh --enroll-only

  Search only (gallery already enrolled):
    python scripts/lasd_mated_pair_test.py --search-only

  Custom gallery name and more workers:
    python scripts/lasd_mated_pair_test.py --gallery lasd_test_v2 --fresh --workers 16

  Quick smoke test (first 20 probes):
    python scripts/lasd_mated_pair_test.py --search-only --limit 20
"""

import argparse
import base64
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

# ── Credentials from .env via config.py ──────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_URL, HEADERS

# ── Defaults (override via CLI) ───────────────────────────────────────────────
DEFAULT_GALLERY      = "lasd_mated_pair_test"
DEFAULT_IMAGES_DIR   = r"C:\Users\dnicolau\Desktop\images"
DEFAULT_GALLERY_XLSX = r"C:\Users\dnicolau\Downloads\lasd_gallery.xlsx"
DEFAULT_PROBES_XLSX  = r"C:\Users\dnicolau\Downloads\lasd_probes.xlsx"
DEFAULT_OUTPUT       = "lasd_search_results.csv"
DEFAULT_FAILED_CSV   = "lasd_failed_enrollments.csv"
DEFAULT_WORKERS      = 8
DEFAULT_THRESHOLD    = 0.0   # 0 = return all candidates regardless of score
MAX_CANDIDATES       = 100
ENROLL_TIMEOUT       = 30
SEARCH_TIMEOUT       = 60
PROGRESS_EVERY       = 200


# ── URL builder ───────────────────────────────────────────────────────────────

def url(path: str) -> str:
    return f"{BASE_URL}/facematch{path}"


# ── Image encoding ────────────────────────────────────────────────────────────

def b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ── Excel loader ──────────────────────────────────────────────────────────────

def load_xlsx(path: str) -> list[dict]:
    """Load an xlsx into a list of dicts keyed by header row."""
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl required: pip install openpyxl")
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    rows = []
    for r in range(2, ws.max_row + 1):
        row = {headers[c]: ws.cell(r, c + 1).value for c in range(len(headers))}
        rows.append(row)
    wb.close()
    return rows


# ── Gallery CRUD ──────────────────────────────────────────────────────────────

def create_gallery(name: str) -> None:
    r = requests.post(url("/galleries"), headers=HEADERS,
                      json={"name": name}, timeout=10)
    if r.status_code in (200, 201):
        print(f"  Created gallery '{name}'.")
    elif r.status_code == 400 and ("already" in r.text.lower() or "exist" in r.text.lower()):
        print(f"  Gallery '{name}' already exists — reusing.")
    else:
        raise RuntimeError(f"Create gallery failed {r.status_code}: {r.text}")


def delete_gallery(name: str) -> None:
    r = requests.delete(url(f"/galleries/{name}"), headers=HEADERS, timeout=10)
    if r.status_code in (200, 204):
        print(f"  Deleted gallery '{name}'.")
    elif r.status_code == 404:
        print(f"  Gallery '{name}' not found — nothing to delete.")
    else:
        print(f"  WARN delete returned {r.status_code}: {r.text[:80]}", file=sys.stderr)


def gallery_face_count(name: str) -> int:
    r = requests.get(url("/galleries"), headers=HEADERS,
                     params={"size": 200}, timeout=10)
    r.raise_for_status()
    for g in r.json().get("content", []):
        if g["name"] == name:
            return g["faceCount"]
    return -1


# ── Enrollment phase ──────────────────────────────────────────────────────────

@dataclass
class EnrollResult:
    identifier:  str
    success:     bool
    duration_ms: float
    error:       Optional[str] = None


def enroll_one(gallery: str, identifier: str, image_path: Path) -> EnrollResult:
    try:
        image_b64 = b64(image_path)
    except Exception as exc:
        return EnrollResult(identifier, False, 0.0, f"read_error:{exc}")

    t0 = time.perf_counter()
    try:
        r = requests.post(
            url(f"/galleries/{gallery}/enrollments/{identifier}"),
            headers=HEADERS,
            json={"image": image_b64},
            timeout=ENROLL_TIMEOUT,
        )
        ms = (time.perf_counter() - t0) * 1000
        if r.status_code in (200, 201):
            return EnrollResult(identifier, True, ms)
        return EnrollResult(identifier, False, ms,
                            f"http_{r.status_code}:{r.text[:150]}")
    except requests.Timeout:
        return EnrollResult(identifier, False,
                            (time.perf_counter() - t0) * 1000, "timeout")
    except Exception as exc:
        return EnrollResult(identifier, False,
                            (time.perf_counter() - t0) * 1000, str(exc))


def run_enrollment(gallery: str,
                   gallery_items: list[tuple[str, Path]],
                   workers: int,
                   failed_csv: str) -> dict:
    """
    Enroll gallery-side images.
    gallery_items: list of (identifier, image_path) tuples.
    """
    total = len(gallery_items)
    enrolled = failed = done = 0
    durations: list[float] = []
    failed_rows: list[dict] = []
    t_start = time.perf_counter()

    print(f"\n[Enroll] {total:,} gallery images — {workers} workers")
    print(f"  Endpoint: POST {url(f'/galleries/{gallery}/enrollments/{{id}}')}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(enroll_one, gallery, ident, path): (ident, path)
            for ident, path in gallery_items
        }
        for fut in as_completed(futures):
            res = fut.result()
            done += 1
            if res.success:
                enrolled += 1
                durations.append(res.duration_ms)
            else:
                failed += 1
                failed_rows.append({"identifier": res.identifier, "error": res.error,
                                    "duration_ms": f"{res.duration_ms:.1f}"})
            if done % PROGRESS_EVERY == 0 or done == total:
                elapsed = time.perf_counter() - t_start
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  {done:>7,}/{total:,}  enrolled={enrolled:,}  "
                      f"failed={failed:,}  {rate:.1f} img/sec", flush=True)

    wall_s = time.perf_counter() - t_start

    if failed_rows:
        with open(failed_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["identifier", "error", "duration_ms"])
            w.writeheader()
            w.writerows(failed_rows)
        print(f"  Failed enrollments: {failed_csv}  ({failed} rows)")

    s = sorted(durations)
    return {
        "total": total, "enrolled": enrolled, "failed": failed,
        "wall_s": wall_s,
        "img_per_sec": round(enrolled / wall_s, 2) if wall_s > 0 else 0,
        "avg_ms":  round(sum(durations) / len(durations), 1) if durations else 0,
        "p95_ms":  round(s[int(0.95 * len(s))], 1) if s else 0,
        "p99_ms":  round(s[int(0.99 * len(s))], 1) if s else 0,
    }


# ── Search phase ──────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    probe_identifier:  str
    person_id:         str
    num_gallery_mates: int
    mate_found:        bool
    best_mate_rank:    Optional[int]
    best_mate_id:      Optional[str]
    best_mate_score:   Optional[float]
    response_time_ms:  float
    top_ids:           list = field(default_factory=list)
    top_scores:        list = field(default_factory=list)
    http_status:       int  = 0
    status:            str  = "ok"   # ok | error | timeout
    error:             Optional[str] = None


def search_one(gallery: str, image_path: Path, identifier: str,
               person_id: str, mate_ids: set[str],
               threshold: float) -> SearchResult:

    base = SearchResult(
        probe_identifier=identifier, person_id=person_id,
        num_gallery_mates=len(mate_ids),
        mate_found=False, best_mate_rank=None,
        best_mate_id=None, best_mate_score=None,
        response_time_ms=0.0,
    )

    try:
        image_b64 = b64(image_path)
    except Exception as exc:
        base.status = "error"
        base.error  = f"read_error:{exc}"
        return base

    t0 = time.perf_counter()
    try:
        r = requests.post(
            url("/search"),
            headers=HEADERS,
            json={
                "probe":         {"image": image_b64},
                "gallery":       gallery,
                "maxCandidates": MAX_CANDIDATES,
                "threshold":     threshold,
            },
            timeout=SEARCH_TIMEOUT,
        )
        base.response_time_ms = (time.perf_counter() - t0) * 1000
        base.http_status = r.status_code
        r.raise_for_status()
    except requests.Timeout:
        base.response_time_ms = (time.perf_counter() - t0) * 1000
        base.status = "timeout"
        base.error  = "request_timeout"
        return base
    except Exception as exc:
        base.response_time_ms = (time.perf_counter() - t0) * 1000
        base.status = "error"
        base.error  = str(exc)
        return base

    candidates = r.json().get("candidates", [])
    base.top_ids    = [c["id"]           for c in candidates]
    base.top_scores = [float(c["score"]) for c in candidates]

    # Find best-ranking gallery mate in the candidate list
    for rank, c in enumerate(candidates, start=1):
        if c["id"] in mate_ids:
            base.mate_found    = True
            base.best_mate_rank  = rank
            base.best_mate_id    = c["id"]
            base.best_mate_score = float(c["score"])
            break  # first hit = best rank

    return base


def run_searches(gallery: str,
                 probe_items: list[tuple[str, Path, str, set[str]]],
                 workers: int,
                 threshold: float) -> list[SearchResult]:
    """
    probe_items: list of (identifier, image_path, person_id, {mate_ids})
    """
    total   = len(probe_items)
    results: list[SearchResult] = []
    errors = found = done = 0
    t_start = time.perf_counter()

    print(f"\n[Search] {total:,} probes — {workers} workers")
    print(f"  Endpoint : POST {url('/search')}")
    print(f"  Gallery  : {gallery}")
    print(f"  Max cands: {MAX_CANDIDATES}   Threshold: {threshold}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(search_one, gallery, path, ident, pid, mates, threshold):
            (ident, path)
            for ident, path, pid, mates in probe_items
        }
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            done += 1
            if res.status != "ok":
                errors += 1
            if res.mate_found:
                found += 1
            if done % PROGRESS_EVERY == 0 or done == total:
                elapsed = time.perf_counter() - t_start
                tput = done / elapsed if elapsed > 0 else 0
                print(f"  {done:>6,}/{total:,}  found={found:,}  "
                      f"errors={errors}  {tput:.1f} req/sec", flush=True)

    wall = time.perf_counter() - t_start
    print(f"  Wall: {wall:.1f}s  Throughput: {total/wall:.1f} req/sec")
    return results


# ── CSV writer ────────────────────────────────────────────────────────────────

def write_csv(results: list[SearchResult], path: str) -> None:
    id_cols    = [f"rank_{i:03d}_id"    for i in range(1, MAX_CANDIDATES + 1)]
    score_cols = [f"rank_{i:03d}_score" for i in range(1, MAX_CANDIDATES + 1)]
    fieldnames = [
        "probe_identifier", "person_id", "num_gallery_mates",
        "mate_found", "best_mate_rank", "best_mate_id", "best_mate_score",
        "response_time_ms", "http_status", "status", "error",
        *id_cols, *score_cols,
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(fieldnames)
        for r in results:
            pad_ids    = r.top_ids    + [None] * (MAX_CANDIDATES - len(r.top_ids))
            pad_scores = r.top_scores + [None] * (MAX_CANDIDATES - len(r.top_scores))
            w.writerow([
                r.probe_identifier, r.person_id, r.num_gallery_mates,
                r.mate_found, r.best_mate_rank,
                r.best_mate_id,
                f"{r.best_mate_score:.4f}" if r.best_mate_score is not None else "",
                f"{r.response_time_ms:.2f}",
                r.http_status, r.status, r.error or "",
                *pad_ids,
                *[f"{s:.4f}" if s is not None else "" for s in pad_scores],
            ])
    print(f"  Results CSV: {path}  ({len(results):,} rows)")


# ── Summaries ─────────────────────────────────────────────────────────────────

def pct(n: int, total: int) -> str:
    return f"{100 * n / total:.2f}%" if total else "N/A"

def percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(int(p * len(s)), len(s) - 1)]


def print_enrollment_summary(stats: dict) -> None:
    w = stats["wall_s"]
    print(f"\n{'='*60}")
    print("  Enrollment Summary")
    print(f"{'='*60}")
    print(f"  Gallery images:      {stats['total']:>8,}")
    print(f"  Enrolled:            {stats['enrolled']:>8,}")
    print(f"  Failed:              {stats['failed']:>8,}")
    print(f"  Wall time:           {w/60:>7.1f} min  ({w:.0f}s)")
    print(f"  Throughput:          {stats['img_per_sec']:>7.1f} img/sec")
    print(f"  Avg latency:         {stats['avg_ms']:>7.1f} ms")
    print(f"  P95 latency:         {stats['p95_ms']:>7.1f} ms")
    print(f"  P99 latency:         {stats['p99_ms']:>7.1f} ms")
    print(f"{'='*60}")


def print_search_summary(results: list[SearchResult]) -> None:
    n      = len(results)
    ok     = [r for r in results if r.status == "ok"]
    found  = [r for r in results if r.mate_found]
    errs   = [r for r in results if r.status != "ok"]
    times  = [r.response_time_ms for r in ok]
    ranks  = [r.best_mate_rank for r in found if r.best_mate_rank]
    scores = [r.best_mate_score for r in found if r.best_mate_score is not None]

    r1   = sum(1 for r in ranks if r == 1)
    r5   = sum(1 for r in ranks if r <= 5)
    r10  = sum(1 for r in ranks if r <= 10)
    r20  = sum(1 for r in ranks if r <= 20)
    r50  = sum(1 for r in ranks if r <= 50)
    r100 = len(found)

    print(f"\n{'='*60}")
    print("  1:N Search Summary")
    print(f"{'='*60}")
    print(f"  Probes searched:          {n:>8,}")
    print(f"  Successful responses:     {len(ok):>8,}")
    print(f"  Errors / timeouts:        {len(errs):>8,}  ({pct(len(errs), n)})")
    print()
    print("  IDENTIFICATION ACCURACY (mate in top N):")
    print(f"    Rank-1   : {r1:>6,} / {n:,}  ({pct(r1, n)})")
    print(f"    Top-5    : {r5:>6,} / {n:,}  ({pct(r5, n)})")
    print(f"    Top-10   : {r10:>6,} / {n:,}  ({pct(r10, n)})")
    print(f"    Top-20   : {r20:>6,} / {n:,}  ({pct(r20, n)})")
    print(f"    Top-50   : {r50:>6,} / {n:,}  ({pct(r50, n)})")
    print(f"    Top-100  : {r100:>6,} / {n:,}  ({pct(r100, n)})")
    not_found = n - r100
    print(f"    Not found: {not_found:>6,} / {n:,}  ({pct(not_found, n)})")
    if ranks:
        print(f"    Avg mate rank: {sum(ranks)/len(ranks):.2f}")
    print()
    if times:
        print("  RESPONSE TIME (ms):")
        print(f"    Min      : {min(times):>8.1f}")
        print(f"    Average  : {sum(times)/len(times):>8.1f}")
        print(f"    Median   : {percentile(times, 0.50):>8.1f}")
        print(f"    P95      : {percentile(times, 0.95):>8.1f}")
        print(f"    P99      : {percentile(times, 0.99):>8.1f}")
        print(f"    Max      : {max(times):>8.1f}")
        wall_s = sum(r.response_time_ms for r in results) / 1000
        print(f"    Throughput: {n/wall_s:.1f} req/sec (sustained)")
    print()
    if scores:
        print("  MATE SCORE — when found  (-log10(FMR), higher = better):")
        print(f"    Min      : {min(scores):>8.4f}")
        print(f"    Average  : {sum(scores)/len(scores):>8.4f}")
        print(f"    Max      : {max(scores):>8.4f}")
    print(f"{'='*60}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="LASD Mated Pair 1:N Search Test (credentials from .env)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--gallery",       default=DEFAULT_GALLERY,
                   help="Gallery name to create and enroll into")
    p.add_argument("--images-dir",    default=DEFAULT_IMAGES_DIR,
                   help="Local directory containing all LASD images")
    p.add_argument("--gallery-xlsx",  default=DEFAULT_GALLERY_XLSX,
                   help="Excel file for gallery-side images (File, PersonID columns)")
    p.add_argument("--probes-xlsx",   default=DEFAULT_PROBES_XLSX,
                   help="Excel file for probe-side images (File, PersonID columns)")
    p.add_argument("--workers",       type=int,   default=DEFAULT_WORKERS,
                   help="Concurrent workers for enrollment and search")
    p.add_argument("--threshold",     type=float, default=DEFAULT_THRESHOLD,
                   help="Search score threshold (0.0 returns all candidates)")
    p.add_argument("--fresh",         action="store_true",
                   help="Delete and recreate gallery before enrolling")
    p.add_argument("--output",        default=DEFAULT_OUTPUT,
                   help="Search results CSV path")
    p.add_argument("--failed-output", default=DEFAULT_FAILED_CSV,
                   help="Failed enrollments CSV path")
    p.add_argument("--enroll-only",   action="store_true",
                   help="Run enrollment phase only")
    p.add_argument("--search-only",   action="store_true",
                   help="Skip enrollment — gallery already populated")
    p.add_argument("--limit",         type=int, default=None,
                   help="Limit probes to first N (smoke test)")
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    print("LASD Mated Pair 1:N Search Test")
    print(f"  Service      : {BASE_URL}")
    print(f"  Gallery      : {args.gallery}")
    print(f"  Images dir   : {args.images_dir}")
    print(f"  Gallery xlsx : {args.gallery_xlsx}")
    print(f"  Probes xlsx  : {args.probes_xlsx}")
    print(f"  Workers      : {args.workers}")
    print(f"  Threshold    : {args.threshold}")
    print(f"  Output       : {args.output}")

    images_dir = Path(args.images_dir)
    if not images_dir.exists():
        print(f"ERROR: images directory not found: {images_dir}", file=sys.stderr)
        sys.exit(1)

    # Health check
    try:
        h = requests.get(url("/health"), headers=HEADERS, timeout=10)
        print(f"  Health       : {h.json().get('status', 'ok')}")
    except Exception as exc:
        print(f"  WARN health check failed: {exc}", file=sys.stderr)

    # ── Load Excel files ──────────────────────────────────────────────────────
    print(f"\n[Load] Reading Excel manifests ...")
    gallery_rows = load_xlsx(args.gallery_xlsx)
    probe_rows   = load_xlsx(args.probes_xlsx)
    print(f"  Gallery xlsx : {len(gallery_rows):,} rows")
    print(f"  Probes xlsx  : {len(probe_rows):,} rows")

    # Build PersonID → set of gallery UUIDs
    person_to_gallery: dict[str, set[str]] = {}
    gallery_uuid_to_path: dict[str, Path] = {}
    missing_gallery = 0

    for row in gallery_rows:
        file_val   = row.get("File", "") or ""
        person_id  = str(row.get("PersonID", "")).strip()
        uuid_stem  = Path(file_val).stem
        local_path = images_dir / f"{uuid_stem}.jpg"
        if not local_path.exists():
            missing_gallery += 1
            continue
        gallery_uuid_to_path[uuid_stem] = local_path
        person_to_gallery.setdefault(person_id, set()).add(uuid_stem)

    # Build probe list
    probe_items_all: list[tuple[str, Path, str, set[str]]] = []
    missing_probes = 0

    for row in probe_rows:
        file_val  = row.get("File", "") or ""
        person_id = str(row.get("PersonID", "")).strip()
        uuid_stem = Path(file_val).stem
        local_path = images_dir / f"{uuid_stem}.jpg"
        if not local_path.exists():
            missing_probes += 1
            continue
        mate_ids = person_to_gallery.get(person_id, set())
        probe_items_all.append((uuid_stem, local_path, person_id, mate_ids))

    print(f"  Gallery images resolved : {len(gallery_uuid_to_path):,}  "
          f"(missing locally: {missing_gallery})")
    print(f"  Probe images resolved   : {len(probe_items_all):,}  "
          f"(missing locally: {missing_probes})")
    print(f"  Unique PersonIDs        : {len(person_to_gallery):,}")

    probes_no_mate = sum(1 for _, _, _, m in probe_items_all if not m)
    if probes_no_mate:
        print(f"  WARN: {probes_no_mate} probes have no gallery mate in the xlsx")

    # Apply limit
    probe_items = probe_items_all
    if args.limit:
        probe_items = probe_items_all[: args.limit]
        print(f"  --limit: using {len(probe_items)} of {len(probe_items_all)} probes")

    # ── Gallery setup ─────────────────────────────────────────────────────────
    if not args.search_only:
        print(f"\n[Gallery] Setting up '{args.gallery}' ...")
        if args.fresh:
            delete_gallery(args.gallery)
            time.sleep(0.5)
        create_gallery(args.gallery)

    # ── Enrollment ────────────────────────────────────────────────────────────
    enroll_stats = {
        "total": 0, "enrolled": 0, "failed": 0, "wall_s": 0,
        "img_per_sec": 0, "avg_ms": 0, "p95_ms": 0, "p99_ms": 0,
    }
    if not args.search_only:
        gallery_items = list(gallery_uuid_to_path.items())  # [(uuid, path), ...]
        enroll_stats = run_enrollment(
            args.gallery, gallery_items,
            workers=args.workers,
            failed_csv=args.failed_output,
        )
        print_enrollment_summary(enroll_stats)
        count = gallery_face_count(args.gallery)
        print(f"  Gallery face count: {count:,}")

    if args.enroll_only:
        return

    # ── 1:N Search ────────────────────────────────────────────────────────────
    results = run_searches(
        args.gallery, probe_items,
        workers=args.workers,
        threshold=args.threshold,
    )

    write_csv(results, args.output)
    print_search_summary(results)


if __name__ == "__main__":
    main()
