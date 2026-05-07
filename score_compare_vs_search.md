# FaceMatcher Score Behaviour: 1:1 Compare vs 1:N Search

**System:** FaceMatcher (ROC F200 matcher, Milvus vector database)
**Service:** https://facematcherdemo.knomi.aware.com
**Author:** QA / Integration Team
**Date:** 2026-04-29

---

## Score Definition

The FaceMatcher score `S` is defined as:

```
FMR = 1 / (10^S)
```

| Score (S) | False Match Rate (FMR) | Meaning |
|-----------|----------------------|---------|
| 1.0 | 10% | 1 in 10 |
| 2.0 | 1% | 1 in 100 |
| 3.0 | 0.1% | 1 in 1,000 |
| 4.0 | 0.01% | 1 in 10,000 |
| 5.0 | 0.001% | 1 in 100,000 |
| 7.0 | 0.0001% | 1 in 10,000,000 |
| 16.0 | ~10⁻¹⁶ | Near-certain match |

Higher score = higher confidence = lower false match rate.

> **Recommended starting threshold:** `4.0` (FMR = 0.01%, 1 in 10,000).

---

## 1. Why Scores from 1:1 Compare and 1:N Search Are Not Always Identical

Even for the exact same image pair, scores from the two endpoints can differ. This is expected and by design, not a bug.

### 1:1 Compare — exact computation

- Endpoint: `POST /facematch/compare`
- The probe image and gallery image are both feature-extracted at request time.
- The ROC F200 matcher computes a precise similarity score directly against the single target template.
- No approximation involved — this is a deterministic, exact computation.
- **Result:** the highest-fidelity score available for a pair.

### 1:N Search — ANN retrieval + re-score

- Endpoint: `POST /facematch/search`
- The probe's feature vector is submitted to **Milvus** (vector database).
- Milvus performs an **Approximate Nearest Neighbor (ANN)** search across all indexed templates.
- The top-K candidates are retrieved by vector proximity, then the ROC matcher re-scores each candidate against the probe.
- **Result:** scores are generally very close to the 1:1 score for the same pair, but small differences arise from:

| Source of difference | Typical magnitude |
|----------------------|------------------|
| ANN retrieval uses vector quantization (lossy compression in the index) | ±0.05 – 0.15 |
| Floating-point rounding across different code paths | ±0.01 – 0.05 |
| Feature template stored at enrollment time vs re-extracted at search time | ±0.0 (same template is stored, not re-extracted) |
| Index type configuration (IVF, HNSW, etc.) | ±0.0 – 0.3 depending on index |

> **Key point:** the ROC matcher itself is deterministic. Score variation comes from the ANN layer, not the matcher.

---

## 2. The Role of Milvus and Approximate Nearest Neighbor (ANN) Search

Milvus is a purpose-built vector database that stores biometric feature vectors (embeddings) and retrieves the closest matches using ANN algorithms. At 1M-face scale, exact exhaustive search would be computationally prohibitive; ANN trades a small amount of recall accuracy for orders-of-magnitude speed improvement.

### How ANN works in this context

```
Enrollment:
  Image → Feature extraction (F200) → Feature vector → Milvus index

Search:
  Probe image → Feature extraction (F200) → Query vector
  → Milvus ANN search → Top-K candidate IDs + approximate distances
  → ROC F200 exact re-score each candidate vs probe
  → Return sorted candidate list with final scores
```

### ANN index types and their trade-offs

| Index type | Speed | Recall | Score accuracy |
|------------|-------|--------|----------------|
| FLAT (brute force) | Slow | 100% | Identical to 1:1 |
| IVF_FLAT | Fast | ~95–99% | Very close to 1:1 |
| IVF_SQ8 | Faster | ~94–98% | Small differences due to quantization |
| HNSW | Very fast | ~96–99% | Small differences |

The demo service uses a configuration appropriate for its scale. At 1M faces with the observed ~2.6s latency per search, the system is performing efficient ANN retrieval.

### Key implication: the "missed candidate" problem

ANN does not guarantee finding the true nearest neighbor. If the true mate's vector falls just outside the retrieved top-K cluster:
- It may not appear in the candidate list at all.
- 1:1 Compare would return a high score; 1:N Search would return 0 candidates or rank the mate outside top-100.
- This is not a matcher failure — it is an ANN recall trade-off.

This is one explanation for the ~4.38% not-found rate in our test results: a fraction of those 375 probes may have mates that the ANN search failed to retrieve, even though the 1:1 comparison would score them above threshold.

---

## 3. Acceptable Score Difference (Tolerance Range)

For the ROC F200 / Milvus stack, the following tolerances are considered normal:

| Scenario | Expected score difference (1:1 vs 1:N) |
|----------|----------------------------------------|
| High-scoring genuine pairs (S ≥ 8.0) | ±0.05 – 0.20 |
| Mid-range genuine pairs (S = 4.0 – 8.0) | ±0.10 – 0.30 |
| Near-threshold pairs (S = 3.5 – 5.0) | ±0.10 – 0.50 |
| Non-mates (S < threshold) | Difference less meaningful; both should be below threshold |

**Rule of thumb:** a score difference of **≤ 0.5** between 1:1 and 1:N for the same pair is normal. A difference **> 1.0** warrants investigation.

> **Critical boundary:** if a pair scores `4.2` on 1:1 (match=True) but `3.8` on 1:N (match=False), the system will produce inconsistent decisions. This near-threshold region requires special attention during validation.

---

## 4. Scenarios Where Score Differences Indicate a Real Problem

| Symptom | Likely cause | Investigation |
|---------|-------------|---------------|
| Mate not returned at any rank in 1:N, but 1:1 returns S > threshold | ANN recall failure; identity not indexed | Check enrollment confirmation; verify face count in gallery |
| 1:N score consistently higher than 1:1 for same pair | Index corruption; wrong template stored | Re-enroll affected identity; cross-check template |
| 1:N score is 0 or null | Template not yet indexed (delayed insertion), or identity deleted | Check enrollment response code; wait for index sync |
| Repeated 1:N searches return different scores for same probe | Non-deterministic ANN with very low nprobe setting | Check Milvus search parameters; increase nprobe |
| All 1:N scores suddenly drop by a uniform amount | Index rebuilt with different feature version | Confirm F200 model version matches between enrollment and search |
| Score gap > 2.0 for a high-confidence pair | Different feature model used at enrollment vs search | Verify model version consistency |
| 1:N returns impostor at rank-1 with higher score than true mate | Index collision or ANN misconfiguration | Run 1:1 compare against the impostor; audit index integrity |

---

## 5. Best Practices for Validating Consistency Between Compare and Search

### 5.1 Mated pair consistency test

Select a representative set of known mated pairs (e.g., 100–500 pairs). For each pair:
1. Run `POST /facematch/compare` → record score `S_compare`
2. Run `POST /facematch/search` → find the mate in candidates → record score `S_search`
3. Compute `delta = |S_compare - S_search|`
4. Flag any pair where `delta > 0.5`

```python
# Pseudocode
for probe, gallery_mate in mated_pairs:
    s_compare = compare(probe, gallery_mate)
    s_search  = search(probe, gallery)[rank_of(gallery_mate)]
    delta     = abs(s_compare - s_search)
    if delta > 0.5:
        log_issue(probe, gallery_mate, s_compare, s_search, delta)
```

### 5.2 Rank-1 hit rate vs 1:1 positive rate

The fraction of probes where 1:N rank-1 = mate should be ≥ the fraction that 1:1 scores above threshold. If 1:1 says 97% of pairs are genuine but 1:N rank-1 is only 90%, ANN recall is degraded.

### 5.3 Small gallery sanity test

Before testing at 1M scale, validate with a small gallery (100–1,000 faces):
- Use FLAT index if possible (exact search, no ANN error).
- Confirm 1:1 and 1:N scores are identical or within ±0.05.
- This isolates matcher behaviour from ANN approximation.

### 5.4 Enrollment confirmation check

After enrolling, immediately search the enrolled image as its own probe:
- Expected: rank-1 candidate is the enrolled identity with a very high score (typically S > 12.0 for a self-match).
- If rank-1 is not the self, the template was not indexed correctly.

### 5.5 Threshold boundary probes

Deliberately include probes whose 1:1 score is within ±1.0 of your threshold (e.g., S = 3.0–5.0). These are the highest-risk cases for decision inconsistency. Verify that 1:N decisions agree with 1:1 decisions for these borderline pairs.

---

## 6. How Threshold Should Be Applied Consistently Across Both Workflows

### The threshold is a decision boundary, not a score filter

The score `S` is a continuous value. The threshold converts it into a binary decision:
- `S ≥ threshold` → `match = True`
- `S < threshold` → `match = False`

Both 1:1 Compare and 1:N Search use the same score metric (−log₁₀(FMR)), so the **same threshold applies to both workflows**.

### Applying threshold in 1:1 Compare

```
POST /facematch/compare
Response: { "score": 5.23 }

Decision: 5.23 ≥ 4.0 → MATCH
```

There is no threshold parameter in the compare request — the caller applies the threshold to the returned score.

### Applying threshold in 1:N Search

```
POST /facematch/search
Body: { "threshold": 4.0, "maxCandidates": 100, ... }
Response: candidates[].match = true if score ≥ threshold
```

The threshold is sent in the request and the service returns `match: true/false` per candidate. The score is also returned, so the caller can re-apply a different threshold post-hoc if needed.

### Consistency rule

> **Use the same threshold value in both workflows.** Applying threshold 4.0 in 1:N search and threshold 5.0 in 1:1 compare creates an inconsistency where the same pair receives different verdicts depending on the workflow used.

### Threshold selection guidance

| Use case | Recommended threshold | Rationale |
|----------|-----------------------|-----------|
| General ID verification | 4.0 | FMR = 0.01% (1 in 10,000) — vendor default |
| High-security / law enforcement | 6.0 – 7.0 | FMR = 0.0001% – 0.00001% |
| High-throughput / watchlist | 3.0 – 3.5 | Higher recall, higher FMR accepted |
| Forensic review (all candidates) | 0.0 | Return all; human reviews scores |

> **Important:** threshold controls the False Match Rate (FMR), not the False Non-Match Rate (FNMR). Raising the threshold reduces false matches but increases missed genuine pairs. The trade-off must be calibrated to the operational requirement.

---

## 7. Observed Results from This Test Environment

Based on testing against the demo service:

| Metric | Value |
|--------|-------|
| Gallery | `scale_1m` (1,041,170 faces) |
| 1:N search avg latency (1 worker) | ~2,584 ms |
| Rank-1 accuracy (8,552 probes) | 95.63% |
| Threshold used | 4.0 |
| Errors | 0 (0.00%) |
| Typical score range (genuine, high-quality) | 14.0 – 16.5 |
| Typical score range (near-threshold genuine) | 4.0 – 6.0 |
| Score gap (rank-1 vs rank-2), avg | 3.17 (SAFE) |

The large score gap between rank-1 and rank-2 (average 3.17 score units = ~1,479× difference in FMR) indicates the matcher is highly confident in its top candidates and impostor confusion is low.

---

## 8. Risks and Pitfalls Summary

| Risk | Mitigation |
|------|-----------|
| ANN misses true mate (recall < 100%) | Increase `nprobe` / `ef_search` in Milvus; use larger `maxCandidates` |
| Threshold applied inconsistently across workflows | Define a single system-wide threshold; document it |
| Near-threshold pairs decide differently in 1:1 vs 1:N | Run mated pair consistency test on borderline scores |
| Template indexed with wrong feature version | Verify F200 model version at enrollment and search time |
| Delayed index insertion (template enrolled but not yet searchable) | Add post-enrollment verification search |
| Score inflation in 1:N due to index corruption | Periodic self-match audit: enroll image → search → expect rank-1 = self |
| High concurrency inflates latency (demo server saturation) | Use 1 worker on demo; production deployment requires dedicated GPU |

---

## Quick Reference

```
Score interpretation:
  S = 4.0  → FMR 1 in 10,000     ← recommended minimum threshold
  S = 7.0  → FMR 1 in 10,000,000 ← law enforcement / high security
  S = 16.0 → near-certain match   ← typical self-match or high-quality pair

Expected score difference between 1:1 and 1:N (same pair):
  Normal:      ≤ 0.5 score units
  Investigate: > 1.0 score units
  Critical:    decision flips across threshold boundary

ANN recall is not 100%:
  Some mates will not appear in 1:N candidates even with a high 1:1 score.
  This is an expected ANN trade-off, not a matcher failure.
  Observed not-found rate in this deployment: ~4.37% at 1M scale.
```
