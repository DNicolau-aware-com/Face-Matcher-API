# Face Matcher — API Reference

Base URL: `http://localhost:8082`
Swagger UI: `http://localhost:8082/docs`

All endpoints are under the `/facematch/` prefix.
All responses include an `x-aware-trace-id` header for request tracing.

---

## Health & Version

### GET /facematch/version

Returns service version.

```json
{"version": "1.0.0"}
```

### GET /facematch/health

Returns service health and configuration summary.

```json
{
  "status": "healthy",
  "algorithm": "f500",
  "vectorDim": 460,
  "sdk": "http://facematcher-sdk:8081/facematcher",
  "milvus": "connected",
  "database": "connected"
}
```

---

## Galleries

### POST /facematch/galleries

Create a gallery.

**Request:**
```json
{"name": "my_gallery"}
```

**Response (200):**
```json
{"name": "my_gallery", "createdAt": "2024-01-15 10:30:00", "faceCount": 0}
```

**Error (400):** Gallery already exists.

### GET /facematch/galleries

List galleries with pagination.

**Query params:** `page` (default 0), `size` (default 20), `sort` (default `createdAt,desc`)

**Response:**
```json
{
  "content": [
    {"name": "my_gallery", "createdAt": "2024-01-15 10:30:00", "faceCount": 42}
  ],
  "totalItems": 1,
  "prev": null,
  "next": null
}
```

### DELETE /facematch/galleries/{galleryName}

Delete a gallery and all its enrollments. Returns **204 No Content**.

---

## Enrollment

### POST /facematch/galleries/{galleryName}/enrollments/{identifier}

Enroll a face image.

**Request:**
```json
{"image": "<BASE64_IMAGE>"}
```

**Response:**
```json
{"success": true, "identifier": "person-001", "gallery": "my_gallery"}
```

### DELETE /facematch/galleries/{galleryName}/enrollments/{identifier}

Delete an enrollment. Returns **204** or **404**.

---

## Search (1:N)

### POST /facematch/search

Search a gallery for matching faces.

**Request:**
```json
{
  "probe": {"image": "<BASE64_IMAGE>"},
  "gallery": "my_gallery",
  "maxCandidates": 10,
  "threshold": 4.0
}
```

**Response:**
```json
{
  "candidates": [
    {"id": "person-001", "score": 12.5, "match": true},
    {"id": "person-002", "score": 2.1, "match": false}
  ]
}
```

- `score` — scoreFmr (-log10(FMR)), higher = better match
- `match` — whether score >= threshold

---

## Verify (1:1)

### POST /facematch/verify

**Image vs enrolled identity:**
```json
{
  "probe": {"image": "<BASE64_IMAGE>"},
  "candidate": {"id": "person-001", "gallery": "my_gallery"},
  "threshold": 4.0
}
```

**Image vs image:**
```json
{
  "probe": {"image": "<BASE64_PROBE>"},
  "candidate": {"image": "<BASE64_CANDIDATE>"},
  "threshold": 4.0
}
```

**Response:**
```json
{"score": 12.5, "match": true}
```

---

## Bulk Enrollment

### POST /facematch/admin/enroll/bulk

Batch enroll with pre-extracted templates.

**Request:**
```json
{
  "items": [
    {"identifier": "person-001", "template": "<BASE64_TEMPLATE>"},
    {"identifier": "person-002", "template": "<BASE64_TEMPLATE>"}
  ],
  "gallery": "my_gallery"
}
```

### POST /facematch/admin/enroll/images

Batch enroll from images (synchronous).

**Request:**
```json
{
  "items": [
    {"identifier": "person-001", "image": "<BASE64_IMAGE>"},
    {"identifier": "person-002", "image": "<BASE64_IMAGE>"}
  ],
  "gallery": "my_gallery",
  "storeImages": true
}
```

### POST /facematch/admin/jobs

Create a background enrollment job.

**Request:**
```json
{
  "items": [
    {"identifier": "person-001", "image": "<BASE64_IMAGE>"}
  ],
  "gallery": "my_gallery"
}
```

### GET /facematch/admin/jobs/{jobId}

Check job status and progress.

### GET /facematch/admin/jobs

List all jobs.

### DELETE /facematch/admin/jobs/{jobId}

Cancel or delete a job.

---

## Admin

### GET /facematch/admin/queue

Retry queue status and statistics.

### POST /facematch/admin/queue/retry

Reset exhausted retry items for re-processing.

### GET /facematch/admin/validate/{gallery}

Check SQL and Milvus sync status for a gallery.

### DELETE /facematch/admin/orphans/{gallery}

Remove orphaned Milvus entries (entries not in SQL).

---

## Request Tracing

Pass `x-aware-trace-id` header for request tracing:
```bash
curl -H "x-aware-trace-id: my-trace-123" http://localhost:8082/facematch/health
```

If omitted, a UUID is auto-generated. The response always includes the trace ID header.

---

## Error Format

All errors follow a consistent format:
```json
{
  "error": "Bad request",
  "message": "Gallery 'test' already exists"
}
```

HTTP status codes used:
- **400** — Bad request / validation error
- **404** — Resource not found
- **409** — Conflict
- **503** — Service unavailable (Milvus/SDK down)
- **500** — Internal server error
