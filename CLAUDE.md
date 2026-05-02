# Stripe DATEV Exporter

A Python CLI that pulls Stripe financial data and exports it in DATEV format for German tax accounting. Forked from [jonaswitt/stripe-datev-exporter](https://github.com/jonaswitt/stripe-datev-exporter) with Customer ID dependency removed.

## What it does

Fetches one month (or full year) of Stripe data and writes structured outputs:

| Output file | Contents |
|---|---|
| `out/overview/overview-YYYY-MM.csv` | Invoice summary with customer details |
| `out/monthly_recognition/monthly_recognition-YYYY-MM.csv` | Revenue recognition split across service periods (pRAP) |
| `out/datev/EXTF_YYYY-MM_Revenue.csv` | DATEV booking records for invoices |
| `out/datev/EXTF_YYYY-MM_Charges.csv` | DATEV booking records for direct (non-invoice) charges |
| `out/datev/EXTF_YYYY-MM_Payouts.csv` | DATEV booking records for Stripe payouts to bank |
| `out/datev/EXTF_YYYY-MM_Contributions.csv` | DATEV booking records for Stripe contributions |
| `out/pdf/*.pdf` | Invoice PDFs downloaded from Stripe |
| `out/pdf/*.html` | Charge receipt HTML pages (currently downloaded but not needed) |

When using a test API key (`sk_test_...`) all output goes under `out/test/`.

## Setup

```bash
virtualenv -p python3 venv
. venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set STRIPE_API_KEY
```

## Commands

```bash
# Export one month
python stripe-datev-cli.py download 2024 1

# Export full year (month = 0)
python stripe-datev-cli.py download 2024 0

# List unpaid invoices (open outstanding)
python stripe-datev-cli.py opos

# List unpaid invoices as of a specific date
python stripe-datev-cli.py opos 2024 12 31

# Check customer tax/VAT configuration
python stripe-datev-cli.py validate_customers
```

## Configuration

| Variable | File | Default | Description |
|---|---|---|---|
| `STRIPE_API_KEY` | `.env` | required | Stripe secret key |
| `accounting_tz` | `stripe_datev/config.py` | `Europe/Berlin` | Accounting timezone |
| `berater_nr` | `stripe_datev/config.py` | `1` | DATEV Beraternummer |
| `mandenten_nr` | `stripe_datev/config.py` | `1` | DATEV Mandantennummer |

## Module overview

- **stripe-datev-cli.py** — Entry point; orchestrates download flow and writes all files
- **stripe_datev/invoices.py** — Fetches finalized invoices, builds revenue items, handles voids/credits/pRAP
- **stripe_datev/charges.py** — Fetches direct (non-invoice) charges, skips fully refunded ones
- **stripe_datev/payouts.py** — Fetches payouts and balance contributions
- **stripe_datev/customer.py** — Resolves customer country/VAT status → DATEV revenue account (8400/8336/8338)
- **stripe_datev/recognition.py** — `split_months()`: splits a prepaid amount across calendar months
- **stripe_datev/output.py** — Writes EXTF v700 DATEV CSV files (data category 21)
- **stripe_datev/dateparser.py** — Extracts service-period dates from invoice line descriptions
- **stripe_datev/config.py** — Timezone and DATEV identity numbers

## Tax / VAT account mapping

| Customer type | DATEV account | Tax key |
|---|---|---|
| DE domestic | 8400 | — |
| EU with valid VAT ID | 8336 | 40 |
| Non-EU / world | 8338 | 0 |

## DATEV output format

Files follow the EXTF (Externe Finanzbuchhaltung) format, version 700, data category 21. Semicolon-delimited, UTF-8 with BOM, two-line header. Import directly into DATEV Buchungsstapel.
