#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_image_manifest.py — Sample images from a folder and build a JSON manifest
for FaceMatcher automated tests.

Usage:
    python scripts/generate_image_manifest.py
    python scripts/generate_image_manifest.py --input C:/path/to/images --count 200
    python scripts/generate_image_manifest.py --input C:/path/to/images --count 200 --env-compat
    python scripts/generate_image_manifest.py --input C:/path/to/images --count 200 --seed 42

Arguments:
    --input       Folder containing .jpg/.png/.jpeg images  [default: C:/Users/dnicolau/Desktop/images]
    --output      Destination JSON manifest                  [default: tests/data/images.json]
    --count       Number of images to sample                 [default: 200]
    --seed        Random seed for reproducible sampling      [default: 42]
    --env-compat  Also write .env-style snippet to stdout
    --all         Include all images (ignores --count)

Subject ID extraction:
    Filenames with underscore pattern   subject001_02.jpg  → subject_id="subject001"
    UUID-style filenames (no underscore) → subject_id=null
    All images in a subfolder named <subject> → subject_id from parent folder name
"""

import argparse
import base64
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
DEFAULT_INPUT  = r'C:\Users\dnicolau\Desktop\images'
DEFAULT_OUTPUT = 'tests/data/images.json'
DEFAULT_COUNT  = 200
DEFAULT_SEED   = 42


def discover_images(root: Path) -> list[Path]:
    """Return all image files under root (recursive)."""
    found = []
    for ext in SUPPORTED_EXTENSIONS:
        found.extend(root.rglob(f'*{ext}'))
        found.extend(root.rglob(f'*{ext.upper()}'))
    return sorted(set(found))


def extract_subject_id(path: Path, root: Path) -> str | None:
    """
    Try to derive a subject ID from the file path.

    Rules (in order):
    1. If the immediate parent folder is not the root → use parent folder name.
       Example: images/subject001/img_01.jpg → subject_id="subject001"
    2. If the stem contains an underscore → use everything before the last underscore.
       Example: subject001_02.jpg → subject_id="subject001"
    3. Otherwise → None (UUID-style filenames have no inherent grouping).
    """
    if path.parent != root:
        return path.parent.name

    stem = path.stem
    if '_' in stem:
        return stem.rsplit('_', 1)[0]

    return None


def image_to_base64(path: Path) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')


def build_manifest(image_paths: list[Path], root: Path, source_dir: str) -> dict:
    images = []
    total = len(image_paths)

    for i, path in enumerate(image_paths, 1):
        if i % 20 == 0 or i == total:
            print(f'  [{i:>3}/{total}] {path.name}', flush=True)

        images.append({
            'id':         path.stem,
            'filename':   path.name,
            'subject_id': extract_subject_id(path, root),
            'base64':     image_to_base64(path),
        })

    return {
        'version':      '1.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_dir':   source_dir,
        'count':        len(images),
        'images':       images,
    }


def write_env_compat(images: list[dict]) -> None:
    """Print IMAGE_<SLUG>=<base64> lines to stdout for backward compatibility."""
    print('\n# ── .env-style snippet (backward compatibility) ──────────────')
    for img in images:
        slug = img['id'].replace('-', '_').upper()
        print(f'IMAGE_{slug}={img["base64"]}')


def main():
    parser = argparse.ArgumentParser(description='Generate FaceMatcher image manifest')
    parser.add_argument('--input',      default=DEFAULT_INPUT,  help='Image source folder')
    parser.add_argument('--output',     default=DEFAULT_OUTPUT, help='Output JSON manifest path')
    parser.add_argument('--count',      type=int, default=DEFAULT_COUNT, help='Number of images to sample')
    parser.add_argument('--seed',       type=int, default=DEFAULT_SEED,  help='Random seed')
    parser.add_argument('--env-compat', action='store_true', help='Print .env snippet to stdout')
    parser.add_argument('--all',        action='store_true',  help='Include every image (no sampling)')
    args = parser.parse_args()

    root = Path(args.input).resolve()
    if not root.is_dir():
        print(f'ERROR: input folder not found: {root}', file=sys.stderr)
        sys.exit(1)

    print(f'Scanning {root} ...')
    all_images = discover_images(root)
    print(f'Found {len(all_images):,} images.')

    if args.all:
        selected = all_images
    elif len(all_images) <= args.count:
        print(f'Fewer than {args.count} images found — using all {len(all_images)}.')
        selected = all_images
    else:
        rng = random.Random(args.seed)
        selected = sorted(rng.sample(all_images, args.count))
        print(f'Sampled {len(selected)} images (seed={args.seed}).')

    print(f'Encoding {len(selected)} images to base64 ...')
    manifest = build_manifest(selected, root, str(root))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    size_mb = out_path.stat().st_size / 1_048_576
    print(f'\nManifest written to: {out_path}  ({size_mb:.1f} MB, {manifest["count"]} images)')

    if args.env_compat:
        write_env_compat(manifest['images'])


if __name__ == '__main__':
    main()
