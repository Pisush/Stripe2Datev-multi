# Stripe DATEV Exporter

Took https://github.com/jonaswitt/stripe-datev-exporter and changed it using GPT-4 to drop the need for Customer ID, and other adjustments.

## Setup

Uses Python's virtualenv. To set up initially:

```bash
virtualenv -p python3 venv
. venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set STRIPE_API_KEY=sk_...
```

## Usage

### Export a specific month

```bash
python stripe-datev-cli.py download 2024 1
```

### Export a full year (month = 0)

```bash
python stripe-datev-cli.py download 2024 0
```

### Incremental export since a specific date

Downloads everything new since the given date. Also detects invoices from earlier months that were voided, credited, or marked uncollectible — and emits only the reversal DATEV entries for those.

```bash
python stripe-datev-cli.py download --since 2024-03-15
```

### Incremental export since the last run

Each successful download saves a timestamp to `out/.last_download`. Use `--since last` to pick up from where you left off:

```bash
python stripe-datev-cli.py download --since last
```

### List unpaid invoices

```bash
# Current open invoices
python stripe-datev-cli.py opos

# Open invoices as of a specific date
python stripe-datev-cli.py opos 2024 12 31
```

### Validate customer tax configuration

```bash
python stripe-datev-cli.py validate_customers
```

## Output

All files are written under `out/` (or `out/test/` when using a test API key):

| File | Contents |
|---|---|
| `out/overview/overview-YYYY-MM.csv` | Invoice summary with customer details |
| `out/monthly_recognition/monthly_recognition-YYYY-MM.csv` | Revenue recognition split across service periods |
| `out/datev/EXTF_YYYY-MM_Revenue.csv` | DATEV booking records for invoices |
| `out/datev/EXTF_YYYY-MM_Charges.csv` | DATEV booking records for direct charges |
| `out/datev/EXTF_YYYY-MM_Payouts.csv` | DATEV booking records for Stripe payouts |
| `out/datev/EXTF_YYYY-MM_Contributions.csv` | DATEV booking records for Stripe contributions |
| `out/pdf/*.pdf` | Invoice PDFs |
| `out/pdf/*_credit_note.pdf` | Credit note PDFs (since mode only) |

Files from `--since` mode use a `since-YYYY-MM-DD` suffix (e.g. `overview-since-2024-03-15.csv`) so they don't overwrite full-month exports.

