# DATA MODEL

## Core design principles

Every decision in this model follows four constraints the assignment made explicit:
multi-tenancy, Scope 1/2/3 categorisation, source-of-truth tracking, and audit trail.
A fifth constraint I added: the model should make it impossible to accidentally leak
data across tenants or lose provenance information.

---

## Tables

### `organisations` (tenant root)

```
id                    UUID PK
name                  VARCHAR(255)
slug                  VARCHAR(255) UNIQUE
active_reporting_year INTEGER          -- which year the org is currently working on
created_at            TIMESTAMPTZ
```

Every other table has a NOT NULL FK to `organisations`. This is the tenancy boundary.
There is no "cross-tenant query" path in the codebase — the ORM queryset filter
`organisation=request.user.organisation` is applied at the top of every view.

I chose a single-database, shared-schema multi-tenancy design rather than a
separate schema per tenant because:
- The expected scale (dozens of clients, thousands of records per client) doesn't
  warrant per-schema isolation.
- Django's ORM makes shared-schema tenancy with a FK constraint easy to enforce.
- Per-schema would complicate migrations and deployment significantly.

---

### `users`

```
id             UUID PK
email          VARCHAR UNIQUE
first_name     VARCHAR
last_name      VARCHAR
organisation   FK → organisations (nullable for superusers)
role           ENUM(analyst, admin, viewer)
is_active      BOOLEAN
is_staff       BOOLEAN
date_joined    TIMESTAMPTZ
```

Custom `AbstractBaseUser` subclass. Email-based auth. Three roles:
- `analyst`: can approve, flag, and edit records
- `admin`: full access, can ingest and manage org settings
- `viewer`: read-only

---

### `ingestion_batches`

```
id                UUID PK
organisation      FK → organisations
source_type       ENUM(sap, utility, travel)
status            ENUM(pending, processing, done, failed)
uploaded_file     FileField (stored permanently)
original_filename VARCHAR
rows_total        INTEGER
rows_success      INTEGER
rows_failed       INTEGER
rows_duplicate    INTEGER
uploaded_by       FK → users (nullable)
error_message     TEXT     -- top-level failure if status=failed
created_at        TIMESTAMPTZ
completed_at      TIMESTAMPTZ
```

One batch = one file upload. Every `emission_record` points back to the batch
that created it. Batches are never deleted — they form part of the audit trail.
The original file is stored on disk and never deleted.

---

### `ingestion_errors`

```
id             UUID PK
batch          FK → ingestion_batches (CASCADE)
row_index      INTEGER     -- which row in the source file
raw_data       TEXT        -- repr of the failing row (truncated at 1000 chars)
error_message  TEXT
created_at     TIMESTAMPTZ
```

Row-level parse failures. Surfaced to the analyst so they can decide whether to
re-upload a corrected file or manually enter the data. Cascades on batch delete
(which we never actually do, but the constraint is correct).

---

### `emission_records` (the canonical table)

```
id                    UUID PK
organisation          FK → organisations (PROTECT)

-- Source provenance
source_type           ENUM(sap, utility, travel)
ingestion_batch       FK → ingestion_batches (PROTECT, nullable)
source_row_index      INTEGER   -- row number in the source file
source_row_hash       VARCHAR(64) INDEXED  -- SHA-256 of key fields for dedup

-- Scope / category
scope                 ENUM(1, 2, 3)
category              ENUM(fuel, procurement, electricity, flight, hotel, ground_transport)
sub_category          VARCHAR   -- e.g. "diesel_litre", "Economy", "London"

-- Raw activity (as ingested, never modified)
raw_quantity          DECIMAL(18,4)
raw_unit              VARCHAR(50)  -- original unit: "GAL", "M3G", "kWh", etc.
raw_description       TEXT

-- Normalised activity (post-conversion)
normalised_quantity   DECIMAL(18,4)
normalised_unit       VARCHAR(20)  -- always: "litres", "kwh", "km", "nights", "kg"

-- Carbon calculation
emission_factor_key   VARCHAR(100)  -- e.g. "diesel_litre"
emission_factor_value DECIMAL(12,6) -- kgCO2e per normalised unit, at time of ingestion
kg_co2e               DECIMAL(18,4)

-- Time and location
activity_date         DATE
activity_period_start DATE     -- for utility billing periods
activity_period_end   DATE
reporting_year        INTEGER
facility_code         VARCHAR(100)  -- SAP plant code, meter ID, etc.
facility_name         VARCHAR(255)
country_code          VARCHAR(3)

-- Source-specific metadata
extra                 JSONB    -- flexible bag for per-source fields

-- Review workflow
status                ENUM(pending, approved, flagged, locked)
review_note           TEXT
reviewed_by           FK → users (nullable)
reviewed_at           TIMESTAMPTZ

-- Audit trail
created_at            TIMESTAMPTZ (auto)
updated_at            TIMESTAMPTZ (auto)
manually_edited       BOOLEAN DEFAULT false
locked_at             TIMESTAMPTZ
```

#### Why UUID PKs everywhere?

Prevents ID enumeration attacks. More importantly, allows the system to assign IDs
client-side if we ever add offline ingestion, without coordination.

#### The `extra` JSON field

Source-specific fields that don't belong in the canonical schema go here.
For SAP records: `doc_number`, `movement_type`, `cost_centre`, `vendor`.
For utility: `meter_id`, `cost`, `ef_country`.
For travel: `traveler`, `origin_iata`, `dest_iata`, `cabin`, `class_multiplier`.

I chose JSONB over additional columns because:
- Source schemas differ per client (one SAP instance may have fields another doesn't)
- Adding a column per source-specific field would inflate the schema with NULLs
- The fields in `extra` are never filtered or indexed — they're reference data only

If a field in `extra` ever needs to be queryable (e.g. filtering by traveller),
it should be promoted to a proper column.

#### Raw vs normalised quantity

We store both. The raw value is what came out of the source file, unchanged.
The normalised value is after unit conversion (e.g. 500 GAL → 1892.7 L).
The emission factor is then applied to the normalised value.

This means an auditor can always verify the calculation:
`raw_quantity × conversion_factor = normalised_quantity`
`normalised_quantity × emission_factor_value = kg_co2e`

#### Emission factor at ingestion time

`emission_factor_value` is stored at write time, not looked up at query time.
This is intentional: DEFRA/EPA update their factors annually. If we stored only
the factor key and looked it up live, the carbon figure would silently change
when we update our factor table. An auditor would see different numbers depending
on when they ran the report. By storing the value at ingestion time, the record
is reproducible forever.

#### Deduplication via `source_row_hash`

Before writing, we compute `SHA-256(doc_number + line_item + quantity + uom + description)`
for SAP, `SHA-256(meter_id + period_start + kwh)` for utility, and similar for travel.
If the hash already exists for the organisation, we skip the row and increment
`rows_duplicate`. This prevents double-counting when a client re-exports overlapping
date ranges.

#### Review state machine

```
pending → approved
pending → flagged → approved
approved → flagged (analyst changes mind)
approved → locked (admin locks for audit; irreversible)
```

`locked` records cannot be modified by anyone. The `lock()` method is the only
path to the locked state. In production, it would be accessible only to admin-role
users and would trigger the creation of an audit export.

---

### `audit_events` (append-only)

```
id               UUID PK
organisation     FK → organisations
emission_record  FK → emission_records (nullable, SET_NULL)
ingestion_batch  FK → ingestion_batches (nullable, SET_NULL)
action           ENUM(approve, flag, edit, lock, ingest)
actor            FK → users (nullable, SET_NULL)
previous_value   JSONB
new_value        JSONB
note             TEXT
created_at       TIMESTAMPTZ
```

The `save()` method raises `ValueError` if the record already exists — enforcing
append-only at the application layer. In production, this table should also have a
database trigger that prevents UPDATE and DELETE.

The `emission_record` FK is `SET_NULL` (not `PROTECT`) because if a record is ever
deleted (which we don't do, but if it were), the audit trail should survive.

---

## Indexes

```sql
-- Primary review dashboard query
CREATE INDEX ON emission_records (organisation_id, reporting_year, status);

-- Scope breakdown for summary API
CREATE INDEX ON emission_records (organisation_id, scope, reporting_year);

-- Provenance lookups
CREATE INDEX ON emission_records (source_type, ingestion_batch_id);

-- Deduplication check
CREATE INDEX ON emission_records (source_row_hash);
```

---

## Scope assignment rules

| Category          | Scope | Rationale |
|-------------------|-------|-----------|
| fuel              | 1     | On-site combustion, direct emissions |
| procurement       | 1     | Non-fuel goods issue (movement type 201/261) assumed on-site use |
| electricity       | 2     | Market-based, grid factor applied |
| flight            | 3     | Category 6 – Business travel |
| hotel             | 3     | Category 6 – Business travel |
| ground_transport  | 3     | Category 6 – Business travel |

Procurement is assigned Scope 1 for now because the SAP movements we handle
(goods issue to cost centre) represent direct consumption. In a more complete
implementation, a procurement item would be Scope 3 Category 1 if it's a purchased
material that's not combusted on-site. This is flagged in DECISIONS.md.
