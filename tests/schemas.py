# -*- coding: utf-8 -*-
"""
schemas.py — JSON Schema definitions for every FaceMatcher API response.

Usage in any test:
    from tests.schemas import assert_schema, SEARCH_SCHEMA, COMPARE_ENROLLED_SCHEMA
    assert_schema(r.json(), COMPARE_ENROLLED_SCHEMA, label='compare enrolled')

assert_schema() raises AssertionError on failure with a human-readable diff showing
exactly which field is missing, wrong type, or out of range.
"""

from jsonschema import validate, ValidationError


# ── Reusable sub-schemas ──────────────────────────────────────────────────────

TIMING_SCHEMA = {
    'type': 'object',
    'required': ['totalMs'],
    'properties': {
        'totalMs':              {'type': ['number', 'null']},
        'templateGenerationMs': {'type': ['number', 'null']},
        'milvusSearchMs':       {'type': ['number', 'null']},
        'scoringMs':            {'type': ['number', 'null']},
        'dbLookupMs':           {'type': ['number', 'null']},
    },
}

CANDIDATE_SCHEMA = {
    'type': 'object',
    'required': ['id', 'score', 'match'],
    'properties': {
        'id':    {'type': 'string', 'minLength': 1},
        'score': {'type': 'number', 'minimum': 0},
        'match': {'type': 'boolean'},
    },
}


# ── Endpoint schemas ──────────────────────────────────────────────────────────

HEALTH_SCHEMA = {
    'type': 'object',
    'required': ['status', 'algorithm', 'vectorDim', 'sdk', 'milvus', 'database'],
    'properties': {
        'status':    {'type': 'string', 'enum': ['healthy', 'degraded', 'unhealthy']},
        'algorithm': {'type': 'string', 'minLength': 1},
        'vectorDim': {'type': 'integer', 'minimum': 1},
        'sdk':       {'type': 'string'},
        'milvus':    {'type': 'string'},
        'database':  {'type': 'string'},
    },
    'additionalProperties': False,
}

VERSION_SCHEMA = {
    'type': 'object',
    'required': ['version'],
    'properties': {
        'version': {'type': 'string', 'minLength': 1},
    },
    'additionalProperties': False,
}

ENROLL_SCHEMA = {
    'type': 'object',
    'required': ['success', 'identifier', 'gallery'],
    'properties': {
        'success':    {'type': 'boolean'},
        'identifier': {'type': 'string', 'minLength': 1},
        'gallery':    {'type': 'string', 'minLength': 1},
        'message':    {'type': ['string', 'null']},
    },
}

# Compare — image vs image.
# No candidate reference is expected: probe and candidate are both anonymous images.
COMPARE_IMAGE_SCHEMA = {
    'type': 'object',
    'required': ['score', 'match'],
    'properties': {
        'score':  {'type': 'number', 'minimum': 0},
        'match':  {'type': 'boolean'},
        'timing': TIMING_SCHEMA,
    },
}

# Compare — image vs enrolled identity.
# Response MUST echo back candidateId and candidateGallery so that:
#   1. API consumers know which enrolled template was compared.
#   2. Audit logs can record the full transaction context.
# NOTE: As of 2026-05-01 the live service does NOT return these fields.
#       Tests using this schema will FAIL until the server is fixed.
COMPARE_ENROLLED_SCHEMA = {
    'type': 'object',
    'required': ['score', 'match', 'candidateId', 'candidateGallery'],
    'properties': {
        'score':            {'type': 'number', 'minimum': 0},
        'match':            {'type': 'boolean'},
        'candidateId':      {'type': 'string', 'minLength': 1},
        'candidateGallery': {'type': 'string', 'minLength': 1},
        'timing':           TIMING_SCHEMA,
    },
}

SEARCH_SCHEMA = {
    'type': 'object',
    'required': ['candidates'],
    'properties': {
        'candidates': {
            'type':  'array',
            'items': CANDIDATE_SCHEMA,
        },
        'timing': TIMING_SCHEMA,
    },
}


# ── Validation helper ─────────────────────────────────────────────────────────

# ── Error response schemas ────────────────────────────────────────────────────

# 400 / 404 — application-level error returned by the FaceMatcher service.
# Shape: {"error": "Bad request"|"Not found", "message": "<detail string>"}
APP_ERROR_SCHEMA = {
    'type': 'object',
    'required': ['error', 'message'],
    'properties': {
        'error':   {'type': 'string', 'minLength': 1},
        'message': {'type': 'string', 'minLength': 1},
    },
    'additionalProperties': False,
}

# 422 — FastAPI request validation error.
# Shape: {"detail": [{"type": "missing", "loc": [...], "msg": "...", "input": ...}]}
_VALIDATION_DETAIL_ITEM = {
    'type': 'object',
    'required': ['type', 'loc', 'msg'],
    'properties': {
        'type':  {'type': 'string'},
        'loc':   {'type': 'array', 'minItems': 1},
        'msg':   {'type': 'string', 'minLength': 1},
        'input': {},
    },
}

VALIDATION_ERROR_SCHEMA = {
    'type': 'object',
    'required': ['detail'],
    'properties': {
        'detail': {
            'type':     'array',
            'minItems': 1,
            'items':    _VALIDATION_DETAIL_ITEM,
        },
    },
    'additionalProperties': False,
}

# 200 — GET /facematch/admin/validate/{gallery}
# Returns counts even when the gallery does not exist (all zeros).
VALIDATE_GALLERY_SCHEMA = {
    'type': 'object',
    'required': ['gallery', 'healthy', 'sqlCount', 'milvusCount',
                 'missingInMilvus', 'orphansInMilvus', 'missingIds', 'orphanIds'],
    'properties': {
        'gallery':         {'type': 'string'},
        'healthy':         {'type': 'boolean'},
        'sqlCount':        {'type': 'integer', 'minimum': 0},
        'milvusCount':     {'type': 'integer', 'minimum': 0},
        'missingInMilvus': {'type': 'integer', 'minimum': 0},
        'orphansInMilvus': {'type': 'integer', 'minimum': 0},
        'missingIds':      {'type': 'array'},
        'orphanIds':       {'type': 'array'},
    },
}


# ── Validation helper ─────────────────────────────────────────────────────────

def assert_schema(body, schema, label='response'):
    """
    Validate *body* against *schema*.
    Raises AssertionError with a clear diff message on any violation.
    """
    try:
        validate(instance=body, schema=schema)
    except ValidationError as exc:
        path = ' -> '.join(str(p) for p in exc.absolute_path) or '(root)'
        raise AssertionError(
            f'\nSchema validation FAILED for: {label}'
            f'\n  Path    : {path}'
            f'\n  Problem : {exc.message}'
            f'\n  Body    : {body}'
        ) from None
