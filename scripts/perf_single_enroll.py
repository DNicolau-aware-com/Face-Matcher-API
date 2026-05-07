#!/usr/bin/env python3
"""
Face Matcher — Single-Image Enrollment Performance Baseline

Enrolls images one at a time via the live single-enrollment endpoint
(POST /facematch/galleries/{gallery}/enrollments/{identifier}), then runs
probe searches to measure accuracy, latency, and throughput.

Credentials and base URL are loaded from the project .env via config.py —
no command-line flags needed for authentication.

Phases:
  1. Gallery setup   (create or fresh-reset)
  2. Enrollment      (one image per request, concurrent workers)
  3. Search          (all images as probes, concurrent workers)
  4. Summary + Analysis

Outputs:
  <output>           search results CSV (1 row per probe)
  <failed-output>    failed enrollments CSV
  perf_charts/       optional matplotlib charts (--charts)

Usage examples:

  Throughput / latency baseline (no accuracy — no mate manifest):
    python scripts/perf_single_enroll.py ^
      --image-dir C:\\data\\probes ^
      --gallery   scale_1m ^
      --search-only

  Full accuracy test with mate-pair manifest:
    python scripts/perf_single_enroll.py ^
      --image-dir C:\\data\\probes ^
      --manifest  mate_pairs.csv ^
      --gallery   scale_1m ^
      --search-only

  Enroll + search from scratch:
    python scripts/perf_single_enroll.py ^
      --image-dir C:\\data\\images ^
      --gallery   my_test_gallery ^
      --fresh

  Enroll only:
    python scripts/perf_single_enroll.py --image-dir ... --enroll-only --fresh

  Quick smoke test (first 20 probes):
    python scripts/perf_single_enroll.py --image-dir ... --search-only --limit 20
"""

import argparse
import base64
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

# ── Load credentials from project .env via config.py ─────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_URL, HEADERS  # BASE_URL = https://facematcherdemo.knomi.aware.com
                                       # HEADERS  = {x-api-key, Content-Type, x-aware-trace-id}

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_CANDIDATES   = 100
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
ENROLL_TIMEOUT   = 30    # seconds per single-enroll call
SEARCH_TIMEOUT   = 60    # seconds per search call
PROGRESS_EVERY   = 500   # print a progress line every N operations


# ── XLSX helpers for LASD mated-pair workflow ─────────────────────────────────

def _read_xlsx_rows(path: str) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl required: pip install openpyxl")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers = [str(c.value).strip() if c.value else ""
               for c in next(ws.iter_rows(max_row=1))]
    rows = [dict(zip(headers, row)) for row in ws.iter_rows(min_row=2, values_only=True)]
    wb.close()
    return rows


def filter_images_by_xlsx(all_images: list[Path], xlsx_path: str) -> list[Path]:
    """Return only images whose stem appears in the xlsx 'File' column."""
    rows = _read_xlsx_rows(xlsx_path)
    stems = {Path(str(r.get("File", "") or "")).stem for r in rows if r.get("File")}
    return [p for p in all_images if p.stem in stems]


def build_probe_to_mates(gallery_xlsx: str, probe_xlsx: str,
                          img_dir: Path) -> dict[str, frozenset]:
    """
    Return {probe_stem: frozenset(gallery_stems)} linked via PersonID.
    Used for mated-pair accuracy: a probe is 'found' if ANY gallery image
    for the same person appears in the top-100 candidates.
    """
    gallery_rows = _read_xlsx_rows(gallery_xlsx)
    probe_rows   = _read_xlsx_rows(probe_xlsx)

    person_to_gallery: dict[str, set] = {}
    for row in gallery_rows:
        stem = Path(str(row.get("File", "") or "")).stem
        pid  = str(row.get("PersonID", "") or "").strip()
        if stem and pid:
            for ext in IMAGE_EXTENSIONS:
                if (img_dir / f"{stem}{ext}").exists():
                    person_to_gallery.setdefault(pid, set()).add(stem)
                    break

    probe_to_mates: dict[str, frozenset] = {}
    for row in probe_rows:
        stem = Path(str(row.get("File", "") or "")).stem
        pid  = str(row.get("PersonID", "") or "").strip()
        if stem and pid:
            mates = person_to_gallery.get(pid, set())
            if mates:
                probe_to_mates[stem] = frozenset(mates)

    return probe_to_mates


# ── URL builder ───────────────────────────────────────────────────────────────

def _url(path: str) -> str:
    """Build full URL: BASE_URL + /facematch + path."""
    return f"{BASE_URL}/facematch{path}"


def _b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ── Single-image enrollment ───────────────────────────────────────────────────
#
# Endpoint: POST /facematch/galleries/{gallery}/enrollments/{identifier}
# Body:     {"image": "<base64>"}
# Success:  HTTP 200 or 201

def _enroll_single(gallery: str, identifier: str, image_path: Path) -> dict:
    """
    POST one image to the single-enrollment endpoint.
    Returns {"success": bool, "error": str|None, "duration_ms": float}.
    """
    try:
        b64 = _b64(image_path)
    except Exception as exc:
        return {"success": False, "error": f"read_failed:{exc}", "duration_ms": 0.0}

    payload = {"image": b64}

    t0 = time.time()
    try:
        r = requests.post(
            _url(f"/galleries/{gallery}/enrollments/{identifier}"),
            headers=HEADERS,
            json=payload,
            timeout=ENROLL_TIMEOUT,
        )
        ms = (time.time() - t0) * 1000
        if r.status_code in (200, 201):
            return {"success": True, "error": None, "duration_ms": ms}
        return {"success": False,
                "error": f"http_{r.status_code}:{r.text[:200]}",
                "duration_ms": ms}
    except requests.Timeout:
        return {"success": False, "error": "timeout",
                "duration_ms": (time.time() - t0) * 1000}
    except Exception as exc:
        return {"success": False, "error": str(exc),
                "duration_ms": (time.time() - t0) * 1000}


# ── Gallery helpers ───────────────────────────────────────────────────────────

def create_gallery(name: str) -> None:
    r = requests.post(
        _url("/galleries"),
        headers=HEADERS,
        json={"name": name},
        timeout=10,
    )
    if r.status_code == 400 and ("already" in r.text.lower() or "exists" in r.text.lower()):
        print(f"  Gallery '{name}' already exists — reusing.")
        return
    if r.status_code != 200:
        raise RuntimeError(f"Create gallery failed {r.status_code}: {r.text}")
    print(f"  Created gallery '{name}'.")


def delete_gallery(name: str) -> None:
    r = requests.delete(_url(f"/galleries/{name}"), headers=HEADERS, timeout=10)
    if r.status_code in (200, 204):
        print(f"  Deleted gallery '{name}'.")
    elif r.status_code == 404:
        print(f"  Gallery '{name}' not found — skipping delete.")
    else:
        print(f"  WARN delete {r.status_code}: {r.text[:80]}", file=sys.stderr)


def gallery_face_count(name: str) -> int:
    r = requests.get(
        _url("/galleries"),
        headers=HEADERS,
        params={"size": 200},
        timeout=10,
    )
    r.raise_for_status()
    for g in r.json().get("content", []):
        if g["name"] == name:
            return g["faceCount"]
    return -1


# ── Image discovery ───────────────────────────────────────────────────────────

def discover_images(image_dir: Path) -> list[Path]:
    return sorted(
        p for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def identifier_from_path(p: Path) -> str:
    return p.stem


# ── Mate-pair manifest ────────────────────────────────────────────────────────
#
# CSV columns:  probe_identifier, gallery_identifier, [person_id]
# XLSX:         same columns, first sheet
#
# Without a manifest the script uses identity mapping
# (probe stem == gallery stem) — good for "does an enrolled image find
# itself at rank 1?" sanity checks.

def load_manifest(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    if suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("openpyxl required for .xlsx: pip install openpyxl")
        wb  = openpyxl.load_workbook(path, data_only=True)
        ws  = wb.active
        hdrs = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        rows = []
        for row_idx in range(2, ws.max_row + 1):
            row = {hdrs[c]: ws.cell(row_idx, c + 1).value for c in range(len(hdrs))}
            rows.append(row)
        wb.close()
        return rows
    raise ValueError(f"Unsupported manifest format: {suffix}")


def build_mate_map(image_files: list[Path],
                   manifest_rows: Optional[list[dict]]) -> dict[str, str]:
    if manifest_rows:
        return {
            str(row["probe_identifier"]): str(row["gallery_identifier"])
            for row in manifest_rows
            if row.get("probe_identifier") and row.get("gallery_identifier")
        }
    return {identifier_from_path(p): identifier_from_path(p) for p in image_files}


def build_person_map(manifest_rows: Optional[list[dict]]) -> dict[str, str]:
    if not manifest_rows:
        return {}
    result = {}
    for row in manifest_rows:
        pid = row.get("person_id") or row.get("probe_person_id")
        key = row.get("probe_identifier")
        if key and pid:
            result[str(key)] = str(pid)
    return result


# ── Enrollment phase ──────────────────────────────────────────────────────────

@dataclass
class EnrollRecord:
    file_path:   str
    identifier:  str
    success:     bool
    duration_ms: float
    error:       Optional[str]


def run_enrollment(gallery: str, image_files: list[Path],
                   workers: int, progress_every: int,
                   failed_csv: Path) -> dict:
    total     = len(image_files)
    attempted = enrolled = failed = 0
    durations: list[float] = []
    failed_rows: list[EnrollRecord] = []
    t_start   = time.time()

    print(f"\n[Enroll] {total:,} images — {workers} concurrent workers")
    print(f"  Endpoint : POST {_url(f'/galleries/{gallery}/enrollments/{{identifier}}')}")

    def _task(p: Path) -> EnrollRecord:
        ident  = identifier_from_path(p)
        result = _enroll_single(gallery, ident, p)
        return EnrollRecord(
            file_path=str(p), identifier=ident,
            success=result["success"],
            duration_ms=result["duration_ms"],
            error=result.get("error"),
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_task, p): p for p in image_files}
        for fut in as_completed(futures):
            rec = fut.result()
            attempted += 1
            if rec.success:
                enrolled += 1
                durations.append(rec.duration_ms)
            else:
                failed += 1
                failed_rows.append(rec)

            if attempted % progress_every == 0 or attempted == total:
                elapsed = time.time() - t_start
                rate    = attempted / elapsed if elapsed > 0 else 0
                print(f"  {attempted:>7,}/{total:,}  enrolled={enrolled:,}  "
                      f"failed={failed:,}  {rate:.1f} img/sec", flush=True)

    wall_s = time.time() - t_start

    if failed_rows:
        with open(failed_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["file_path", "identifier", "error", "duration_ms"])
            for r in failed_rows:
                w.writerow([r.file_path, r.identifier, r.error, f"{r.duration_ms:.1f}"])
        print(f"  Failed enrollments saved: {failed_csv}")

    s = sorted(durations)
    return {
        "total_images":   total,
        "attempted":      attempted,
        "enrolled":       enrolled,
        "failed":         failed,
        "wall_s":         wall_s,
        "workers":        workers,
        "images_per_sec": round(enrolled / wall_s, 2) if wall_s > 0 else 0,
        "avg_ms":  round(sum(durations) / len(durations), 1) if durations else 0,
        "p95_ms":  round(s[int(0.95 * len(s))], 1) if s else 0,
        "p99_ms":  round(s[int(0.99 * len(s))], 1) if s else 0,
    }


# ── Search phase ──────────────────────────────────────────────────────────────

@dataclass
class ProbeResult:
    probe_file:       str
    probe_identifier: str
    probe_person_id:  Optional[str]
    found:            bool
    mate_rank:        Optional[int]
    mate_score:       Optional[float]
    response_ms:      float
    top_ids:          list
    top_scores:       list
    status:           str    # ok | error | timeout
    error:            Optional[str]


def _search_one(image_path: Path, identifier: str,
                person_id: Optional[str],
                mate_ids: Optional[frozenset],   # set of valid gallery IDs for this probe
                gallery: str, threshold: float) -> ProbeResult:
    try:
        b64 = _b64(image_path)
    except Exception as exc:
        return ProbeResult(str(image_path), identifier, person_id,
                           False, None, None, 0.0, [], [], "error", f"read:{exc}")

    t0 = time.time()
    try:
        r = requests.post(
            _url("/search"),
            headers=HEADERS,
            json={
                "probe":         {"image": b64},
                "gallery":       gallery,
                "maxCandidates": MAX_CANDIDATES,
                "threshold":     threshold,
            },
            timeout=SEARCH_TIMEOUT,
        )
        ms = (time.time() - t0) * 1000
        r.raise_for_status()
    except requests.Timeout:
        return ProbeResult(str(image_path), identifier, person_id,
                           False, None, None,
                           (time.time() - t0) * 1000, [], [], "timeout", "request_timeout")
    except Exception as exc:
        return ProbeResult(str(image_path), identifier, person_id,
                           False, None, None,
                           (time.time() - t0) * 1000, [], [], "error", str(exc))

    cands      = r.json().get("candidates", [])
    top_ids    = [c["id"]           for c in cands]
    top_scores = [float(c["score"]) for c in cands]

    # Find best rank — first candidate whose ID is in the mate set
    mate_rank = mate_score = None
    if mate_ids:
        for i, c in enumerate(cands):
            if c["id"] in mate_ids:
                mate_rank  = i + 1
                mate_score = float(c["score"])
                break

    return ProbeResult(
        probe_file=str(image_path),
        probe_identifier=identifier,
        probe_person_id=person_id,
        found=mate_rank is not None,
        mate_rank=mate_rank,
        mate_score=mate_score,
        response_ms=ms,
        top_ids=top_ids,
        top_scores=top_scores,
        status="ok",
        error=None,
    )


def run_searches(gallery: str, image_files: list[Path],
                 mate_map: dict[str, str], person_map: dict[str, str],
                 workers: int, threshold: float,
                 progress_every: int,
                 probe_to_mates: Optional[dict] = None) -> list[ProbeResult]:
    total   = len(image_files)
    results: list[ProbeResult] = []
    errors  = done = 0
    t_start = time.time()

    print(f"\n[Search] {total:,} probes — {workers} concurrent workers")
    print(f"  Endpoint : POST {_url('/search')}")

    def _task(p: Path) -> ProbeResult:
        ident = identifier_from_path(p)
        if probe_to_mates is not None:
            mate_ids = probe_to_mates.get(ident)  # frozenset or None
        else:
            single = mate_map.get(ident)
            mate_ids = frozenset({single}) if single else None
        return _search_one(p, ident, person_map.get(ident),
                           mate_ids, gallery, threshold)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_task, p): p for p in image_files}
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            done += 1
            if res.status != "ok":
                errors += 1
            if done % progress_every == 0 or done == total:
                elapsed = time.time() - t_start
                found   = sum(1 for r in results if r.found)
                tput    = done / elapsed if elapsed > 0 else 0
                print(f"  {done:>7,}/{total:,}  found={found:,}  "
                      f"errors={errors}  {tput:.1f} req/sec", flush=True)

    wall = time.time() - t_start
    print(f"  Wall: {wall:.0f}s  Throughput: {len(results)/wall:.1f} req/sec")
    return results


# ── CSV output ────────────────────────────────────────────────────────────────

def write_search_csv(results: list[ProbeResult], path: Path) -> None:
    score_hdrs = [f"rank_{i:03d}_score" for i in range(1, MAX_CANDIDATES + 1)]
    id_hdrs    = [f"rank_{i:03d}_id"    for i in range(1, MAX_CANDIDATES + 1)]

    def _fmt(v):
        return f"{v:.4f}" if isinstance(v, float) else v

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "probe_file", "probe_identifier", "probe_person_id",
            "found", "mate_rank", "mate_score", "response_ms",
            "status", "error",
            *id_hdrs, *score_hdrs,
        ])
        for r in results:
            pad_ids    = r.top_ids    + [None] * (MAX_CANDIDATES - len(r.top_ids))
            pad_scores = r.top_scores + [None] * (MAX_CANDIDATES - len(r.top_scores))
            w.writerow([
                r.probe_file, r.probe_identifier, r.probe_person_id,
                r.found, r.mate_rank,
                f"{r.mate_score:.4f}" if r.mate_score is not None else None,
                f"{r.response_ms:.2f}",
                r.status, r.error,
                *pad_ids, *[_fmt(s) for s in pad_scores],
            ])
    print(f"  Search CSV: {path}  ({len(results):,} rows)")


# ── Percentile helper ─────────────────────────────────────────────────────────

def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(int(p * len(s)), len(s) - 1)]


# ── Enrollment summary ────────────────────────────────────────────────────────

def print_enrollment_summary(stats: dict) -> None:
    wall = stats["wall_s"]
    print(f"\n{'='*64}")
    print(f"  Enrollment Summary")
    print(f"{'='*64}")
    print(f"  Images discovered:      {stats['total_images']:>10,}")
    print(f"  Attempted:              {stats['attempted']:>10,}")
    print(f"  Enrolled:               {stats['enrolled']:>10,}")
    print(f"  Failed:                 {stats['failed']:>10,}")
    print(f"  Enrollment time:        {wall/60:>9.1f} min  ({wall:.0f}s)")
    print(f"  Throughput:             {stats['images_per_sec']:>9.1f} images/sec")
    print(f"  Avg enroll latency:     {stats['avg_ms']:>9.1f} ms")
    print(f"  P95 enroll latency:     {stats['p95_ms']:>9.1f} ms")
    print(f"  P99 enroll latency:     {stats['p99_ms']:>9.1f} ms")
    print(f"{'='*64}")


# ── Search summary ────────────────────────────────────────────────────────────

def print_search_summary(results: list[ProbeResult], has_mate_map: bool) -> None:
    n      = len(results)
    ok     = [r for r in results if r.status == "ok"]
    found  = [r for r in results if r.found]
    errors = [r for r in results if r.status != "ok"]
    times  = [r.response_ms for r in ok]
    ranks  = [r.mate_rank for r in found if r.mate_rank is not None]

    def pct(k: int) -> str:
        return f"{100 * k / n:.2f}%" if n else "N/A"

    print(f"\n{'='*64}")
    print(f"  Search Summary")
    print(f"{'='*64}")
    print(f"  Probes run:             {n:>10,}")
    print(f"  Successful searches:    {len(ok):>10,}")
    print(f"  Errors / timeouts:      {len(errors):>10,}  ({pct(len(errors))})")

    if has_mate_map:
        r1   = sum(1 for r in ranks if r == 1)
        r5   = sum(1 for r in ranks if r <= 5)
        r10  = sum(1 for r in ranks if r <= 10)
        r100 = len(found)
        print(f"  Mates found (top-100):  {r100:>10,}  ({pct(r100)})")
        print(f"  Rank-1  accuracy:       {r1:>10,}  ({pct(r1)})")
        print(f"  Rank-5  accuracy:       {r5:>10,}  ({pct(r5)})")
        print(f"  Rank-10 accuracy:       {r10:>10,}  ({pct(r10)})")
        print(f"  Rank-100 accuracy:      {r100:>10,}  ({pct(r100)})")
        if ranks:
            print(f"  Avg mate rank:          {sum(ranks)/len(ranks):>10.2f}")
        gaps = [r.top_scores[0] - r.top_scores[1]
                for r in found
                if len(r.top_scores) > 1 and r.mate_rank == 1]
        if gaps:
            print(f"  Avg rank1-rank2 gap:    {sum(gaps)/len(gaps):>10.4f}  (score units)")
    else:
        print("  (no mate manifest — accuracy metrics not available)")

    if times:
        print(f"  Avg response time:      {sum(times)/len(times):>9.0f} ms")
        print(f"  Min / Max:              {min(times):>7.0f} ms / {max(times):.0f} ms")
        print(f"  P95 response time:      {_pct(times, 0.95):>9.0f} ms")
        print(f"  P99 response time:      {_pct(times, 0.99):>9.0f} ms")
        wall_s = sum(r.response_ms for r in results) / 1000
        print(f"  Search throughput:      {n/wall_s:>9.1f} req/sec (sustained)")

    print(f"{'='*64}")


# ── Analysis ──────────────────────────────────────────────────────────────────

def print_analysis(results: list[ProbeResult], enroll_stats: dict,
                   has_mate_map: bool) -> None:
    n      = len(results)
    ok     = [r for r in results if r.status == "ok"]
    found  = [r for r in results if r.found]
    errors = [r for r in results if r.status != "ok"]
    times  = [r.response_ms for r in ok]
    ranks  = [r.mate_rank for r in found if r.mate_rank is not None]

    fail_rate = enroll_stats["failed"] / max(enroll_stats["attempted"], 1)
    err_rate  = len(errors) / n if n else 0

    print(f"\n{'='*64}")
    print(f"  Analysis")
    print(f"{'='*64}")

    print("\n  WHAT LOOKS GOOD:")
    good = []
    if fail_rate == 0:
        good.append("Zero enrollment failures — all images accepted.")
    elif fail_rate < 0.01:
        good.append(f"Low enrollment failure rate ({fail_rate*100:.2f}%).")
    if err_rate == 0:
        good.append("Zero search errors — service stable throughout the run.")
    if has_mate_map and ranks:
        r1_rate = sum(1 for r in ranks if r == 1) / n
        if r1_rate >= 0.95:
            good.append(f"Rank-1 accuracy {r1_rate*100:.1f}% — strong first-choice identification.")
        if sum(ranks) / len(ranks) <= 1.5:
            good.append(f"Avg mate rank {sum(ranks)/len(ranks):.2f} — mates consistently at the top.")
    if times:
        if sum(times) / len(times) < 2000:
            good.append(f"Avg search latency {sum(times)/len(times):.0f}ms — within interactive range.")
        if _pct(times, 0.99) < 5000:
            good.append(f"P99 search latency {_pct(times, 0.99):.0f}ms — acceptable tail.")
    if enroll_stats.get("images_per_sec", 0) >= 5:
        good.append(f"Enrollment throughput {enroll_stats['images_per_sec']:.1f} img/sec viable for live registration.")
    for item in good:
        print(f"    + {item}")
    if not good:
        print("    (none identified)")

    print("\n  WHAT LOOKS WRONG OR SUSPICIOUS:")
    warn = []
    if fail_rate > 0.05:
        warn.append(f"High enrollment failure rate {fail_rate*100:.1f}% — check failed_enrollments.csv.")
    elif fail_rate > 0.01:
        warn.append(f"Non-trivial enrollment failure rate {fail_rate*100:.1f}% — review failed images.")
    if err_rate > 0.01:
        warn.append(f"Search error rate {err_rate*100:.1f}% — possible service instability or timeouts.")
    if has_mate_map and n > 0:
        r1_rate       = sum(1 for r in ranks if r == 1) / n
        not_found_pct = (n - len(found)) / n * 100
        if r1_rate < 0.90:
            warn.append(f"Rank-1 accuracy below 90% ({r1_rate*100:.1f}%) — algorithm or image-quality issue.")
        if not_found_pct > 10:
            warn.append(f"High not-found rate {not_found_pct:.1f}% — see 'Likely causes' below.")
    if times:
        avg_ms = sum(times) / len(times)
        p99    = _pct(times, 0.99)
        max_ms = max(times)
        if p99 > 10000:
            warn.append(f"P99 latency {p99:.0f}ms exceeds 10s — production-risky tail latency.")
        if max_ms > 30000:
            warn.append(f"Max latency {max_ms:.0f}ms — likely timeout or cold-cache event.")
        if p99 / max(avg_ms, 1) > 5:
            warn.append("High latency variance (P99/avg > 5) — inconsistent service performance.")
    enroll_avg = enroll_stats.get("avg_ms", 0)
    if enroll_avg > 5000:
        warn.append(f"Single-image enrollment avg {enroll_avg:.0f}ms — too slow for synchronous live registration.")
    elif enroll_avg > 2000:
        warn.append(f"Single-image enrollment avg {enroll_avg:.0f}ms — marginal for real-time; consider async flow.")
    for item in warn:
        print(f"    ! {item}")
    if not warn:
        print("    (none identified)")

    print("\n  PRODUCTION-USABLE ASSESSMENT:")
    if times:
        p95_ok = _pct(times, 0.95) < 6000
        err_ok = err_rate < 0.01
        enr_ok = fail_rate < 0.01
        if has_mate_map and ranks:
            r1_rate    = sum(1 for r in ranks if r == 1) / n
            accuracy_ok = r1_rate >= 0.95
            all_ok      = p95_ok and err_ok and enr_ok and accuracy_ok
            verdict     = "YES — all thresholds met." if all_ok else \
                          "NO — one or more thresholds not met (see warnings)."
        else:
            all_ok  = p95_ok and err_ok and enr_ok
            verdict = ("LATENCY/STABILITY: OK" if all_ok else
                       "LATENCY/STABILITY: needs review (see warnings)")
            verdict += "\n    (accuracy not assessed — no mate-pair manifest provided)"
        print(f"    {verdict}")

    if has_mate_map and (n - len(found)) > 0:
        print(f"\n  LIKELY CAUSES OF NOT-FOUND MATES ({n - len(found):,} probes):")
        print("    1. Probe image has no detectable face (blur, extreme angle, occlusion).")
        print("    2. Enrollment failed for that identity — cross-check failed_enrollments.csv.")
        print("    3. Score threshold is non-zero — mate below threshold is suppressed.")
        print("    4. Manifest mismatch: probe_identifier does not match enrolled identifier.")
        print("    5. Gallery does not contain the mate (wrong gallery or enrollment error).")

    if has_mate_map and found:
        gaps = [r.top_scores[0] - r.top_scores[1]
                for r in found
                if len(r.top_scores) > 1 and r.mate_rank == 1]
        if gaps:
            avg_gap = sum(gaps) / len(gaps)
            min_gap = min(gaps)
            print(f"\n  RANK-1 vs RANK-2 SCORE GAP (mate at rank-1, N={len(gaps):,}):")
            label = ("SAFE" if avg_gap >= 1.0 else
                     "MODERATE" if avg_gap >= 0.3 else "RISKY")
            print(f"    {label} — avg gap {avg_gap:.4f}, min gap {min_gap:.4f}.")

    print("\n  LATENCY AND THROUGHPUT FOR LIVE PRODUCTION:")
    enroll_avg = enroll_stats.get("avg_ms", 0)
    if enroll_avg > 0:
        verdict = ("acceptable for real-time registration." if enroll_avg < 1000 else
                   "marginal; consider async enrollment flow." if enroll_avg < 3000 else
                   "too slow for synchronous live flow. Use async.")
        print(f"    Enrollment: {enroll_avg:.0f}ms avg — {verdict}")
    if times:
        avg_ms = sum(times) / len(times)
        tput   = n / (sum(r.response_ms for r in results) / 1000)
        verdict = ("suitable for interactive response." if avg_ms < 2000 else
                   "acceptable for non-interactive workflows." if avg_ms < 5000 else
                   "consider gallery scale and hardware upgrade.")
        print(f"    Search:     {avg_ms:.0f}ms avg — {verdict}")
        print(f"    Effective throughput: ~{tput:.1f} req/sec at {enroll_stats.get('workers', '?')} workers.")

    print("\n  WHAT TO TEST NEXT:")
    print("    1. If no manifest: add a mate-pair manifest to measure true ID accuracy.")
    print("    2. Compare to batch-images enrollment at same worker count for throughput delta.")
    print("    3. Increase --workers (try 16, 32) and watch throughput vs latency trade-off.")
    print("    4. Profile not-found probes — verify face detectability with a standalone detector.")
    print("    5. Run on production-class hardware to establish real SLA baselines.")
    print(f"\n{'='*64}")


# ── Optional charts ───────────────────────────────────────────────────────────

def make_charts(results: list[ProbeResult], out_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (install matplotlib for charts: pip install matplotlib)")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    found  = [r for r in results if r.found]
    times  = [r.response_ms for r in results if r.status == "ok"]
    ranks  = [r.mate_rank for r in found if r.mate_rank]

    if ranks:
        not_found = sum(1 for r in results if not r.found)
        bins = [
            ("1",      sum(1 for r in ranks if r == 1)),
            ("2-5",    sum(1 for r in ranks if 2 <= r <= 5)),
            ("6-10",   sum(1 for r in ranks if 6 <= r <= 10)),
            ("11-50",  sum(1 for r in ranks if 11 <= r <= 50)),
            ("51-100", sum(1 for r in ranks if 51 <= r <= 100)),
            (">100",   not_found),
        ]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar([b[0] for b in bins], [b[1] for b in bins], color="steelblue")
        ax.set_xlabel("Mate rank bin")
        ax.set_ylabel("Count")
        ax.set_title("Mate Rank Distribution")
        fig.tight_layout()
        fig.savefig(out_dir / "rank_distribution.png", dpi=120)
        plt.close()

    if times:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(times, bins=60, color="steelblue", edgecolor="white")
        ax.set_xlabel("Response time (ms)")
        ax.set_ylabel("Count")
        ax.set_title("Search Latency Distribution")
        fig.tight_layout()
        fig.savefig(out_dir / "latency_distribution.png", dpi=120)
        plt.close()

    scores = sorted(r.mate_score for r in found if r.mate_score is not None)
    if scores:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(scores, bins=60, color="steelblue", edgecolor="white")
        ax.set_xlabel("Mate score (scoreFmr)")
        ax.set_ylabel("Count")
        ax.set_title("Mate Score Distribution")
        fig.tight_layout()
        fig.savefig(out_dir / "mate_score_distribution.png", dpi=120)
        plt.close()

    gaps = [r.top_scores[0] - r.top_scores[1]
            for r in found
            if len(r.top_scores) > 1 and r.mate_rank == 1]
    if gaps:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(gaps, bins=60, color="tomato", edgecolor="white")
        ax.set_xlabel("Score gap (rank-1 minus rank-2)")
        ax.set_ylabel("Count")
        ax.set_title("Rank-1 vs Rank-2 Score Gap")
        fig.tight_layout()
        fig.savefig(out_dir / "score_gap_distribution.png", dpi=120)
        plt.close()

    print(f"  Charts saved: {out_dir}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Face Matcher — 1:N Search Performance Baseline (reads credentials from .env)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--gallery",        default="scale_1m",
                   help="Gallery to search (must already exist for --search-only)")
    p.add_argument("--image-dir",      required=True,
                   help="Directory of probe images (filename stem = probe identifier)")
    p.add_argument("--manifest",       default=None,
                   help="CSV/XLSX with columns: probe_identifier, gallery_identifier [, person_id]")
    p.add_argument("--workers",        type=int,   default=8,
                   help="Concurrent workers for enrollment and search")
    p.add_argument("--threshold",      type=float, default=0.0,
                   help="Score threshold (0.0 returns all candidates regardless of score)")
    p.add_argument("--fresh",          action="store_true",
                   help="Delete and recreate gallery before enrolling (CAUTION: destructive)")
    p.add_argument("--output",         default="search_results.csv",
                   help="Search results CSV output path")
    p.add_argument("--failed-output",  default="failed_enrollments.csv",
                   help="Failed enrollments CSV output path")
    p.add_argument("--progress-every", type=int, default=PROGRESS_EVERY,
                   help="Print progress every N operations")
    p.add_argument("--search-only",    action="store_true",
                   help="Skip enrollment — gallery already populated")
    p.add_argument("--enroll-only",    action="store_true",
                   help="Run enrollment only, skip search phase")
    p.add_argument("--limit",          type=int, default=None,
                   help="Process only the first N images (smoke test)")
    p.add_argument("--charts",         action="store_true",
                   help="Generate matplotlib charts into --charts-dir")
    p.add_argument("--charts-dir",     default="perf_charts",
                   help="Output directory for charts")
    # LASD mated-pair options
    p.add_argument("--gallery-xlsx",   default=None,
                   help="XLSX with gallery images (File + PersonID columns). "
                        "Filters --image-dir so only listed images are enrolled.")
    p.add_argument("--probe-xlsx",     default=None,
                   help="XLSX with probe images (File + PersonID columns). "
                        "Filters probe images and builds PersonID-based mate map "
                        "(a probe is 'found' if ANY gallery image for the same person "
                        "appears in top-100 candidates).")
    p.add_argument("--probe-dir",      default=None,
                   help="Directory of probe images for search phase. "
                        "Defaults to --image-dir when not set.")
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args      = parse_args()
    image_dir = Path(args.image_dir)
    probe_dir = Path(args.probe_dir) if args.probe_dir else image_dir

    print("Face Matcher — Single-Image Enrollment Performance Baseline")
    print(f"  Service      : {BASE_URL}")
    print(f"  Gallery      : {args.gallery}")
    print(f"  Image dir    : {image_dir}")
    print(f"  Probe dir    : {probe_dir}")
    print(f"  Workers      : {args.workers}")
    print(f"  Threshold    : {args.threshold}")
    print(f"  Gallery xlsx : {args.gallery_xlsx or '(none)'}")
    print(f"  Probe xlsx   : {args.probe_xlsx or '(none)'}")
    print(f"  Manifest     : {args.manifest or '(none — identity mapping)'}")
    print(f"  Output       : {args.output}")

    # Health check
    try:
        h = requests.get(_url("/health"), headers=HEADERS, timeout=10)
        h.raise_for_status()
        print(f"  Health       : {h.json().get('status', 'ok')}")
    except Exception as exc:
        print(f"  WARN health check failed: {exc}", file=sys.stderr)

    # Discover enrollment images
    print(f"\n[Discover] Scanning {image_dir} ...")
    if not image_dir.exists():
        print(f"  ERROR: directory not found: {image_dir}", file=sys.stderr)
        sys.exit(1)
    all_images = discover_images(image_dir)
    print(f"  Found {len(all_images):,} total images in dir")

    if args.gallery_xlsx:
        print(f"  Filtering to gallery xlsx: {args.gallery_xlsx}")
        enroll_images = filter_images_by_xlsx(all_images, args.gallery_xlsx)
        print(f"  Gallery images to enroll : {len(enroll_images):,}")
    else:
        enroll_images = all_images

    if args.limit:
        enroll_images = enroll_images[: args.limit]
        print(f"  --limit applied: using {len(enroll_images):,} images")

    if not enroll_images:
        print("  ERROR: no enrollment images found.", file=sys.stderr)
        sys.exit(1)

    # Discover probe images (may differ from enrollment images)
    if probe_dir != image_dir or args.probe_xlsx:
        print(f"\n[Discover] Scanning probe dir {probe_dir} ...")
        all_probe_images = discover_images(probe_dir)
        print(f"  Found {len(all_probe_images):,} total probe images")
        if args.probe_xlsx:
            probe_images = filter_images_by_xlsx(all_probe_images, args.probe_xlsx)
            print(f"  Filtered to probe xlsx   : {len(probe_images):,}")
        else:
            probe_images = all_probe_images
    else:
        probe_images = enroll_images

    # Build mate map
    probe_to_mates: Optional[dict] = None
    has_mate_map = False

    if args.gallery_xlsx and args.probe_xlsx:
        print(f"\n[Mates] Building PersonID-based mate map ...")
        probe_to_mates = build_probe_to_mates(args.gallery_xlsx, args.probe_xlsx, image_dir)
        matched = sum(1 for v in probe_to_mates.values() if v)
        print(f"  Probes with gallery mates: {matched:,} / {len(probe_images):,}")
        has_mate_map = True
        mate_map   = {}
        person_map = {}
    elif args.manifest:
        print(f"\n[Manifest] Loading {args.manifest} ...")
        manifest_rows = load_manifest(Path(args.manifest))
        print(f"  Loaded {len(manifest_rows):,} mate-pair rows")
        has_mate_map  = True
        mate_map      = build_mate_map(probe_images, manifest_rows)
        person_map    = build_person_map(manifest_rows)
    else:
        mate_map   = build_mate_map(probe_images, None)
        person_map = {}

    # Gallery setup (skip for search-only)
    if not args.search_only:
        print(f"\n[Gallery] Setting up '{args.gallery}' ...")
        if args.fresh:
            print("  --fresh: deleting existing gallery first.")
            delete_gallery(args.gallery)
            time.sleep(1)
        create_gallery(args.gallery)

    # Enrollment
    enroll_stats = {
        "total_images": len(enroll_images), "attempted": 0,
        "enrolled": 0, "failed": 0, "wall_s": 0,
        "workers": args.workers,
        "images_per_sec": 0, "avg_ms": 0, "p95_ms": 0, "p99_ms": 0,
    }
    if not args.search_only:
        enroll_stats = run_enrollment(
            args.gallery, enroll_images,
            workers=args.workers,
            progress_every=args.progress_every,
            failed_csv=Path(args.failed_output),
        )
        enroll_stats["workers"] = args.workers
        print_enrollment_summary(enroll_stats)
        count = gallery_face_count(args.gallery)
        print(f"  Gallery face count after enrollment: {count:,}")

    if args.enroll_only:
        return

    # Search
    search_results = run_searches(
        args.gallery, probe_images,
        mate_map=mate_map,
        person_map=person_map,
        workers=args.workers,
        threshold=args.threshold,
        progress_every=args.progress_every,
        probe_to_mates=probe_to_mates,
    )

    write_search_csv(search_results, Path(args.output))
    print_search_summary(search_results, has_mate_map)
    print_analysis(search_results, enroll_stats, has_mate_map)

    if args.charts:
        make_charts(search_results, Path(args.charts_dir))


if __name__ == "__main__":
    main()
