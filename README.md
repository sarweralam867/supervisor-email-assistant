# Supervisor Email Assistant

A small, review-first Python tool for personalized research-supervisor outreach. It reads only your CSV,
renders a strict template, attaches your CV to drafts, and can optionally deliver through a generic SMTP
provider. It does not scrape websites or discover contact details.

## Safety by default

- `draft_only` is the default; real delivery requires typing `SEND` exactly.
- Sending is capped at 10 per local day, with a configurable delay that cannot go below 120 seconds.
- Drafted, sent, malformed, generic, and opted-out addresses are skipped and audited.
- Opt-outs are stored privately and checked before drafting, previewing, or sending.
- Automated tests never connect to SMTP.

Always verify recipient information and review each message. This is an individual outreach aid, not a
bulk-mailing system.

## Install

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Put your private `professors.csv`, `cv.pdf`, and `email_template.txt` in `private_data/`. Start from
[`examples/professors.sample.csv`](examples/professors.sample.csv) and
[`templates/email_template.example.txt`](templates/email_template.example.txt). Everything personal in
`private_data/`, plus generated drafts and audit logs, is ignored by Git.

## Preview, draft, and send

Preview rendering without reading the CV, creating files, changing duplicate state, or sending:

```powershell
python src/main.py --preview --limit 1
```

Sample output:

```text
--- Preview 1: Dr Example Researcher <researcher@example.edu> ---
Dear Professor Researcher,
...
INFO: Previewed 1 eligible email(s); no files created and nothing sent.
```

Create reviewable `.eml` files in `logs/drafts/`:

```powershell
python src/main.py --mode draft_only --limit 5
```

Record an unsubscribe or other do-not-contact request immediately:

```powershell
python src/main.py --opt-out person@example.edu
```

## SMTP providers and real sending

Set `SMTP_HOST`, `SMTP_PORT`, the SSL/STARTTLS mode, `SMTP_USERNAME`, and `SMTP_PASSWORD` in `.env`.
The example contains Gmail SSL defaults, but the transport is provider-neutral. Then use a very small batch:

```powershell
python src/main.py --mode send --limit 2
```

The sender retries transient connection failures with configurable exponential backoff. Authentication,
recipient rejection, and permanent SMTP errors are surfaced clearly rather than retried indefinitely.

### Credential security

App passwords grant meaningful account access. Create a dedicated credential, keep `.env` local, never paste
it into issues or logs, and revoke it if the machine or repository is exposed. OAuth2 is preferable where a
provider supports it, but OAuth2 is not implemented in this release; use draft mode if password-based SMTP
does not meet your security requirements. The legacy `EMAIL_APP_PASSWORD` variable still works, while new
configurations should use `SMTP_PASSWORD`.

## Configuration

See [`.env.example`](.env.example) for every setting. Important controls include:

| Setting | Default | Meaning |
|---|---:|---|
| `DAILY_LIMIT` | `10` | Daily send limit; values above 10 are capped |
| `SEND_DELAY_MIN_SECONDS` | `120` | Minimum delay; values below 120 are rejected |
| `SEND_DELAY_MAX_SECONDS` | `300` | Maximum randomized delay |
| `SMTP_RETRIES` | `2` | Retries after the initial transient failure |
| `SMTP_RETRY_BACKOFF_SECONDS` | `2` | Base exponential retry delay |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |

Runtime events use Python logging; processing outcomes remain in the private CSV audit log for duplicate,
daily-limit, and opt-out enforcement.

## Troubleshooting

- **CSV is malformed or missing columns:** save it as UTF-8 CSV and copy the exact four sample headers.
- **Authentication fails:** verify the provider host, port, encryption mode, username, and dedicated password.
- **Gmail rejects a normal password:** Gmail SMTP typically requires 2-Step Verification plus an App Password.
- **No eligible emails:** inspect warnings and `logs/email_log.csv`; prior drafts, sends, and opt-outs are skipped.
- **Template rendering fails:** only use defined fields such as `{{ last_name }}` and `{{ domain }}`.

## Development

```powershell
pytest
ruff check src tests
```

GitHub Actions runs both commands on Python 3.10 and 3.12 for every push and pull request.

## License

MIT — see [`LICENSE`](LICENSE).
