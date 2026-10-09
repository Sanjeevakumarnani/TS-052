# InfraPulse Data Dictionary

All demo rows under `backend/data/villages.json` are synthetic. They do not describe real measured infrastructure performance or verified coordinates.

## Village record

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Internal or source village identifier; unique in the dataset. |
| `name` | string | Village display name; demo records use fictional display names. |
| `state`, `district`, `block` | string | Geographic grouping labels; demo geography is illustrative. |
| `latitude`, `longitude` | number | Illustrative map point; not a verified village centroid. |
| `population.value` | number | Synthetic demo population unless an explicitly sourced record is imported. |
| `dimensions` | object | Reliability indicators grouped by dimension. |
| `criticality` | 0–100 | Prototype estimate of service criticality; not an official assessment. |
| `alternative_access` | 0–100 | Prototype score for availability of alternatives; higher means alternatives are more available. |
| `evidence_type` | string | Evidence class such as `simulated` or `uploaded-unverified`. |
| `source_name`, `source_url`, `source_date` | string/date | Provenance fields; may be absent for demo data. |
| `data_notice` | string | Label describing whether the record is demo, uploaded/unverified, or sourced. |

## Community report records

Public field reports are stored separately from village baseline values. Each report has an unverified status and an opaque `reference_code` returned only at submission time for private status lookup. Public report listings exclude the description and reference code. Status transitions are recorded in `field_report_status_history`; no report changes a village score automatically.

## Reviewer & moderation audit records

When an authorized reviewer inspects or acts on a report (via `/api/v1/reviewer/reports` with a bearer token), an audit record is stored in `reviewer_actions`:
- `report_id`: ID of the target field report.
- `reviewer_id`: Identity of the reviewer performing the action.
- `action`: Moderation verb (`approve`, `reject`, `flag`, `request_info`).
- `new_status`: Resulting verification status (`verified`, `rejected`, `flagged`, `pending_info`).
- `note`: Reviewer explanation or evidence citation.
- `acted_at`: Timestamp of review.

## Import sessions and audit history

CSV imports execute through a staged workflow:
1. `import_sessions`: Stores temporary preview payloads under a cryptographically random `token`, tracking parsed valid records, rejection logs, and a `confirmed` flag.
2. `import_history`: Permanent audit log containing the `token`, original `filename`, `file_sha256` digest, count of accepted records, count of rejected rows, and the `confirmed_at` timestamp.

## Verification Workflow Tables

- `users`: User profiles with `id`, `username`, `password_hash` (PBKDF2-HMAC-SHA256), `role` (`admin`, `resident`, `public`), and `display_name`.
- `geography_states`, `geography_districts`, `geography_mandals`, `geography_villages`: Cascading administrative boundary definitions and centroid coordinates.
- `village_memberships`: Location match records pairing authenticated users with their verified village through browser GPS point-in-polygon or centroid distance calculation.
- `development_records`: Base administrative project and asset records for verification across dimensions (roads, electricity, digital, etc.).
- `import_batches` & `import_row_errors`: Detailed record of admin development dataset imports, validation summaries, and row-level parse errors.
- `evidence_submissions`: Resident field observations linking to a development record, containing observed status, user notes, capture coordinates, and submission metadata.
- `attachments`: Metadata and storage pointers for evidence files stored securely in `backend/data/attachments/` outside web root, with MIME magic-byte verification.
- `ai_analyses`: Structured server-side vision AI outputs for captured evidence (summary, relation to claim, observed traits, status).
- `promoted_indicators`: Indicators explicitly elevated by admins from verified submissions into trusted score-influencing factors.
- `audit_events`: Tamper-evident admin audit log recording all status reviews, imports, and indicator promotions.

## Dimension keys

| Key | Display label | Intended meaning |
|---|---|---|
| `digital` | Digital connectivity | Availability and performance of broadband/mobile connectivity. |
| `electricity` | Electricity reliability | Continuity and quality of power supply. |
| `roads` | Road accessibility | Road passability, seasonal reliability and travel accessibility. |
| `public_digital` | Public digital infrastructure | Practical access to digital service points/public connectivity. |
| `essential_services` | Essential-service accessibility | Access to healthcare, education, markets, government and emergency services. |

A dimension may contain `score`, `availability_score`, `reliability_score`, `evidence_type`, `source_date`, `confidence` and explanatory notes. Scores should be on a 0–100 scale. Availability/reliability gaps are only meaningful if their definitions, spatial scale and observation periods are compatible.

## Import CSV

Required columns: `id,name,district,latitude,longitude,population,digital_score,electricity_score,road_score,public_digital_score,essential_services_score`.

Optional columns: `state,block,digital_availability,criticality,alternative_access`.

Every uploaded row is marked unverified. Check data licence, dates, units, geography and measurement method before treating it as reliable evidence.
