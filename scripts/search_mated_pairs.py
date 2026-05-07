#!/usr/bin/env python3
"""
search_mated_pairs.py — 1:N search for mated pair probes against the scale_1m gallery.

READ-ONLY: only calls POST /facematch/search. Does NOT modify or delete the gallery.

For each probe image, sends a 1:N search request and records:
  - Position of the mate in the candidate list (1-indexed, None = not in top 100)
  - Scores of top 100 candidates (full JSON)
  - Response time in milliseconds

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INPUT FORMATS (pick one):

  Option A — CSV file (--input pairs.csv)
    Required columns: probe_path, mate_id
    Example:
      probe_path,mate_id
      /data/probes/subj001_probe.jpg,subj001
      /data/probes/subj002_probe.jpg,subj002

  Option B — Directory of probe images (--probe-dir /data/probes)
    The filename stem (without extension) is used as the mate_id.
    Example: subj001_probe.jpg  →  mate_id = "subj001_probe"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE EXAMPLES:

  python scripts/search_mated_pairs.py --input pairs.csv
  python scripts/search_mated_pairs.py --input pairs.csv --output my_results.csv --workers 10
  python scripts/search_mated_pairs.py --probe-dir /data/probes --limit 50
  python scripts/search_mated_pairs.py --input pairs.csv --gallery scale_1m --threshold 4.0
"""

import argparse
import base64
import csv
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_URL, HEADERS

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_GALLERY = "scale_1m"
MAX_CANDIDATES = 100
DEFAULT_THRESHOLD = 4.0
DEFAULT_WORKERS = 5
REQUEST_TIMEOUT_S = 120

# Output CSV columns (order matters)
FIELDNAMES = [
    "probe_file",
    "mate_id",
    "mate_position",       # 1-indexed rank; empty = not found in top 100
    "mate_score",          # -log10(FMR) score of the mate if found
    "mate_match",          # True/False whether mate exceeded threshold
    "response_time_ms",    # end-to-end HTTP round-trip time
    "num_candidates_returned",
    "top_candidates_json", # full JSON array: [{id, score, match}, ...]
    "http_status",
    "error",
    "timestamp",
    "probe_path",
]


# ── Core search ───────────────────────────────────────────────────────────────

def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def search_probe(probe_path: str, mate_id: str, gallery: str, threshold: float) -> dict:
    """
    Send one 1:N search request.
    Returns a flat dict of all metrics — never raises.
    """
    result = {
        "probe_file": Path(probe_path).name,
        "probe_path": probe_path,
        "mate_id": mate_id,
        "mate_position": "",
        "mate_score": "",
        "mate_match": "",
        "response_time_ms": "",
        "num_candidates_returned": "",
        "top_candidates_json": "",
        "http_status": "",
        "error": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Encode image
    try:
        image_b64 = encode_image(probe_path)
    except Exception as exc:
        result["error"] = f"encode error: {exc}"
        return result

    payload = {
        "probe": {"image": image_b64},
        "gallery": gallery,
        "maxCandidates": MAX_CANDIDATES,
        "threshold": threshold,
    }

    # Send request and measure round-trip time
    try:
        t0 = time.perf_counter()
        resp = requests.post(
            f"{BASE_URL}/facematch/search",
            headers=HEADERS,
            json=payload,
            timeout=REQUEST_TIMEOUT_S,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
    except requests.exceptions.Timeout:
        result["error"] = f"request timed out after {REQUEST_TIMEOUT_S}s"
        return result
    except requests.exceptions.RequestException as exc:
        result["error"] = f"request error: {exc}"
        return result

    result["http_status"] = resp.status_code
    result["response_time_ms"] = round(elapsed_ms, 2)

    if resp.status_code != 200:
        result["error"] = f"HTTP {resp.status_code}: {resp.text[:300]}"
        return result

    try:
        body = resp.json()
    except Exception as exc:
        result["error"] = f"JSON parse error: {exc}"
        return result

    candidates = body.get("candidates", [])
    result["num_candidates_returned"] = len(candidates)
    result["top_candidates_json"] = json.dumps(candidates)

    # Find mate's position (1-indexed)
    for rank, candidate in enumerate(candidates, start=1):
        if candidate.get("id") == mate_id:
            result["mate_position"] = rank
            result["mate_score"] = candidate.get("score", "")
            result["mate_match"] = candidate.get("match", "")
            break

    return result


# ── Input loaders ─────────────────────────────────────────────────────────────

def load_pairs_from_csv(csv_path: str) -> list[tuple[str, str]]:
    """
    Read a CSV with columns probe_path and mate_id.
    Skips rows missing either field.
    """
    pairs = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            probe_path = row.get("probe_path", "").strip()
            mate_id = row.get("mate_id", "").strip()
            if not probe_path or not mate_id:
                print(f"  [WARN] Row {i} skipped (missing probe_path or mate_id)")
                continue
            if not Path(probe_path).exists():
                print(f"  [WARN] Row {i} skipped (file not found): {probe_path}")
                continue
            pairs.append((probe_path, mate_id))
    return pairs


def load_pairs_from_directory(probe_dir: str) -> list[tuple[str, str]]:
    """
    Scan a directory for image files.
    mate_id = filename stem (e.g. 'subj001_probe.jpg' → mate_id 'subj001_probe').
    """
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    pairs = []
    for f in sorted(Path(probe_dir).iterdir()):
        if f.is_file() and f.suffix.lower() in image_extensions:
            pairs.append((str(f), f.stem))
    return pairs


# ── Summary statistics ────────────────────────────────────────────────────────

def print_summary(results: list[dict], elapsed_total_s: float, output_path: str):
    successful = [r for r in results if not r["error"]]
    errored = [r for r in results if r["error"]]

    found = [r for r in successful if r["mate_position"] != ""]
    not_found = [r for r in successful if r["mate_position"] == ""]

    def rank_accuracy(n: int) -> tuple[int, str]:
        count = sum(1 for r in found if int(r["mate_position"]) <= n)
        pct = count / len(successful) * 100 if successful else 0
        return count, f"{pct:.2f}%"

    times = [r["response_time_ms"] for r in successful if r["response_time_ms"] != ""]
    sorted_times = sorted(times)

    def percentile(lst, p):
        if not lst:
            return 0
        idx = max(0, int(len(lst) * p / 100) - 1)
        return lst[idx]

    mate_scores = [float(r["mate_score"]) for r in found if r["mate_score"] != ""]

    print()
    print("=" * 62)
    print("  MATED PAIR SEARCH — RESULTS SUMMARY")
    print("=" * 62)
    print(f"  Total probes           : {len(results)}")
    print(f"  Successful searches    : {len(successful)}")
    print(f"  Errors                 : {len(errored)}")
    print(f"  Total elapsed          : {elapsed_total_s:.1f}s")
    if times:
        throughput = len(successful) / elapsed_total_s
        print(f"  Throughput             : {throughput:.1f} searches/sec")
    print()

    if successful:
        r1_n, r1_p = rank_accuracy(1)
        r5_n, r5_p = rank_accuracy(5)
        r10_n, r10_p = rank_accuracy(10)
        r20_n, r20_p = rank_accuracy(20)
        r50_n, r50_p = rank_accuracy(50)
        r100_n, r100_p = rank_accuracy(100)
        nf = len(not_found)
        nf_p = f"{nf/len(successful)*100:.2f}%"

        print("  IDENTIFICATION ACCURACY (mate found in top N):")
        print(f"    Rank-1  : {r1_n:>6} / {len(successful)}  ({r1_p})")
        print(f"    Top-5   : {r5_n:>6} / {len(successful)}  ({r5_p})")
        print(f"    Top-10  : {r10_n:>6} / {len(successful)}  ({r10_p})")
        print(f"    Top-20  : {r20_n:>6} / {len(successful)}  ({r20_p})")
        print(f"    Top-50  : {r50_n:>6} / {len(successful)}  ({r50_p})")
        print(f"    Top-100 : {r100_n:>6} / {len(successful)}  ({r100_p})")
        print(f"    Not found in top-100 : {nf} ({nf_p})")
        print()

    if times:
        print("  RESPONSE TIME (ms):")
        print(f"    Min      : {min(times):.1f}")
        print(f"    Average  : {sum(times)/len(times):.1f}")
        print(f"    Median   : {percentile(sorted_times, 50):.1f}")
        print(f"    95th pct : {percentile(sorted_times, 95):.1f}")
        print(f"    99th pct : {percentile(sorted_times, 99):.1f}")
        print(f"    Max      : {max(times):.1f}")
        print()

    if mate_scores:
        print("  MATE SCORE — when found (−log₁₀(FMR), higher = better):")
        print(f"    Min      : {min(mate_scores):.4f}")
        print(f"    Average  : {sum(mate_scores)/len(mate_scores):.4f}")
        print(f"    Max      : {max(mate_scores):.4f}")
        print()

    if errored:
        print(f"  ERRORS ({len(errored)} probes):")
        for r in errored[:10]:
            print(f"    {r['probe_file']}: {r['error']}")
        if len(errored) > 10:
            print(f"    ... and {len(errored) - 10} more (see output CSV)")
        print()

    print(f"  Full results saved to  : {output_path}")
    print("=" * 62)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="1:N mated pair search — scale_1m gallery. Read-only (no deletes).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--input", "-i",
        metavar="FILE",
        help="CSV with columns: probe_path, mate_id",
    )
    src.add_argument(
        "--probe-dir", "-d",
        metavar="DIR",
        help="Directory of probe images (filename stem = mate_id)",
    )

    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output CSV path (default: search_results_YYYYMMDD_HHMMSS.csv)",
    )
    parser.add_argument(
        "--gallery", "-g",
        default=DEFAULT_GALLERY,
        help=f"Gallery to search against (default: {DEFAULT_GALLERY})",
    )
    parser.add_argument(
        "--threshold", "-t",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Match score threshold (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Concurrent search threads (default: {DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process first N probes (useful for a quick smoke test)",
    )

    args = parser.parse_args()

    output_path = args.output or f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    # ── Load pairs ────────────────────────────────────────────────────────────
    if args.input:
        print(f"Loading probe pairs from CSV : {args.input}")
        pairs = load_pairs_from_csv(args.input)
    else:
        print(f"Loading probe images from dir: {args.probe_dir}")
        pairs = load_pairs_from_directory(args.probe_dir)

    if not pairs:
        print("ERROR: No valid probe pairs found. Check your input.")
        sys.exit(1)

    if args.limit:
        pairs = pairs[: args.limit]
        print(f"--limit applied: processing {len(pairs)} of available probes")

    print()
    print(f"  Gallery        : {args.gallery}")
    print(f"  Max candidates : {MAX_CANDIDATES}")
    print(f"  Threshold      : {args.threshold}")
    print(f"  Workers        : {args.workers}")
    print(f"  Total probes   : {len(pairs)}")
    print(f"  Output file    : {output_path}")
    print()
    print("Starting searches... (Ctrl+C to abort — partial results are saved)")
    print("-" * 62)

    results = []
    write_lock = threading.Lock()
    completed = 0
    total = len(pairs)

    t_start = time.perf_counter()

    with open(output_path, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        writer.writeheader()
        out_f.flush()

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_pair = {
                executor.submit(search_probe, probe_path, mate_id, args.gallery, args.threshold): (probe_path, mate_id)
                for probe_path, mate_id in pairs
            }

            try:
                for future in as_completed(future_to_pair):
                    result = future.result()
                    results.append(result)

                    with write_lock:
                        writer.writerow(result)
                        out_f.flush()
                        completed += 1

                    pos_str = str(result["mate_position"]) if result["mate_position"] != "" else "not_found"
                    rt_str = f"{result['response_time_ms']:.0f}ms" if result["response_time_ms"] != "" else "N/A"
                    status = "OK" if not result["error"] else f"ERR"
                    print(
                        f"  [{completed:>6}/{total}]  "
                        f"{result['probe_file']:<35}  "
                        f"rank={pos_str:<10}  "
                        f"rt={rt_str:<10}  "
                        f"{status}"
                        + (f": {result['error'][:60]}" if result["error"] else "")
                    )

            except KeyboardInterrupt:
                print("\n[INTERRUPTED] Partial results have been saved.")

    elapsed = time.perf_counter() - t_start
    print_summary(results, elapsed, output_path)


if __name__ == "__main__":
    main()
