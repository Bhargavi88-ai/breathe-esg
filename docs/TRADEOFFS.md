# TRADEOFFS

Three things I deliberately did not build, and why.

---

## 1. Celery / async task queue for ingestion

**What it would do:** Move file parsing off the request thread. The upload endpoint
returns immediately with a batch ID; a Celery worker processes the file in the
background; the frontend polls for completion.

**Why I didn't build it:**
For the file sizes realistic at prototype stage (hundreds to a few thousand rows),
synchronous processing completes in under 2 seconds. Adding Celery requires Redis as
a broker, worker processes, and additional infrastructure on Render (a paid add-on
or a separate worker service).

The cost of adding this complexity upfront — both in build time and in operational
burden — isn't justified until we have a client with SAP exports large enough to
time out. The code is structured so that the service layer (`ingestion/service.py`)
is already decoupled from the HTTP layer (`ingestion/views.py`); wrapping it in a
Celery task is a 20-line change.

**What breaks without it:**
A very large file (>50,000 rows, ~5 MB) would cause a 30-second timeout on the
HTTP request. The batch would be left in "processing" status. This is a known
limitation documented in DECISIONS.md.

---

## 2. PDF bill parsing for utility data

**What it would do:** Accept a utility bill PDF and extract meter ID, billing period,
and kWh consumption using pdfplumber or a similar library.

**Why I didn't build it:**
PDF parsing is the correct long-term answer — most facilities teams have PDFs, not
portal CSVs. But it's also the highest-effort, most brittle component to build well.
Every utility formats their bill differently. BESCOM PDFs differ from PG&E PDFs
differ from British Gas PDFs. A parser that works for one breaks for another.

Building a robust PDF parser would require either:
(a) A per-utility parser — weeks of work, not days, and requires sample bills from
    every utility the client uses.
(b) An LLM-based extraction (send the PDF to Claude, ask it to extract kWh) — works
    surprisingly well but adds API cost and latency, and raises questions about sending
    client utility bills to a third-party API.

The CSV portal export covers the same data and is available from every major utility.
The right order of operations: ship with CSV, add PDF once we have real utility bills
to test against.

---

## 3. Market-based vs location-based Scope 2 accounting

**What it would do:** Allow an organisation to use electricity attribute certificates
(RECs in the US, GoOs in Europe, RECs/I-RECs in India) to report market-based Scope 2
emissions separately from location-based.

**Why I didn't build it:**
GHG Protocol requires both market-based and location-based Scope 2 calculations when
the organisation has instrument-based claims (RECs). The current model only implements
location-based (grid average emission factor per country).

Market-based accounting requires knowing which RECs the client has purchased, for which
locations, covering which periods — and then deducting those from the location-based
figure. This is a significant data model addition: a `certificates` table, a way to
link certificates to specific meters or facilities, and a new calculation path.

I excluded it because (a) it requires additional data the client hasn't provided, and
(b) for a prototype, establishing the location-based baseline correctly is the right
first step. Most clients don't have REC programs on day one.

**What I'd do next:**
Add a `renewable_energy_certificates` table FK'd to `organisations`, with fields for
certificate type, issuing body, coverage period, and MWh covered. Subtract the
covered kWh from the Scope 2 total and present both figures in the dashboard.
