# AutoOutreach Pipeline

AutoOutreach Pipeline is a production-style Python 3.11 CLI that automates a cold outreach workflow from one seed company domain. It finds similar companies, discovers decision-makers, enriches verified work emails, generates personalized outreach, previews the send list, and sends through Brevo only after explicit confirmation.

The real provider flow is:

```text
Ocean.io company lookalikes
  -> Prospeo decision-makers
  -> Prospeo email enrichment
  -> Jinja2 outreach copy
  -> Rich safety preview
  -> Brevo email sending
```

Eazyreach remains in the codebase as an optional provider boundary, but it is intentionally disabled by default because free API access/credits were unavailable. Prospeo is used as the replacement for both decision-maker discovery and email enrichment.

## Architecture

```text
Typer CLI
  -> Pipeline Orchestrator
     -> OceanClient or MockDiscoveryClient
     -> ProspeoClient or MockProspeoClient
     -> Dedupe + Validation
     -> Jinja2 Email Templates
     -> Rich Safety Checkpoint
     -> BrevoClient or MockBrevoClient
     -> JSON/CSV/Markdown Artifacts + SQLite Run Metadata
```

The pipeline is dry-run by default. Even when `--send` is passed, the user must type exactly `SEND` before Brevo is called.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Then add real credentials to `.env`. Do not commit `.env`; it is gitignored.

## Environment Variables

```env
OCEAN_API_KEY=
OCEAN_BASE_URL=https://api.ocean.io
OCEAN_LOOKALIKE_ENDPOINT=/v3/search/companies
OCEAN_LOOKALIKE_METHOD=POST
OCEAN_AUTH_HEADER=x-api-token
OCEAN_AUTH_PREFIX=
OCEAN_SEED_DOMAIN_FIELD=domain
OCEAN_LIMIT_FIELD=limit
OCEAN_RESPONSE_COMPANIES_PATH=companies
OCEAN_COMPANY_NAME_FIELD=company.name
OCEAN_COMPANY_DOMAIN_FIELD=company.domain
OCEAN_COMPANY_SCORE_FIELD=relevance
OCEAN_LOOKALIKE_BODY_TEMPLATE={"size":{limit},"companiesFilters":{"lookalikeDomains":["{domain}"]}}
COMPANY_DISCOVERY_PROVIDER=ocean

PROSPEO_API_KEY=

EAZYREACH_API_KEY=
EMAIL_PROVIDER=prospeo
EAZYREACH_ENABLED=false

BREVO_API_KEY=
BREVO_SENDER_EMAIL=
BREVO_SENDER_NAME=
BREVO_SANDBOX=true
TEST_RECIPIENT=

DEFAULT_LIMIT=10
REQUEST_TIMEOUT_SECONDS=30
MAX_RETRIES=3
```

`BREVO_SANDBOX=true` sends Brevo requests with `X-Sib-Sandbox: drop`, so Brevo validates the request without delivering it. `TEST_RECIPIENT` is optional and is useful for demos.

## Common Commands

Validate local configuration:

```powershell
python main.py validate-env
```

Run the mock demo with no API keys:

```powershell
python main.py run --domain example.com --mock
```

Run real providers in dry-run mode:

```powershell
python main.py run --domain apollo.io --limit 3
```

Dry-run means the pipeline creates outreach emails and records `dry_run` send results, but does not send through Brevo.

Provider smoke tests:

```powershell
python main.py test-provider ocean --domain apollo.io --debug
python main.py test-provider prospeo --domain apollo.io
python main.py test-provider brevo --sandbox
python main.py test-provider brevo --to myemail@example.com
```

Probe Ocean directly when checking API docs/config:

```powershell
python main.py probe-ocean --method POST --endpoint "/v3/search/companies" --domain apollo.io --limit 1
```

Safe send demo:

```powershell
python main.py run --domain apollo.io --limit 3 --send --test-recipient myemail@example.com
```

With `--test-recipient`, every approved email is sent to the test inbox instead of the discovered prospect. The original intended recipient is written into the email body for review.

Resume and export saved runs:

```powershell
python main.py resume --run-id <run-id>
python main.py export --run-id <run-id>
```

## Safety Model

- Default mode is dry-run.
- `--send` only enables the send path; it does not send immediately.
- Before sending, the CLI shows a Rich table with name, title, company, email, and subject.
- The CLI also shows totals for companies, contacts, verified emails, skipped emails, and duplicates removed.
- Sending proceeds only when the user types exactly:

```text
SEND
```

Anything else skips sending and saves the run as dry-run.

## Saved Artifacts

Each run writes:

```text
data/runs/<timestamp>_<seed-domain>/
  run.json
  companies.json
  contacts.json
  email_candidates.json
  outreach_emails.csv
  send_results.json
  report.md
```

Run metadata is also stored in:

```text
data/runs.db
```

Ocean probe responses are saved under:

```text
data/debug/
```

## Tests and Quality

```powershell
python -m pytest
python -m ruff check .
```

Coverage includes domain validation, dedupe, deterministic email copy, safety confirmation behavior, Ocean parsing/config, Prospeo parsing/enrichment, and mock pipeline end-to-end behavior.

## Tradeoffs

- Eazyreach is optional but disabled because free API access/credits were unavailable; Prospeo fills that role.
- Ocean remains configurable because API docs and account access can expose different request shapes over time.
- Mock mode is intentionally robust so the assignment can be demonstrated without paid credits.
- Email copy is deterministic to make tests and demos predictable.
- Resume currently inspects saved artifacts; it does not replay partially completed provider stages.

## Interview Talking Points

- The project separates provider clients from pipeline orchestration, so Ocean, Prospeo, Brevo, mocks, and optional Eazyreach can be swapped without rewriting the pipeline.
- Safety is enforced in layers: dry-run default, explicit `--send`, exact `SEND` confirmation, Brevo sandbox support, and `--test-recipient` demo routing.
- The pipeline saves audit-friendly artifacts for every stage plus SQLite metadata for run history.
- Provider failures are isolated per company/contact when possible, so one bad enrichment does not crash the whole run.
- The project includes realistic mocks, typed Pydantic models, async HTTP clients, retry/backoff, terminal UX, templated copy, exports, tests, and linting.
