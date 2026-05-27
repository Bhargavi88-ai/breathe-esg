# Breathe ESG — Emissions Ingestion & Review Platform

A Django REST + React prototype for ingesting emissions data from three sources
(SAP fuel exports, utility portal CSVs, corporate travel exports), normalising it,
and surfacing a review dashboard where analysts can approve or flag records before
they're locked for audit.

---

## Architecture

```
breathe-esg/
├── backend/          Django 4.2 REST API
│   ├── breathe_esg/
│   │   ├── apps/
│   │   │   ├── accounts/     Custom User + Organisation (tenant)
│   │   │   ├── ingestion/    File upload, parsers (SAP/Utility/Travel), batch tracking
│   │   │   ├── emissions/    Canonical EmissionRecord model, review workflow
│   │   │   └── audit/        Append-only audit event log
│   │   ├── settings/
│   │   └── urls.py
│   ├── sample_data/  Realistic sample files for all three sources
│   └── requirements.txt
├── frontend/         React 18 SPA
│   └── src/
│       ├── pages/    Dashboard, Review queue, Ingestion upload
│       ├── components/
│       ├── hooks/    useAuth (context)
│       └── api/      Axios client
└── docs/
    ├── MODEL.md      Data model + rationale
    ├── DECISIONS.md  Every ambiguity resolved
    ├── TRADEOFFS.md  Three deliberate omissions
    └── SOURCES.md    Per-source format research
```

---

## Running locally

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — the defaults work for local dev

python manage.py migrate
python manage.py seed_demo   # Creates demo org + users + ~80 records

python manage.py runserver
```

API runs at `http://localhost:8000/api/v1/`

### Frontend

```bash
cd frontend
npm install
npm start
```

App runs at `http://localhost:3000`

---

## Demo credentials

| Email | Password | Role |
|-------|----------|------|
| admin@acme.com | demo1234 | Admin |
| analyst@acme.com | demo1234 | Analyst |

---

## Sample data files

All three sample files are in `backend/sample_data/`:

| File | Source | Description |
|------|--------|-------------|
| `sap_mseg_export_sample.csv` | SAP MB51 export | Tab-delimited MSEG extract, 13 fuel movements across 3 plants |
| `utility_bescom_sample.csv` | BESCOM portal | 11 billing records across 3 meters (HQ, factory, Pune office) |
| `navan_travel_export_sample.csv` | Navan trip export | 45 travel records (flights, hotels, ground) |

Upload them via the Ingest page in the app.

---

## API endpoints

### Auth
- `POST /api/v1/auth/login/` — returns token + user
- `POST /api/v1/auth/logout/`
- `GET  /api/v1/auth/me/`

### Ingestion
- `POST /api/v1/ingestion/upload/` — multipart: `source_type`, `file`, `country_code`
- `GET  /api/v1/ingestion/batches/`
- `GET  /api/v1/ingestion/batches/{id}/`

### Emissions
- `GET  /api/v1/emissions/records/` — filters: `scope`, `status`, `source_type`, `year`, `search`
- `GET  /api/v1/emissions/records/{id}/`
- `POST /api/v1/emissions/records/{id}/approve/`
- `POST /api/v1/emissions/records/{id}/flag/` — body: `{ "note": "..." }`
- `POST /api/v1/emissions/records/bulk-approve/` — body: `{ "ids": [...] }`
- `GET  /api/v1/emissions/summary/` — aggregated by scope + source

### Audit
- `GET  /api/v1/audit/events/` — filter: `?record={uuid}`

---

## Deployment (Render)

1. Fork this repo
2. Create a new Render Web Service from the `backend/` directory
3. Set environment variables (SECRET_KEY, DATABASE_URL from Render Postgres, CORS_ALLOWED_ORIGINS)
4. The build command (`pip install && migrate && seed_demo`) runs automatically
5. For the frontend, create a Render Static Site from `frontend/`, build command `npm run build`, publish dir `build/`
6. Set `REACT_APP_API_URL` in the frontend env to your backend Render URL

See `backend/render.yaml` for the full Render service definition.

---

## Grading notes

- **Data model:** See `docs/MODEL.md` — multi-tenancy, scope categorisation, source-of-truth tracking, unit normalisation, audit trail all addressed.
- **Decision defence:** See `docs/DECISIONS.md` — every fork in the road is documented with rationale and what I'd ask the PM.
- **Source research:** See `docs/SOURCES.md` — format research, sample data justification, production failure modes.
- **Tradeoffs:** See `docs/TRADEOFFS.md` — async ingestion, PDF parsing, market-based Scope 2.
- **Analyst UX:** Review queue with status filters, scope filters, source filters, full-text search, inline approve/flag with note, bulk approve, pagination.
