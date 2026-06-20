# Supervisor Email Assistant

Create personalized research-supervisor emails from your own professor list. The recommended workflow makes
complete local drafts for you to review. Nothing is sent automatically unless you deliberately choose the
advanced SMTP mode and type `SEND`.

## Choose how you want to use it

### Option 1: Easy drafts (recommended)

- No email password or SMTP setup
- One command creates every eligible draft
- A private review page opens in your browser
- Complete `.eml` files include your CV
- You review and send each message yourself

### Option 2: Automatic sending (advanced)

- Sends through your email provider's SMTP server
- Requires a provider-specific password and configuration
- Requires typing `SEND` exactly
- Sends no more than 10 emails per local day
- Waits 2-5 minutes between sends

## Easy setup for Windows

### 1. Install Python

Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). Select
**Add Python to PATH** during installation.

### 2. Download the project

On GitHub, click **Code**, then **Download ZIP**, and extract the ZIP. Open the extracted
`supervisor-email-assistant` folder.

If you already use Git, you can clone it instead:

```powershell
git clone https://github.com/sarweralam867/supervisor-email-assistant.git
cd supervisor-email-assistant
```

### 3. Open PowerShell in the project folder

In File Explorer, open the folder containing `README.md` and `pyproject.toml`. Click the address bar, type
`powershell`, and press **Enter**.

### 4. Install and create your private starter files

Paste these commands into that PowerShell window:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item examples\professors.sample.csv private_data\professors.csv
Copy-Item templates\email_template.example.txt private_data\email_template.txt
Copy-Item templates\subject.example.txt private_data\subject.txt
```

You do not need to activate the virtual environment or change PowerShell security settings.

### 5. Add four private files

Prepare these files inside `private_data`:

| File | What to put in it |
|---|---|
| `professors.csv` | Your verified professor list |
| `email_template.txt` | Your email wording and personal details |
| `cv.pdf` | Your CV, named exactly `cv.pdf` (not `cv.pdf.pdf`) |
| `subject.txt` | One subject line for new drafts |

All four files are ignored by Git and must never be committed.

#### Professor list example

Keep the same headers. These addresses are fictional; replace them with addresses you verified yourself.

```csv
No,Priority,Professor / Researcher,Email,University,Lab / Group / Centre,Best-fit Domain,Outreach Note,Verification Status,Official Source
1,High,Dr Example Researcher,researcher@example.edu,Example University,AI Lab,medical imaging,Relevant imaging research,Verified,https://example.edu/profile
2,Medium,Prof Sample Scientist,scientist@example.org,Sample University,Vision Group,computer vision,Relevant vision projects,Verified,https://example.org/profile
```

#### Email template example

The program replaces `{{ last_name }}` and `{{ domain }}` automatically.

```text
Dear Professor {{ last_name }},

I hope you are doing well.

My name is [YOUR NAME]. I am interested in pursuing a research degree in {{ domain }}. My background in
[YOUR RELEVANT EXPERIENCE] aligns with your work on [SPECIFIC TOPIC OR PROJECT].

I have attached my CV for your review. Thank you for your time and consideration.

Kind regards,
[YOUR NAME]
[YOUR EMAIL]
```

#### Subject example

`private_data/subject.txt` contains only one line:

```text
Prospective Research Student in AI/ML and Medical Imaging
```

## Make all drafts with one command

Run this in the project PowerShell window:

```powershell
.\.venv\Scripts\python.exe make_drafts.py
```

The program will:

1. Validate the professor list and skip unsafe or missing addresses.
2. Skip addresses already drafted, sent, or opted out.
3. Create complete `.eml` files with the CV attached in `logs/drafts`.
4. Create `logs/drafts/review.html` and open it in your default browser.
5. Send nothing.

On the review page, **Open in Gmail** prefills the recipient, subject, and message. For browser security,
Gmail cannot accept a local attachment through a link, so attach `private_data/cv.pdf` before sending.
The `.eml` files already contain the CV and can be opened with a compatible desktop email application such
as Outlook or Thunderbird.

Do not close your browser page until you finish reviewing. You can reopen it at any time by opening
`logs/drafts/review.html`.

## Useful safe commands

Preview one email without creating files:

```powershell
.\.venv\Scripts\python.exe src\main.py --preview --limit 1
```

Create only five local drafts:

```powershell
.\.venv\Scripts\python.exe src\main.py --mode draft_only --limit 5
```

Record an opt-out address:

```powershell
.\.venv\Scripts\python.exe src\main.py --opt-out person@example.edu
```

## Automatic sending (advanced and optional)

Choose this mode instead of Easy drafts for recipients you want the program to send automatically.
Addresses already recorded as drafted or sent are skipped to prevent duplicates.

1. Create your private configuration:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

2. Set `EMAIL_ADDRESS`, `SMTP_USERNAME`, and `SMTP_PASSWORD` for your provider. Never use or share your normal
   account password. Gmail usually requires 2-Step Verification and a separate App Password.
3. Preview one eligible message:

   ```powershell
   .\.venv\Scripts\python.exe src\main.py --preview --limit 1
   ```

4. Send one real message as a test:

   ```powershell
   .\.venv\Scripts\python.exe src\main.py --mode send --limit 1
   ```

5. Type `SEND` exactly when prompted. Successful output says `SENT`.

After a successful test, use `--limit 10` for the daily maximum. Keep PowerShell open while the program waits
between messages. Authentication failures are not retried; transient network failures use bounded backoff.

## Privacy and safety

- The program uses only your CSV and never scrapes websites.
- `.env`, everything in `private_data`, generated drafts, review pages, and logs are ignored by Git.
- Never force-add ignored files with `git add -f`.
- Public examples contain only fictional identities and addresses.
- Real sending always requires exact confirmation and is capped at 10 per local day.
- Opted-out, invalid, generic, previously drafted, and previously sent addresses are skipped.

Before pushing changes, `git status` must not show `.env`, `private_data` contents, `logs`, or `.eml` files.

## Troubleshooting

- **`python` is not recognized:** reinstall Python and select **Add Python to PATH**, then reopen PowerShell.
- **`pyproject.toml` not found:** PowerShell is in the wrong folder. Open it in the folder containing this README.
- **No eligible emails:** previous drafts/sends and invalid or missing addresses are intentionally skipped.
- **CV not found:** confirm the filename is exactly `private_data/cv.pdf`.
- **CSV error:** save it as UTF-8 CSV and keep the sample headers unchanged.
- **Template error:** keep `{{ last_name }}` and `{{ domain }}` unchanged.
- **Gmail login rejected:** revoke exposed credentials and create a fresh Gmail App Password for the same account.

## Development

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests make_drafts.py
```

GitHub Actions runs tests and lint on Python 3.10 and 3.12 for every push and pull request.

## License

MIT - see [`LICENSE`](LICENSE).
