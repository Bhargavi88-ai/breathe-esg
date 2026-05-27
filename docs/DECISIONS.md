# DECISIONS

Every ambiguity I resolved, what I chose, why, and what I'd ask the PM.

---

## SAP ingestion format

**Ambiguity:** IDoc XML, flat-file RFC extract, OData service, BAPI?

**Choice:** Flat-file RFC extract (MSEG-based, delimiter-separated).

**Why:**
The flat-file extract is the lowest barrier to entry. Every SAP ECC 6.0 and
S/4HANA system can produce it without middleware — the client's SAP admin runs
a report (MB51 / MB52 in MM, or a custom RFC) and exports it. No EDI infrastructure,
no live API connection, no OAuth token negotiation.

IDoc XML would be more structured but requires EDI partner agreements and an IDoc
processor on our side. OData (the modern S/4HANA approach) is cleaner but requires
a live internet-accessible SAP system — enterprise clients almost never expose their
SAP OData endpoints to the internet without a proxy, and the per-client OAuth setup
is heavy. For an onboarding scenario where we're meeting a client for the first time,
"can you export MB51 to CSV?" is a much easier ask than "can you set up OData access?"

**Subset handled:** Movement types 201 and 261 (goods issue to cost centre) — the
ones that represent direct consumption of fuel. I ignore receipts (501), returns,
and transfer postings as they don't represent consumption events.

**What I'd ask the PM:**
- Does this client use SAP ECC or S/4HANA? (Affects column names slightly.)
- Do they use plant-level or company-code-level cost centres? (Affects facility mapping.)
- Are there multiple plants across countries, or India-only? (Affects grid factor selection.)
- Do they want procurement (non-fuel materials) included as Scope 3 Category 1?

---

## Utility ingestion format

**Ambiguity:** Portal CSV export, PDF bill, or utility API (Green Button / ESPI)?

**Choice:** Portal CSV export.

**Why:**
PDF bill parsing is the most common format clients actually have, but it's the worst
to parse — every utility has a different PDF layout, and pdfplumber breaks on scanned
bills or bills with complex tariff tables. I considered it and rejected it.

Green Button / ESPI is the US standard for utility data sharing. In theory, any US
utility offers it. In practice, the OAuth setup is per-utility, and Indian clients
(BESCOM, MSEDCL, TNEB) don't support it at all. Not viable for a multi-geography client.

Portal CSV is available from essentially every utility that has a web portal. BESCOM
offers it at bescom.in → Billing History → Download. PG&E, British Gas, Con Edison all
offer "Download my usage" CSV. The format varies (column names differ), which is why
I built a column alias map that handles the most common variants.

**What I'd ask the PM:**
- How many meters / sites does this client have? (If hundreds, manual CSV export won't scale — we'd need to build a Green Button integration or scrape the portal.)
- Is the data from India, UK, or US? (Determines grid emission factor.)
- Do they have demand charges they want tracked separately, or just consumption?

---

## Travel ingestion format

**Ambiguity:** Concur API vs Navan API vs file export?

**Choice:** CSV export (compatible with both Concur and Navan).

**Why:**
Both Concur and Navan support expense report exports as CSV or Excel. Finance teams
routinely export these for GL reconciliation — it's an existing workflow, not a new ask.

The Concur TripLink API requires enterprise OAuth and a Concur admin to grant access
per customer. Navan's API is similarly gated. Both also require that the corporate
travel platform is the system of record (some clients use both, or mix platforms).
The export path bypasses all of that.

The column names differ between Concur and Navan, so I built a `TRAVEL_COLUMN_ALIASES`
map that handles both. The parser detects which columns are present and adapts.

**What I'd ask the PM:**
- Does the client use Concur, Navan, or something else? (Affects which column alias set to expand first.)
- Is distance always present in the export, or only airport codes? (My haversine implementation covers ~50 major airports — a real deployment needs an aviation distances API like OAG or FlightAware.)
- Do they want rail travel tracked separately? (Currently goes to ground_transport; no rail-specific factor.)

---

## Distance calculation for flights

**Ambiguity:** Concur sometimes provides miles or km; sometimes only airport codes.

**Choice:** Haversine from a hardcoded IATA coordinate table for the 50 most-common
airports; fall back gracefully with an error if both codes are missing.

**Why:**
The haversine formula is accurate enough for emission factor purposes — the error
vs a published great-circle distance is <1%. The IATA table covers the routes that
account for the vast majority of business travel (major hubs in India, US, UK, Europe,
Middle East, Southeast Asia).

**What breaks in production:**
If origin or destination isn't in my table (e.g. a regional Indian airport like
Tiruchirappalli, TRZ), the parser records an error for that row. An analyst sees
it in the review queue and can either manually add the airport to the table or
enter the distance directly. For a real deployment, we'd call an aviation distances
API (OAG Schedules API, or a free alternative like the OpenFlights dataset).

---

## Scope assignment for SAP procurement records

**Ambiguity:** A goods issue (movement type 201) could be Scope 1 (if the material is
combusted on-site) or Scope 3 Category 1 (if it's a purchased input).

**Choice:** If the material description matches a fuel pattern, assign Scope 1. Otherwise,
assign Scope 1 with category "procurement" and flag it for analyst review.

**Why:**
Without a complete material master mapping (MATNR → emission category), we can't
reliably distinguish "diesel for the generator" from "steel sheets for the production
line". The fuel pattern matching handles the easy cases. The rest are marked pending
and surfaced to the analyst, who has the context to categorise them.

**What I'd ask the PM:**
- Does the client have a material master list we can use for categorisation?
- Should non-fuel procurement be Scope 3 Category 1 (purchased goods) or excluded entirely?

---

## Emission factor selection

**Choice:** DEFRA 2023 GHG Conversion Factors for flights and ground transport;
CEA 2022-23 for Indian grid electricity; EPA 2023 for US grid; DEFRA 2023 for UK.

**Why:**
DEFRA is the most widely used emission factor source in corporate reporting (GHG
Protocol compliant, updated annually). CEA (Central Electricity Authority of India)
is the authoritative source for the Indian grid. For a client with Indian operations,
using a global average would significantly understate or overstate Scope 2 emissions.

The emission factor is stored at record creation time, not looked up dynamically.
See MODEL.md for why.

**Business class multiplier:**
I apply a 2× multiplier for business class and 2.4× for first class, following DEFRA
2023 methodology (which accounts for greater cabin space per passenger).

---

## Synchronous ingestion

**Choice:** File parsing runs synchronously in the Django request-response cycle.
No Celery, no task queue.

**Why:**
For the prototype scope and expected file sizes (hundreds to a few thousand rows),
synchronous processing completes in under 2 seconds. Adding Celery would require
Redis, worker processes, and additional deployment configuration — not worth it at
this stage.

**What changes in production:**
Files with tens of thousands of rows (a large SAP export covering a full year) would
time out the HTTP request. For production, the upload endpoint would enqueue a Celery
task and return immediately with a batch ID; the frontend would poll `GET /ingestion/batches/{id}/`
until status changes from "processing" to "done".

---

## Authentication

**Choice:** DRF Token authentication (one opaque token per user, stored in the database).

**Why:**
Simple to implement, simple to revoke (delete the token), works well with the SPA
architecture. For a production system with many users or SSO requirements, we'd
move to JWT (shorter token lifetime, no DB lookup per request) or OAuth2 with
SAML/OIDC for enterprise SSO (Okta, Azure AD).

---

## Database

**Choice:** SQLite for local dev; PostgreSQL (via dj-database-url) in production.

**Why:**
Django's ORM is database-agnostic for the queries we're using. SQLite gets developers
running in 30 seconds with no infrastructure. The `render.yaml` deploys to Postgres
automatically on Render. The only SQLite-specific caveat: `JSONB` queries are `JSON`
in SQLite; we don't use JSON-specific operators in our ORM queries, so this is fine.
