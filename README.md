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

## Beginner setup (Windows)

You need Python 3.10 or newer. Download it from [python.org](https://www.python.org/downloads/) if needed.
During installation, select **Add Python to PATH**.

### 1. Get the project

The easiest method is:

1. Click the green **Code** button near the top of this GitHub page.
2. Click **Download ZIP**.
3. Extract the ZIP file.
4. Open the extracted `supervisor-email-assistant` folder.

If you already use Git, you may clone it instead:

```powershell
git clone https://github.com/sarweralam867/supervisor-email-assistant.git
```

### 2. Open PowerShell in the project folder

In File Explorer, open the folder containing `README.md` and `pyproject.toml`. Click the address bar, type
`powershell`, and press **Enter**. A PowerShell window will open in the correct folder.

### 3. Install the project

Copy all five lines below, paste them into PowerShell, and press **Enter**:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
Copy-Item examples\professors.sample.csv private_data\professors.csv
Copy-Item templates\email_template.example.txt private_data\email_template.txt
```

Wait until installation finishes. You do not need to activate anything or change PowerShell security
settings. If PowerShell says `python` is not recognized, reinstall Python with **Add Python to PATH** selected,
then close and reopen PowerShell.

### 4. Add your information

Open the `private_data` folder and prepare these three files:

1. Rename or copy your CV to exactly `cv.pdf`.
2. Open `professors.csv` in Excel and add verified professor details. Save it as a CSV file.
3. Open `email_template.txt` in Notepad and replace every `[BRACKETED ITEM]` with your information.

Do not change `{{ last_name }}` or `{{ domain }}` in the email template. They are filled automatically.
The examples below show the required formats.

### 5. Check your email before creating anything

Return to the same PowerShell window and run:

```powershell
.venv\Scripts\python.exe src\main.py --preview --limit 1
```

You should see one personalized email in PowerShell. Nothing is sent and no draft is created. If it looks
correct, continue to the **Preview, draft, and send** section below.

### Professor list example

Keep the same CSV headers. The addresses below are fictional; replace them with addresses you verified
yourself.

```csv
No,Priority,Professor / Researcher,Email,University,Lab / Group / Centre,Best-fit Domain,Outreach Note,Verification Status,Official Source
1,High,Dr Example Researcher,researcher@example.edu,Example University,AI Lab,medical imaging,Interested in recent imaging research,Verified,https://example.edu/profile
2,Medium,Prof Sample Scientist,scientist@example.org,Sample University,Vision Group,computer vision,Relevant vision projects,Verified,https://example.org/profile
```

### Email template example

The template supports `{{ last_name }}` and `{{ domain }}`. Save your version as
`private_data/email_template.txt`.

```text
Dear Professor {{ last_name }},

I hope you are doing well.

My name is Your Name. I am interested in pursuing a research degree in {{ domain }} and am writing to ask
whether you are currently accepting research students. My background in [your relevant experience] aligns
with your work on [specific topic or project].

I have attached my CV for your review. Thank you for your time and consideration.

Kind regards,
Your Name
your.email@example.com
```

Edit `.env` only if you need different paths or SMTP settings. Private inputs, generated drafts, and audit
logs are ignored by Git.

### Change the email subject

Open `.env` and edit this line:

```env
EMAIL_SUBJECT=Prospective Master by Research/MPhil Student - Medical AI
```

This changes the subject for all new drafts and sent emails. Existing `.eml` drafts are not changed.

## Preview, draft, and send

Preview rendering without reading the CV, creating files, changing duplicate state, or sending:

```powershell
.venv\Scripts\python.exe src\main.py --preview --limit 1
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
.venv\Scripts\python.exe src\main.py --mode draft_only --limit 5
```

Record an unsubscribe or other do-not-contact request immediately:

```powershell
.venv\Scripts\python.exe src\main.py --opt-out person@example.edu
```

## SMTP providers and real sending

Set `SMTP_HOST`, `SMTP_PORT`, the SSL/STARTTLS mode, `SMTP_USERNAME`, and `SMTP_PASSWORD` in `.env`.
The example contains Gmail SSL defaults, but the transport is provider-neutral. Then use a very small batch:

```powershell
.venv\Scripts\python.exe src\main.py --mode send --limit 2
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
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check src tests
```

GitHub Actions runs both commands on Python 3.10 and 3.12 for every push and pull request.

## License

MIT — see [`LICENSE`](LICENSE).
