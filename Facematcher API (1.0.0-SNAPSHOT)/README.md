# Milvus Face Matcher API — Test Suite

Automated pytest test suite for the **Milvus Face Matcher API** (v1.0.0-SNAPSHOT).
Covers galleries, enrollment, search, verify/compare, bulk enrollment, admin operations, and negative cases.

---

## Project Structure

```
Milvus Facematcher API (1.0.0-SNAPSHOT)/
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
    └── system/                # Health check and version
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

All configuration is stored in a single `.env` file located **one level above** this folder:

```
AWRNSS-AUT/
├── .env                                          ← put your config here
└── Milvus Facematcher API (1.0.0-SNAPSHOT)/
```

### Required `.env` keys

```env
BASE_URL=https://your-facematcher-host.com
x-api-key=your-api-key

# Face images as base64-encoded strings
IMAGE_DAN_FACE=<base64>
IMAGE_JOHN_FACE=<base64>
IMAGE_JANE_FACE=<base64>
IMAGE_PART_FACE=<base64>
IMAGE_L_FACE=<base64>
IMAGE_R_FACE=<base64>
IMAGE_TWO_SPOOF=<base64>

# Optional — auto-populated by test_create_enrollment_job
JOB_ID=
```

> Images must be base64-encoded JPEG/PNG strings (no `data:image/...` prefix).

---

## Running the Tests

All commands must be run from inside the project folder:

```bash
cd "Milvus Facematcher API (1.0.0-SNAPSHOT)"
```

### Single run
```bash
python -m pytest requests/ -v --tb=short
```

### Stability runner (repeats N times)
```bash
python run_suite.py              # 10 runs (default)
python run_suite.py --count 3   # 3 runs
python run_suite.py --count 1 --verbose   # 1 run with full pytest output
pytest requests -v -s --html=report.html --self-contained-html
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

## Test Inventory (39 tests)

| Folder | File | Test(s) |
|---|---|---|
| Admin | test_delete_orphans.py | Delete orphaned enrollments |
| Admin | test_get_queue_status.py | Get processing queue status |
| Admin | test_retry_queue.py | Retry failed queue items |
| Admin | test_validate_gallery.py | Validate gallery integrity |
| Bulk Enrollment | test_create_enrollment_job.py | Create bulk enrollment job |
| Bulk Enrollment | test_delete_job.py | Delete job (valid + invalid ID) |
| Bulk Enrollment | test_enroll_bulk_images.py | Bulk enroll from image list |
| Bulk Enrollment | test_enroll_bulk_templates.py | Bulk enroll from template list |
| Bulk Enrollment | test_get_job_status.py | List all jobs |
| Bulk Enrollment | test_list_jobs.py | List jobs with filters |
| Negative Tests | test_400_bad_request.py | Missing fields, invalid payloads |
| Negative Tests | test_404_not_found.py | Nonexistent gallery / enrollment / job |
| Negative Tests | test_409_conflict.py | Duplicate identifier enrollment |
| Search(1N) | test_search.py | 1-to-N face search |
| Verify(1 to 1) | test_verify_image_vs_enrolled_identity.py | Compare image vs enrolled face |
| Verify(1 to 1) | test_verify_image_vs_image.py | Compare image vs image (same + different) |
| enrollment | test_create_gallery_and_enroll_all_faces.py | Enroll all configured images |
| enrollment | test_delete_an_enrollment_from_a_gallery.py | Delete a single enrollment |
| enrollment | test_enroll_a_face_into_a_gallery.py | Enroll one face |
| enrollment | test_enroll_twospoof_into_a_gallery.py | Enroll a two-face (spoof) image |
| galleries | test_create_a_gallery.py | Create a gallery |
| galleries | test_delete_a_gallery.py | Delete gallery (isolated + create-and-delete) |
| galleries | test_delete_an_enrollment_from_a_gallery.py | Delete enrollment from gallery |
| galleries | test_list_galleries.py | List all galleries |
| matching | test_search_for_face_candidates.py | Search within session gallery |
| matching | test_verify_a_face.py | Verify face against enrolled identity |
| system | test_check_health.py | Health endpoint |
| system | test_check_version.py | Version endpoint |

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

### Dynamic identifiers
- `random_uuid` fixture — function-scoped, used for gallery CRUD tests to avoid naming conflicts
- `unique_identifier` fixture — session-scoped enrollment ID (`enroll_XXXXXXXX`), stable within a run
- Bulk enrollment uses IMAGES dict keys (`dan_face`, `john_face`, etc.) as identifiers

### Test execution order
pytest runs folders alphabetically. The suite is designed to work in this order:
```
Admin → Bulk Enrollment → Negative Tests → Search(1N) → Verify(1 to 1)
→ enrollment → galleries → matching → system
```
Tests that run before enrollment (e.g. Verify) self-enroll a temporary identity and clean up after asserting.
