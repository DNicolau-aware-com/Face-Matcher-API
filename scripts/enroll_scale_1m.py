#!/usr/bin/env python3
"""
enroll_scale_1m.py — Build a gallery via export/batch + enroll/bulk

Benchmarked throughput on this server:
  export/batch  : ~57 img/sec (sequential batches of 50, 1 worker)
  enroll/bulk   : ~8 ms/template (pure DB write, no ML inference)

Phases
──────
  Phase 1 — Export    POST /facematch/admin/export/batch  (max 50 images/req)
                       Converts local images to face templates.
                       1 sequential worker (concurrent requests overload server).
                       Templates saved to --cache file — skip on reruns with
                       --skip-export.
                       41K images ≈ 12 min.

  Phase 2 — Enroll    POST /facematch/admin/enroll/bulk
                       Enroll the cached templates into the gallery.
                       Fast DB writes, supports many workers.
                       41K templates ≈ 2–3 min.

  Phase 3 — Multiply  POST /facematch/admin/enroll/bulk  (re-enroll with prefix)
                       Re-enroll cached templates with round-number ID prefixes
                       (r002_, r003_, ...) until gallery reaches --target.
                       958K extra templates ≈ 15–20 min.
                       Skip with --no-multiply.

  Phase 4 — Search    python scripts/lasd_mated_pair_test.py  (optional)
                       Run automatically with --run-search.

Total for 1M gallery + search: ~30–40 min.

Usage
─────
  Full run to 1M + search:
    python scripts/enroll_scale_1m.py --fresh --run-search

  Export + enroll 41K only (no multiply):
    python scripts/enroll_scale_1m.py --fresh --no-multiply

  Resume multiply (export already cached):
    python scripts/enroll_scale_1m.py --skip-export

  Search only (gallery already built):
    python scripts/enroll_scale_1m.py --search-only
"""

import argparse
import base64
import importlib.util
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import BASE_URL, HEADERS

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_GALLERY      = "test1m"
DEFAULT_TARGET       = 1_000_000
DEFAULT_IMAGES_DIR   = r"C:\Users\dnicolau\Desktop\images"
DEFAULT_GALLERY_XLSX = r"C:\Users\dnicolau\Downloads\lasd_gallery.xlsx"
DEFAULT_PROBES_XLSX  = r"C:\Users\dnicolau\Downloads\lasd_probes.xlsx"
DEFAULT_CACHE        = "templates_cache.json"
DEFAULT_OUTPUT       = "test1m_search_results.csv"
EXPORT_BATCH_SIZE    = 50    # API hard limit
ENROLL_BATCH_SIZE    = 500   # templates per bulk enroll request
ENROLL_WORKERS       = 8     # concurrent bulk-enroll workers
EXPORT_TIMEOUT       = 300   # seconds per export request
ENROLL_TIMEOUT       = 120   # seconds per bulk enroll request
IMAGE_EXTENSIONS     = {".jpg", ".jpeg", ".png", ".bmp"}


def url(path: str) -> str:
    return f"{BASE_URL}/facematch{path}"


# ── Gallery helpers ───────────────────────────────────────────────────────────

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
        print(f"  Gallery '{name}' not found.")
    else:
        print(f"  WARN {r.status_code}: {r.text[:80]}", file=sys.stderr)


def gallery_face_count(name: str) -> int:
    r = requests.get(url("/galleries"), headers=HEADERS,
                     params={"size": 200}, timeout=10)
    r.raise_for_status()
    for g in r.json().get("content", []):
        if g["name"] == name:
            return g["faceCount"]
    return 0


# ── Phase 1: Export images → templates ───────────────────────────────────────

def load_gallery_stems(gallery_xlsx: str, images_dir: str) -> set[str]:
    """Return the set of filename stems listed in the gallery xlsx that exist locally."""
    import openpyxl
    wb = openpyxl.load_workbook(gallery_xlsx, read_only=True, data_only=True)
    ws = wb.active
    headers = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows())]
    file_col = headers.index("File") if "File" in headers else None
    if file_col is None:
        raise RuntimeError("Column 'File' not found in gallery xlsx")
    stems = set()
    img_dir = Path(images_dir)
    for row in ws.iter_rows(min_row=2, values_only=True):
        val = row[file_col]
        if val:
            stem = Path(str(val)).stem
            for ext in IMAGE_EXTENSIONS:
                if (img_dir / f"{stem}{ext}").exists():
                    stems.add(stem)
                    break
    wb.close()
    return stems


def phase1_export(images_dir: str, cache_file: str,
                  gallery_xlsx: str = "") -> list[dict]:
    """
    Export gallery images to face templates via export/batch.
    If gallery_xlsx is given, only exports images listed there.
    Uses 1 sequential worker (concurrent requests overload the server).
    Saves results to cache_file so this phase can be skipped on reruns.
    Returns list of {identifier, template} dicts.
    """
    cache_path = Path(cache_file)
    if cache_path.exists():
        print(f"  Loading cached templates from {cache_file} ...")
        with open(cache_path, encoding="utf-8") as f:
            templates = json.load(f)
        print(f"  Loaded {len(templates):,} cached templates — skipping export.")
        return templates

    img_dir = Path(images_dir)

    if gallery_xlsx and Path(gallery_xlsx).exists():
        print(f"  Filtering to gallery images from: {gallery_xlsx}")
        gallery_stems = load_gallery_stems(gallery_xlsx, images_dir)
        print(f"  Gallery stems found locally: {len(gallery_stems):,}")
        all_images = sorted(
            p for p in img_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            and p.stem in gallery_stems
        )
    else:
        all_images = sorted(
            p for p in img_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )

    total = len(all_images)
    batches = [all_images[i: i + EXPORT_BATCH_SIZE]
               for i in range(0, total, EXPORT_BATCH_SIZE)]

    print(f"  Images      : {total:,}")
    print(f"  Batches     : {len(batches):,}  (up to {EXPORT_BATCH_SIZE}/request)")
    print(f"  Workers     : 1  (sequential — server rejects concurrent export requests)")
    print(f"  Est. time   : ~{total/57/60:.0f} min  (@57 img/sec)")

    # Load partial cache so interrupted runs resume from where they left off
    partial_cache = Path(str(cache_path) + ".partial")
    templates: list[dict] = []
    already_exported: set[str] = set()
    if partial_cache.exists():
        with open(partial_cache, encoding="utf-8") as f:
            templates = json.load(f)
        already_exported = {t["identifier"] for t in templates}
        print(f"  Resuming from partial cache: {len(templates):,} templates already done.")
        batches = [b for b in batches if not all(p.stem in already_exported for p in b)]
        print(f"  Remaining batches: {len(batches):,}")

    done = len(already_exported)
    failed_imgs = 0
    t_start = time.perf_counter()

    for batch_num, batch in enumerate(batches, start=1):
        items = []
        for p in batch:
            if p.stem in already_exported:
                continue
            try:
                b64 = base64.b64encode(open(p, "rb").read()).decode()
                items.append({"identifier": p.stem, "image": b64})
            except Exception:
                failed_imgs += 1

        if not items:
            done += len(batch)
            continue

        try:
            r = requests.post(url("/admin/export/batch"), headers=HEADERS,
                              json={"images": items}, timeout=EXPORT_TIMEOUT)
            if r.status_code == 200:
                for res in r.json().get("results", []):
                    if res.get("success") and res.get("template"):
                        templates.append({"identifier": res["identifier"],
                                          "template":   res["template"]})
                    else:
                        failed_imgs += 1
            else:
                failed_imgs += len(items)
        except Exception as exc:
            print(f"\n  WARN batch failed: {exc}", file=sys.stderr)
            failed_imgs += len(items)

        done += len(batch)
        elapsed = time.perf_counter() - t_start
        rate = (done - len(already_exported)) / elapsed if elapsed > 0 else 0
        eta  = (total - done) / rate if rate > 0 else 0
        print(f"  {done:>7,}/{total:,}  templates={len(templates):,}  "
              f"failed={failed_imgs}  {rate:.1f} img/sec  ETA ~{eta/60:.0f}min",
              flush=True)

        # Save partial cache every 20 batches (~1000 images) so we can resume if interrupted
        if batch_num % 20 == 0:
            with open(partial_cache, "w", encoding="utf-8") as f:
                json.dump(templates, f)

    # Save final cache and remove partial
    print(f"  Saving {len(templates):,} templates to {cache_file} ...")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(templates, f)
    if partial_cache.exists():
        partial_cache.unlink()
    print(f"  Cache saved.")
    return templates


# ── Phase 2: Enroll templates into gallery ───────────────────────────────────

def enroll_bulk(gallery: str, items: list[dict]) -> tuple[int, int]:
    """POST one bulk-enroll request. Returns (enrolled, failed)."""
    try:
        r = requests.post(url("/admin/enroll/bulk"), headers=HEADERS,
                          json={"items": items, "gallery": gallery},
                          timeout=ENROLL_TIMEOUT)
        if r.status_code == 200:
            body = r.json()
            return body.get("enrolled", 0), body.get("failed", 0)
        return 0, len(items)
    except Exception:
        return 0, len(items)


def phase2_enroll(gallery: str, templates: list[dict],
                  id_prefix: str = "") -> tuple[int, int]:
    """
    Enroll a list of templates into gallery using concurrent bulk requests.
    id_prefix: prepended to each identifier (e.g. "r002_" for multiply rounds).
    Returns (enrolled, failed).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    items = [
        {"identifier": id_prefix + t["identifier"], "template": t["template"]}
        for t in templates
    ]
    batches = [items[i: i + ENROLL_BATCH_SIZE]
               for i in range(0, len(items), ENROLL_BATCH_SIZE)]

    total_enrolled = total_failed = 0
    t_start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=ENROLL_WORKERS) as pool:
        futures = [pool.submit(enroll_bulk, gallery, b) for b in batches]
        for fut in as_completed(futures):
            ok, fail = fut.result()
            total_enrolled += ok
            total_failed   += fail

    elapsed = time.perf_counter() - t_start
    rate = total_enrolled / elapsed if elapsed > 0 else 0
    label = f"r{id_prefix.strip('_')}" if id_prefix else "base"
    print(f"  [{label}]  enrolled={total_enrolled:,}  failed={total_failed:,}  "
          f"{rate:.0f} tmpl/sec  ({elapsed:.1f}s)", flush=True)
    return total_enrolled, total_failed


# ── Phase 3: Multiply to target ───────────────────────────────────────────────

def phase3_multiply(gallery: str, templates: list[dict],
                    current_count: int, target: int) -> None:
    needed       = target - current_count
    per_round    = len(templates)
    rounds       = -(-needed // per_round)   # ceiling division
    est_min      = (needed * 0.008) / ENROLL_WORKERS / 60

    print(f"  Current : {current_count:,}")
    print(f"  Target  : {target:,}")
    print(f"  Needed  : {needed:,}  ({rounds} round(s) of {per_round:,})")
    print(f"  Est.    : ~{est_min:.0f} min  (@8ms/template, {ENROLL_WORKERS} workers)")

    total_added = 0
    for round_num in range(2, 2 + rounds):
        if total_added >= needed:
            break
        still_needed  = needed - total_added
        round_tmpls   = templates[: min(per_round, still_needed)]
        prefix        = f"r{round_num:03d}_"
        ok, _         = phase2_enroll(gallery, round_tmpls, id_prefix=prefix)
        total_added  += ok

    final = gallery_face_count(gallery)
    print(f"  Gallery count after multiply: {final:,}")


# ── Phase 4: Search ───────────────────────────────────────────────────────────

def phase4_search(gallery: str, images_dir: str, gallery_xlsx: str,
                  probes_xlsx: str, workers: int, output: str) -> None:
    spec = importlib.util.spec_from_file_location(
        "lasd_mated_pair_test",
        Path(__file__).parent / "lasd_mated_pair_test.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    images_path = Path(images_dir)
    gallery_rows = mod.load_xlsx(gallery_xlsx)
    probe_rows   = mod.load_xlsx(probes_xlsx)

    person_to_gallery: dict[str, set[str]] = {}
    for row in gallery_rows:
        file_val  = row.get("File", "") or ""
        person_id = str(row.get("PersonID", "")).strip()
        stem      = Path(file_val).stem
        if (images_path / f"{stem}.jpg").exists():
            person_to_gallery.setdefault(person_id, set()).add(stem)

    probe_items = []
    for row in probe_rows:
        file_val  = row.get("File", "") or ""
        person_id = str(row.get("PersonID", "")).strip()
        stem      = Path(file_val).stem
        local     = images_path / f"{stem}.jpg"
        if local.exists():
            probe_items.append((stem, local, person_id,
                                person_to_gallery.get(person_id, set())))

    print(f"  Probes: {len(probe_items):,}")
    results = mod.run_searches(gallery, probe_items,
                               workers=workers, threshold=0.0)
    mod.write_csv(results, Path(output))
    mod.print_search_summary(results)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Export + bulk-enroll gallery, optionally multiply to 1M and search",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--gallery",       default=DEFAULT_GALLERY)
    p.add_argument("--target",        type=int, default=DEFAULT_TARGET,
                   help="Target face count for multiply phase")
    p.add_argument("--images-dir",    default=DEFAULT_IMAGES_DIR,
                   help="Local images directory")
    p.add_argument("--cache",         default=DEFAULT_CACHE,
                   help="Template cache JSON file (reused across runs)")
    p.add_argument("--gallery-xlsx",  default=DEFAULT_GALLERY_XLSX)
    p.add_argument("--probes-xlsx",   default=DEFAULT_PROBES_XLSX)
    p.add_argument("--workers",       type=int, default=ENROLL_WORKERS,
                   help="Workers for bulk enroll and search phases")
    p.add_argument("--output",        default=DEFAULT_OUTPUT,
                   help="Search results CSV")
    p.add_argument("--fresh",         action="store_true",
                   help="Delete and recreate gallery")
    p.add_argument("--skip-export",   action="store_true",
                   help="Skip Phase 1 — load templates from --cache")
    p.add_argument("--no-multiply",   action="store_true",
                   help="Skip Phase 3 — enroll 41K only, do not multiply to 1M")
    p.add_argument("--run-search",    action="store_true",
                   help="Run 1:N search after enrollment")
    p.add_argument("--search-only",   action="store_true",
                   help="Skip enrollment phases, run search only")
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    print("Enroll Scale Gallery  —  export/batch + enroll/bulk")
    print(f"  Service  : {BASE_URL}")
    print(f"  Gallery  : {args.gallery}")
    print(f"  Target   : {args.target:,}")
    print(f"  Cache    : {args.cache}")
    print(f"  Output   : {args.output}")

    try:
        h = requests.get(url("/health"), headers=HEADERS, timeout=10)
        print(f"  Health   : {h.json().get('status', 'ok')}")
    except Exception as exc:
        print(f"  WARN health: {exc}", file=sys.stderr)

    if args.search_only:
        print(f"\n{'='*62}\n  Phase 4 — 1:N Search\n{'='*62}")
        phase4_search(args.gallery, args.images_dir, args.gallery_xlsx,
                      args.probes_xlsx, args.workers, args.output)
        return

    # Gallery setup
    if args.fresh:
        print(f"\n[Gallery] Resetting '{args.gallery}' ...")
        delete_gallery(args.gallery)
        time.sleep(0.5)
    create_gallery(args.gallery)

    # Phase 1 — Export
    print(f"\n{'='*62}\n  Phase 1 — Export Images to Templates\n{'='*62}")
    if args.skip_export:
        cache_path = Path(args.cache)
        if not cache_path.exists():
            print(f"  ERROR: cache not found: {cache_path}", file=sys.stderr)
            sys.exit(1)
        with open(cache_path, encoding="utf-8") as f:
            templates = json.load(f)
        print(f"  Loaded {len(templates):,} templates from cache (--skip-export).")
    else:
        templates = phase1_export(args.images_dir, args.cache,
                                   gallery_xlsx=args.gallery_xlsx)

    if not templates:
        print("  ERROR: no templates. Check --images-dir.", file=sys.stderr)
        sys.exit(1)

    # Phase 2 — Enroll base round
    print(f"\n{'='*62}\n  Phase 2 — Enroll {len(templates):,} Templates\n{'='*62}")
    phase2_enroll(args.gallery, templates, id_prefix="")
    count = gallery_face_count(args.gallery)
    print(f"  Gallery count: {count:,}")

    # Phase 3 — Multiply
    if not args.no_multiply and count < args.target:
        print(f"\n{'='*62}\n  Phase 3 — Multiply to {args.target:,}\n{'='*62}")
        phase3_multiply(args.gallery, templates, count, args.target)

    final = gallery_face_count(args.gallery)
    print(f"\n  Final gallery count: {final:,}")

    # Phase 4 — Search
    if args.run_search:
        print(f"\n{'='*62}\n  Phase 4 — 1:N Search\n{'='*62}")
        phase4_search(args.gallery, args.images_dir, args.gallery_xlsx,
                      args.probes_xlsx, args.workers, args.output)


if __name__ == "__main__":
    main()
