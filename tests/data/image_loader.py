# -*- coding: utf-8 -*-
"""
image_loader.py — Load the FaceMatcher image manifest for tests.

Public API:
    from tests.data.image_loader import ImageManifest, load_manifest

    manifest = load_manifest()              # loads tests/data/images.json
    img      = manifest.by_id('00004A97')   # look up by ID
    probe    = manifest.random_image()      # pick one at random
    pairs    = manifest.by_subject('sub01') # all images for one subject
    sample   = manifest.sample(10)          # random subset

Each image object is a plain dict:
    {
        "id":         "00004A97-238D-4A01-A5A8-FEE9A5461856",
        "filename":   "00004A97-238D-4A01-A5A8-FEE9A5461856.jpg",
        "subject_id": null,
        "base64":     "/9j/4AAQ..."
    }
"""

import json
import os
import random
from pathlib import Path
from typing import Optional

_DEFAULT_MANIFEST = Path(__file__).parent / 'images.json'


class ImageManifest:
    def __init__(self, data: dict):
        self._images: list[dict] = data['images']
        self._by_id:  dict[str, dict] = {img['id']: img for img in self._images}
        self._by_subject: dict[str, list[dict]] = {}
        for img in self._images:
            sid = img.get('subject_id')
            if sid:
                self._by_subject.setdefault(sid, []).append(img)

        self.version      = data.get('version', '1.0')
        self.generated_at = data.get('generated_at', '')
        self.source_dir   = data.get('source_dir', '')
        self.count        = data['count']

    # ── Lookups ───────────────────────────────────────────────────────────────

    def by_id(self, image_id: str) -> Optional[dict]:
        return self._by_id.get(image_id)

    def by_subject(self, subject_id: str) -> list[dict]:
        return self._by_subject.get(subject_id, [])

    def subjects(self) -> list[str]:
        return list(self._by_subject.keys())

    def all_images(self) -> list[dict]:
        return self._images

    # ── Sampling ──────────────────────────────────────────────────────────────

    def random_image(self, seed: Optional[int] = None) -> dict:
        rng = random.Random(seed)
        return rng.choice(self._images)

    def sample(self, n: int, seed: Optional[int] = None) -> list[dict]:
        rng = random.Random(seed)
        return rng.sample(self._images, min(n, len(self._images)))

    def first(self, n: int = 1) -> list[dict]:
        return self._images[:n]

    # ── Base64 convenience ───────────────────────────────────────────────────

    def base64(self, image_id: str) -> Optional[str]:
        img = self.by_id(image_id)
        return img['base64'] if img else None

    def __len__(self):
        return len(self._images)

    def __repr__(self):
        return (
            f'ImageManifest(count={self.count}, '
            f'subjects={len(self._by_subject)}, '
            f'generated_at={self.generated_at!r})'
        )


_manifest_cache: dict[str, ImageManifest] = {}


def load_manifest(path: Optional[str] = None) -> ImageManifest:
    """
    Load the JSON manifest once and cache it for the process lifetime.

    Args:
        path: Override path to images.json. Defaults to tests/data/images.json.
    """
    resolved = str(Path(path).resolve() if path else _DEFAULT_MANIFEST)

    if resolved not in _manifest_cache:
        if not os.path.exists(resolved):
            raise FileNotFoundError(
                f'Image manifest not found: {resolved}\n'
                f'Generate it first:\n'
                f'    python scripts/generate_image_manifest.py\n'
            )
        with open(resolved, encoding='utf-8') as f:
            data = json.load(f)
        _manifest_cache[resolved] = ImageManifest(data)

    return _manifest_cache[resolved]
