# Professor Email Automation

A safe Python tool for creating personalized Master by Research outreach emails. It creates reviewable `.eml` drafts by default and can optionally send through Gmail.

## Safety

- Draft mode is the default; nothing is sent automatically.
- Real sending requires typing `SEND` exactly.
- Maximum 10 sent emails per day.
- Random 2-5 minute delay between sends.
- Previously drafted or sent addresses are skipped.
- Missing, invalid, and generic addresses are skipped.

Always verify professor information and review every draft before sending.

## Installation

Python 3.10 or newer is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Add your information

Keep personal files inside `private_data/`. Git ignores this folder, so its contents will not be published.

Add these three files:

- `private_data/professors.csv` - your verified professor list
- `private_data/cv.pdf` - your CV
- `private_data/email_template.txt` - your personalized email

Use `examples/professors.sample.csv` for the required CSV headers. Copy `templates/email_template.example.txt` as a starting template, replace the bracketed instructions, and keep `{{ last_name }}` and `{{ domain }}` unchanged.

## Create drafts

```powershell
python src/main.py --mode draft_only --limit 5
```

Review drafts in `logs/drafts/` and results in `logs/email_log.csv`.

## Optional Gmail sending

Enable Google 2-Step Verification and create a Gmail App Password. Add your credentials to the private `.env` file:

```env
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_APP_PASSWORD=your_app_password
```

Then run a small batch:

```powershell
python src/main.py --mode send --limit 5
```

Type `SEND` when prompted to confirm real sending. Never commit `.env`, your CV, professor data, drafts, or logs.

## Customization

- Change the main message in `private_data/email_template.txt`.
- Change file paths or the daily limit in `.env`.
- Replace `private_data/professors.csv` whenever you update your verified list.

The tool uses only the supplied CSV and does not scrape websites.

## License

MIT - anyone may use, modify, and share the project under the terms in `LICENSE`.
