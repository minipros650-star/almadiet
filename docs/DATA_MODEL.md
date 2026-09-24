# Data Model

**Status:** Implemented (Alembic migrations 0001–0003)

## ER overview

```
users 1──* refresh_tokens
users 1──* consents
users 1──* audit_logs
users 1──* health_records 1──0..1 diet_plans
users 1──* diet_plans
users 1──* urgent_help_notes
meals 1──* meal_allergens *──1 allergens (category enum)
meals 1──* content_versions
```

## Tables

### users
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| email | String(255) | UNIQUE NOT NULL, indexed |
| password_hash | String(255) | NOT NULL (Argon2id) |
| name | String(255) | NOT NULL |
| phone | String(20) | nullable |
| region | String(20) | NOT NULL, CHECK in ('kerala','tamilnadu','karnataka','andhra') |
| language | String(5) | NOT NULL, CHECK in ('en','ml','ta','kn','te') |
| lmp_date, due_date | Date | nullable |
| age | Integer | CHECK 14–55 |
| height_cm | Float | CHECK 100–250 |
| pre_pregnancy_weight_kg | Float | CHECK 30–200 |
| created_at / updated_at | timestamptz | server default / onupdate |

### refresh_tokens
id PK · user_id FK→users ON DELETE CASCADE · token_hash UNIQUE NOT NULL
· family_id (rotation family) · expires_at NOT NULL · revoked_at nullable
· created_at. Index (user_id), index (family_id).

### consents
id PK · user_id FK CASCADE · consent_version NOT NULL · accepted_at NOT NULL
· ip_hash nullable. Index (user_id, accepted_at).

### health_records
id PK · user_id FK CASCADE NOT NULL (indexed, composite index
(user_id, recorded_at)) · trimester CHECK 1–3 · week_number CHECK 1–42
· **CHECK ((trimester=1 AND week BETWEEN 1 AND 13) OR (trimester=2 AND week
BETWEEN 14 AND 26) OR (trimester=3 AND week BETWEEN 27 AND 42))**
· current_weight_kg CHECK 30–200 · bmi nullable CHECK 10–60
· blood_pressure_sys/dia nullable CHECKs · hemoglobin nullable CHECK 3–20
· blood_sugar_fasting nullable CHECK 20–600
· allergies JSONB (list of allergen **category codes**) · medical_conditions
JSONB (list of condition codes) · is_vegetarian BOOL · dietary_preference
CHECK in ('veg','nonveg','eggetarian') · notes TEXT nullable · recorded_at.
Application-layer validation mirrors the same rules (domain/gestational.py).

### meals
id PK · dataset_id UNIQUE nullable · name NOT NULL · name_{tamil,malayalam,
kannada,telugu} nullable · region NOT NULL · meal_type NOT NULL
· trimester_suitability JSONB · nutrition columns NOT NULL DEFAULT 0 with
CHECK (value >= 0): calories, protein_g, carbs_g, fat_g, fiber_g, iron_mg,
calcium_mg, folate_mcg, vitamin_c_mg, sodium_mg, sugar_g
· ingredients JSONB · serving_size · serving_basis · preparation_time_minutes
CHECK ≥ 0 · benefits JSONB · cautions TEXT · best_time_to_eat
· food_safety_notes TEXT · cuisine · image_url
· is_vegetarian BOOL NOT NULL
· **source** String NOT NULL (provenance) · source_url · evidence_version
NOT NULL DEFAULT '1' · reviewed_at · reviewer · **content_status**
CHECK in ('DRAFT','REVIEW_REQUIRED','REVIEWED','PUBLISHED','RETIRED')
NOT NULL DEFAULT 'REVIEW_REQUIRED' · created_at/updated_at.
Removed: `clinically_approved`, `who_alignment` (claims field).

### allergens
id PK · category (enum: peanut, tree_nut, milk, egg, wheat_gluten, soy,
fish, shellfish, sesame, mustard, sulfite, other) UNIQUE NOT NULL
· display_name NOT NULL.

### meal_allergens
meal_id FK CASCADE · allergen_id FK RESTRICT · match_type
('exact','normalized','synonym','contains') · matched_term · PK (meal_id,
allergen_id, matched_term). Populated at import time by domain/allergens.py.

### content_versions
id PK · meal_id FK CASCADE · version INT NOT NULL · payload JSONB ·
change_note · reviewer · status · created_at. Index (meal_id, version desc).

### diet_plans
id PK · user_id FK CASCADE · health_record_id FK SET NULL
· trimester, week_number (CHECKs as health_records) ·
**days JSONB NOT NULL — array of exactly 7 day objects, each
{day_index, meals: {breakfast:[MealCard], lunch:[…], snack:[…], dinner:[…]}}**
· targets (calories/protein/iron/calcium — displayed as reference context,
not prescriptions) · dietary_alerts JSONB (explanations + sources)
· exclusions_applied JSONB · is_swappable BOOL · plan_start/plan_end NOT NULL
· created_at. Removed: `is_emergency_plan`, `emergency_meals`.

MealCard (inside JSONB) = meal id, names, nutrition, allergens, substitutions,
safety_notes, **why_suggested[] (deterministic explanations)**, source,
evidence_version, content_status.

### urgent_help_notes
id PK · user_id FK CASCADE · observed_symptoms JSONB (free text supplied by
user) · created_at. **No resolved_at, no is_active** — the app never records
resolution of urgent situations.

### audit_logs
id PK · user_id nullable FK SET NULL · event_code NOT NULL (enum:
LOGIN_SUCCESS, LOGIN_LOCKOUT, TOKEN_REFRESHED, TOKEN_REVOKED,
PROFILE_UPDATED, HEALTH_RECORD_CREATED, HEALTH_RECORD_DELETED,
PLAN_GENERATED, CONSENT_ACCEPTED, CONSENT_UPDATED, DATA_EXPORTED,
ACCOUNT_DELETED, CONTENT_STATUS_CHANGED) · context JSONB (**no health
values**) · ip_hash · created_at. Index (user_id, created_at), (event_code).

## Constraints philosophy
- DB-level CHECKs mirror domain validation; domain functions remain the
  single source of truth for code paths, DB constraints are defence in depth.
- All user-scoped tables: composite index on (user_id, <query column>).
- Soft delete not used; hard delete via account deletion (documented).
