# Milvus Face Matcher API — Test Suite

Automated pytest test suite for the **Milvus Face Matcher API** (v1.0.0-SNAPSHOT).
Covers galleries, enrollment, search, verify/compare, bulk enrollment, admin operations, negative cases, and Swagger-friendly upload endpoints.

**57 tests | 56 passed | 1 skipped**

---

## Project Structure

```
Facematcher API (1.0.0-SNAPSHOT)/
├── config.py                  # Loads .env, exports BASE_URL, HEADERS, IMAGES, ensure_gallery()
├── conftest.py                # pytest fixtures: session_gallery, shared_state, random_uuid, unique_identifier
├── run_suite.py               # Stability runner — repeats the full suite N times
├── pytest.ini                 # pytest config (--import-mode=importlib)
└── requests/
    ├── Admin/                 # Admin operations (queue, orphans, gallery validation)
    ├── Bulk Enrollment/       # Job-based bulk enrollment (create, list, status, delete)
    ├── Negative Tests/        # 400 / 404 / 409 error-case validation
    ├── Search(1N)/            # 1-to-N face search
    ├── Verify(1 to 1)/        # 1-to-1 face comparison (image vs image, image vs enrolled)
    ├── enrollment/            # Single-face enrollment and deletion
    ├── galleries/             # Gallery CRUD
    ├── matching/              # Search and verify against enrolled faces
    ├── system/                # Health check and version
    └── upload/                # Swagger-friendly multipart/form-data upload endpoints
```

---

## Prerequisites

- Python 3.9+
- Install dependencies:
  ```bash
  pip install pytest python-dotenv requests
  ```

---

## Configuration

All configuration is stored in a single `.env` file located **one level above** this folder.
Copy `.env.example` and fill in your values:

```
AWRNSS-AUT/
├── .env                                          ← put your config here
├── .env.example                                  ← template with all keys
└── Facematcher API (1.0.0-SNAPSHOT)/
```

### Required `.env` keys

```env
BASE_URL=https://your-facematcher-host.com
x-api-key=your-api-key

# Face images as base64-encoded strings (no data:image/... prefix)
IMAGE_DAN_FACE=
IMAGE_JOHN_FACE=
IMAGE_JANE_FACE=
IMAGE_PART_FACE=
IMAGE_L_FACE=
IMAGE_R_FACE=
IMAGE_TWO_SPOOF=

# Optional — used by bulk enrollment scan test
SCAN_DIRECTORY=

# Optional — auto-populated by test_create_enrollment_job
JOB_ID=
```

---

## Running the Tests

All commands must be run from inside the project folder:

```bash
cd "Facematcher API (1.0.0-SNAPSHOT)"
```

### Full suite
```bash
python -m pytest requests/ -v --tb=short
```

### Single folder
```bash
python -m pytest requests/upload/ -v -s
```

### With HTML report
```bash
pytest requests -v -s --html=report.html --self-contained-html
```

### Stability runner (repeats N times)
```bash
python run_suite.py              # 10 runs (default)
python run_suite.py --count 3   # 3 runs
python run_suite.py --count 1 --verbose
```

The runner prints a summary table at the end:

```
=================================================================
  SUMMARY  (3 runs)
=================================================================
  Run    Status       Duration
  ------ ---------- ----------
  1      PASSED          41.3s
  2      PASSED          43.0s
  3      PASSED          48.9s
=================================================================
  Passed : 3/3
  Total  : 133.2s
=================================================================
```

---

## Test Inventory (57 tests)

### Admin — 4 tests
Admin endpoints cover background processing queue management and gallery data integrity operations.

| File | Tests | What it checks |
|---|---|---|
| `test_get_queue_status.py` | 1 | `GET /facematch/admin/queue` returns 200 and a valid queue status payload |
| `test_retry_queue.py` | 1 | `POST /facematch/admin/queue/retry` returns 200 and triggers retry of failed queue items |
| `test_delete_orphans.py` | 1 | `DELETE /facematch/admin/orphans/{gallery}` returns 200 and removes enrollments with no corresponding vector |
| `test_validate_gallery.py` | 1 | `GET /facematch/admin/validate/{gallery}` returns 200 and reports gallery integrity counts |

---

### Bulk Enrollment — 19 tests
Covers the job-based async bulk enrollment pipeline: creating jobs, monitoring status, enrolling batches of images or templates, exporting templates, and error handling.

| File | Tests | What it checks |
|---|---|---|
| `test_list_jobs.py` | 1 | `GET /facematch/admin/jobs` returns 200 and lists all enrollment jobs |
| `test_create_enrollment_job.py` | 1 | `POST /facematch/admin/jobs` returns 200, creates a batch job with multiple face images, stores `jobId` in `shared_state` |
| `test_get_job_status.py` | 2 | `GET /facematch/admin/jobs/{jobId}` returns 200 with `jobId`, `status`, `progressPercent` fields; 404 for non-existent job |
| `test_get_job_errors.py` | 3 | `GET /facematch/admin/jobs/{jobId}/errors` returns 200; same with `limit` query param; 404 for non-existent job |
| `test_enroll_bulk_images.py` | 1 | `POST /facematch/admin/enroll/batch-images` returns 200 and bulk enrolls multiple images with `storeImages=true` |
| `test_enroll_bulk_templates.py` | 1 | `POST /facematch/admin/enroll/batch-images` returns 200 and bulk enrolls with `storeImages=false` (template-only) |
| `test_enroll_bulk_by_templates.py` | 1 | `POST /facematch/admin/enroll/bulk` returns 200 and enrolls from pre-extracted biometric templates |
| `test_enroll_bulk_duplicate.py` | 1 | Re-enrolling the same identifiers returns 200 with `enrolled=0` and the expected failure count — confirms duplicate rejection |
| `test_export_batch.py` | 2 | `POST /facematch/admin/export/batch` returns 200 with expected template shape for valid images; returns 400 (or 200 with `success=false`) for invalid base64 |
| `test_enroll_scan.py` | 3 | `POST /facematch/admin/enroll/scan` returns 200 and creates async scan job; 422 when `directory` field is missing; 400 when directory path does not exist on server |
| `test_delete_job.py` | 2 | `DELETE /facematch/admin/jobs/{jobId}` returns 200 for a valid job; 404 for a non-existent job ID |

---

### Negative Tests — 16 tests
Validates that the API returns correct HTTP error codes and structured error bodies for invalid inputs, missing fields, duplicates, and non-existent resources.

| File | Tests | What it checks |
|---|---|---|
| `test_400_bad_request.py` | 5 | Gallery creation without `name` → 422; duplicate gallery name → 400; enrollment without `image` → 422; search without required fields → 422; compare without required fields → 422 |
| `test_404_not_found.py` | 5 | Delete non-existent gallery → 404; delete non-existent enrollment → 404; search non-existent gallery → 400 (validation fires first); validate non-existent gallery → 200 with zero counts; get non-existent job → 404 |
| `test_409_conflict.py` | 1 | Enrolling the same identifier twice returns 409 with `error`/`message` fields; cleans up after |

> **Note:** `test_400_create_gallery_duplicate` is counted in the 400 file but triggers a 400 (not 422) because it passes a valid payload — the server rejects it at the business-logic layer, not the validation layer.

---

### Search(1N) — 1 test
| File | Tests | What it checks |
|---|---|---|
| `test_search.py` | 1 | `POST /facematch/search` returns 200 and a `candidates` array where each item has `id`, `score`, and `match` fields |

---

### Verify(1 to 1) — 6 tests
Covers the compare endpoint in all scenarios: image vs image, image vs enrolled identity, non-matching faces, invalid input, and non-existent candidates.

| File | Tests | What it checks |
|---|---|---|
| `test_verify_image_vs_image.py` | 2 | `POST /facematch/compare` returns 200 with `score`/`match` fields for two different images; same image vs itself returns a high score |
| `test_verify_image_vs_enrolled_identity.py` | 1 | `POST /facematch/compare` returns 200 when probing against an enrolled identity in a gallery |
| `test_verify_negative_cases.py` | 3 | Compare with artificially high threshold returns `match=false`; invalid base64 probe returns 400; non-existent candidate ID returns 404 |

---

### enrollment — 5 tests
| File | Tests | What it checks |
|---|---|---|
| `test_enroll_a_face_into_a_gallery.py` | 1 | `POST /facematch/galleries/{gallery}/enrollments/{id}` returns 200 and enrolls `jane_face`; stores `enrollment_id` in `shared_state` for downstream tests |
| `test_enroll_twospoof_into_a_gallery.py` | 1 | Enrolls a two-face (spoof) image — confirms the API accepts images with two detected faces |
| `test_create_gallery_and_enroll_all_faces.py` | 1 | Iterates over all images configured in `.env` and enrolls each one; accepts 200 (new) or 409 (already enrolled) — seeds the session gallery for search/verify tests |
| `test_delete_an_enrollment_from_a_gallery.py` | 1 | `DELETE /facematch/galleries/{gallery}/enrollments/{id}` returns 204; uses `enrollment_id` from `shared_state` or falls back to a hardcoded ID |

---

### galleries — 6 tests
| File | Tests | What it checks |
|---|---|---|
| `test_create_a_gallery.py` | 1 | `POST /facematch/galleries` returns 200 and creates a gallery with a unique name; stores `gallery_create_test` in `shared_state` |
| `test_delete_a_gallery.py` | 2 | Deletes the gallery created by `test_create_a_gallery` (204); also runs a full create-then-delete lifecycle with a fresh `random_uuid` name |
| `test_list_galleries.py` | 1 | `GET /facematch/galleries` returns 200 with pagination fields (`page`, `size`, `sort`) |
| `test_list_galleries_pagination.py` | 1 | `GET /facematch/galleries?page=0&size=1` verifies `prev=null` for the first page and that the `next` link is present when there is more than one gallery |
| `test_delete_an_enrollment_from_a_gallery.py` | 1 | Self-contained: enrolls `delete_test_jane`, then deletes it (204) — does not rely on prior tests |

---

### matching — 2 tests
| File | Tests | What it checks |
|---|---|---|
| `test_search_for_face_candidates.py` | 1 | `POST /facematch/search` against the session gallery returns 200 and at least one candidate with `id`, `score`, `match` |
| `test_verify_a_face.py` | 1 | `POST /facematch/compare` returns 200 with `score`/`match`; if running standalone it self-enrolls a temporary identity and cleans up after |

---

### system — 2 tests
| File | Tests | What it checks |
|---|---|---|
| `test_check_health.py` | 1 | `GET /facematch/health` returns 200 — confirms the service is up |
| `test_check_version.py` | 1 | `GET /facematch/version` returns 200 — confirms the version endpoint is reachable |

---

### upload — 3 tests
These endpoints accept `multipart/form-data` file uploads instead of base64 JSON, making them usable directly from Swagger UI's "Try it out" feature. They delegate to the same underlying logic as their JSON equivalents.

| Upload Endpoint | Equivalent JSON Endpoint |
|---|---|
| `POST /facematch/upload/galleries/{gallery}/enrollments/{id}` | `POST /facematch/galleries/{gallery}/enrollments/{id}` |
| `POST /facematch/upload/search` | `POST /facematch/search` |
| `POST /facematch/upload/compare` | `POST /facematch/compare` |

Each test decodes the base64 image from `.env` into raw bytes and sends it as a real file. The `Content-Type` header is intentionally omitted so `requests` sets the multipart boundary automatically.

| File | Tests | What it checks |
|---|---|---|
| `test_upload_enroll.py` | 1 | `POST /facematch/upload/galleries/{gallery}/enrollments/{id}` returns 200 with `image` form field; cleans up the enrollment after |
| `test_upload_search.py` | 1 | `POST /facematch/upload/search` returns 200 with `image` file + `gallery`/`maxCandidates`/`threshold` form fields; returns a `candidates` array |
| `test_upload_compare.py` | 1 | `POST /facematch/upload/compare` returns 200 with `probe_image` file + `candidate_id`/`candidate_gallery`/`threshold` form fields; returns `score`/`match` |

---

## Key Design Decisions

### `session_gallery` fixture
A unique gallery (`gallery_YYYYMMDD_HHMMSS`) is created once per pytest session, shared across all enrollment/search/verify tests, and deleted at teardown. This ensures tests never collide with pre-existing server state.

### `shared_state` fixture
A session-scoped `dict` that acts as pytest's equivalent of Postman environment variables. Tests that create resources (galleries, enrollments, jobs) store their IDs here; downstream tests consume them with a fallback chain:
```
shared_state value → .env config value → hardcoded default
```

### `ensure_gallery(name)` helper
Available from `config.py`. Creates a gallery if it doesn't exist (accepts 200 or 400/already-exists). Used by `test_delete_a_gallery` to guarantee the gallery is present before deletion, making the test idempotent across repeated runs.

### Self-contained tests
Every test that requires a pre-condition (an enrolled face, an existing gallery) either:
- Creates it at the start of the test and deletes it at the end, **or**
- Reads from `shared_state` set by an earlier test and falls back gracefully if running in isolation.

This means any individual test file can be run standalone without needing to run the full suite first.

### Dynamic identifiers
- `random_uuid` fixture — function-scoped, used for gallery CRUD tests to avoid naming conflicts
- `unique_identifier` fixture — session-scoped enrollment ID (`enroll_XXXXXXXX`), stable within a run
- Bulk enrollment uses IMAGES dict keys (`dan_face`, `john_face`, etc.) as identifiers

### Test execution order
pytest runs folders alphabetically. The suite is designed to work in this order:
```
Admin → Bulk Enrollment → Negative Tests → Search(1N) → Verify(1 to 1)
→ enrollment → galleries → matching → system → upload
```
Tests that run before enrollment (e.g. Verify) self-enroll a temporary identity and clean up after asserting.
