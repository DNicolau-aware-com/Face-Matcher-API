# -*- coding: utf-8 -*-
"""
Shared helpers for the FaceMatcher test suite.

All functions are lru_cache'd — one HTTP call per process, result shared
across every test file that imports them.
"""

import requests
from functools import lru_cache
from config import BASE_URL, HEADERS


@lru_cache(maxsize=1)
def service_version() -> str:
    """Return the service version string from GET /facematch/version."""
    try:
        r = requests.get(f'{BASE_URL}/facematch/version', headers=HEADERS, timeout=5)
        if r.status_code == 200:
            return r.json().get('version', 'unknown')
    except Exception:
        pass
    return 'unknown'


@lru_cache(maxsize=1)
def service_algorithm() -> str:
    """Return the active algorithm from GET /facematch/health (e.g. 'f500', 'f200')."""
    try:
        r = requests.get(f'{BASE_URL}/facematch/health', headers=HEADERS, timeout=5)
        if r.status_code == 200:
            return r.json().get('algorithm', 'unknown')
    except Exception:
        pass
    return 'unknown'
