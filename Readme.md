# Stripe DATEV Exporter

Took https://github.com/jonaswitt/stripe-datev-exporter and changed it using GPT-4 to drop the need for Customer ID, and other adjustments.

## Environment

Uses Python's virtualenv. To setup initially:

```
virtualenv -p python3 venv
```

To activate in your current shell:

```
. venv/bin/activate
pip install -r requirements.txt
export STRIPE_API_KEY=sk...
```

## Example
```
python stripe-datev-cli.py download 2023 1
```

