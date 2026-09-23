# Content Governance

**Status:** Implemented · **Applies to:** every meal record

## 1. Principles

1. Every nutrition record is traceable to a **source** and **evidence version**.
2. Content moves through explicit lifecycle states; nothing enters production
   recommendations implicitly.
3. Reviewers are accountable: reviewer identity and review date are stored.
4. If provenance is unknown, the content is marked accordingly and excluded
   from production recommendation flows.

## 2. Lifecycle states

| State | Meaning | In production recommendations? |
|---|---|---|
| `DRAFT` | Being authored | No |
| `REVIEW_REQUIRED` | Ready for review | No |
| `REVIEWED` | Content reviewed, awaiting publish decision | No |
| `PUBLISHED` | Reviewed and released | **Yes** |
| `RETIRED` | Withdrawn (unsafe, outdated, or unsourceable) | No |

State transitions are enforced in `backend/app/domain/content_state.py`:

```
DRAFT → REVIEW_REQUIRED → REVIEWED → PUBLISHED → RETIRED
            ↑                    │
            └────── (edit re-opens review) ──────┘
```

Invalid transitions raise `ValueError` (tested).

## 3. Required provenance fields (meals table)

- `source` (human-readable origin, e.g. dataset reference)
- `source_url` (optional link)
- `evidence_version` (string, bumped on content change)
- `reviewed_at`, `reviewer`
- `content_status` (lifecycle state above)
- `serving_basis` (what one serving means)

**No field named `clinically_approved` exists.** The previous schema set
`clinically_approved=true` on every seed row without any review — that field
was removed. Governance status now reflects reality: seeded rows are imported
as `REVIEW_REQUIRED` with the dataset as `source`; they must be reviewed and
published before production recommendations use them. In development/test the
pipeline can be configured to include `REVIEWED` content so the app remains
testable (`CONTENT_INCLUDE_STATUSES`).

## 4. Review workflow (data model)

`content_versions` table records each version: meal_id, version, payload
snapshot, change note, reviewer, status, timestamps. The administrative
endpoints allow listing versions and transitioning state; they are guarded by
the `content_admin` scope (not exposed to normal users).

## 5. Prohibited claims

The seed dataset's free-text `who_alignment` claims were removed. Any content
string claiming "WHO approved/aligned", "clinically approved", "medically
validated", "doctor approved", or similar requires a documented evidence URL
and reviewer sign-off, and is otherwise rejected by the import validator
(`domain/content_validator.py`).

## 6. Retiring content

Retired content stays queryable for audit but is excluded from all
recommendation and browse flows. Retirement requires a change note in
`content_versions`.
