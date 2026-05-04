import decimal
from functools import reduce
import sys
import argparse
from datetime import datetime, timedelta, timezone
import datedelta
import stripe
import stripe_datev.invoices, \
  stripe_datev.charges, \
  stripe_datev.customer, \
  stripe_datev.payouts, \
  stripe_datev.recognition, \
  stripe_datev.output, \
  stripe_datev.config
import os, os.path
import requests
import dotenv

dotenv.load_dotenv()

if "STRIPE_API_KEY" not in os.environ:
  print("Require STRIPE_API_KEY environment variable to be set")
  sys.exit(1)

stripe.api_key = os.environ["STRIPE_API_KEY"]
stripe.api_version = "2020-08-27"

out_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'out')
if stripe.api_key.startswith("sk_test"):
  out_dir = os.path.join(out_dir, "test")
if not os.path.exists(out_dir):
  os.mkdir(out_dir)

class StripeDatevCli(object):

    def run(self, argv):
        parser = argparse.ArgumentParser(
          description='Stripe utility',
        )
        parser.add_argument('command', type=str, help='Subcommand to run', choices=[
          'download',
          'validate_customers',
          'fill_account_numbers',
          'list_accounts',
          'opos'
        ])

        args = parser.parse_args(argv[1:2])
        getattr(self, args.command)(argv[2:])

    def download(self, argv):
        parser = argparse.ArgumentParser(prog="stripe-datev-cli.py download")
        parser.add_argument('year', type=int, nargs='?', help='year to download data for')
        parser.add_argument('month', type=int, nargs='?', help='month to download (0 = full year)')
        parser.add_argument('--since', type=str, metavar='DATE',
            help='incremental mode: download changes since DATE (YYYY-MM-DD) or "last"')

        args = parser.parse_args(argv)

        now = datetime.now(tz=stripe_datev.config.accounting_tz)
        since_mode = False
        last_download_file = os.path.join(out_dir, '.last_download')

        if args.since is not None:
            since_mode = True
            if args.since == 'last':
                if not os.path.exists(last_download_file):
                    print("No previous download timestamp found. Run a full month download first, or specify a date with --since YYYY-MM-DD")
                    sys.exit(1)
                with open(last_download_file) as f:
                    fromTime = datetime.fromisoformat(f.read().strip())
            else:
                fromTime = stripe_datev.config.accounting_tz.localize(
                    datetime.strptime(args.since, "%Y-%m-%d")
                )
            toTime = now
            thisMonth = now.strftime("%Y-%m")
            print("Retrieving data since {} (incremental)".format(fromTime.strftime("%Y-%m-%d %H:%M")))
        elif args.year is not None and args.month is not None:
            year = args.year
            month = args.month
            if month > 0:
                fromTime = stripe_datev.config.accounting_tz.localize(datetime(year, month, 1, 0, 0, 0, 0))
                toTime = fromTime + datedelta.MONTH
            else:
                fromTime = stripe_datev.config.accounting_tz.localize(datetime(year, 1, 1, 0, 0, 0, 0))
                toTime = fromTime + datedelta.YEAR
            thisMonth = fromTime.strftime("%Y-%m")
            print("Retrieving data between {} and {}".format(fromTime.strftime("%Y-%m-%d"), (toTime - timedelta(0, 1)).strftime("%Y-%m-%d")))
        else:
            parser.error("Specify YEAR MONTH or --since DATE")
            return

        invoices = list(reversed(list(stripe_datev.invoices.listFinalizedInvoices(fromTime, toTime))))
        print("Retrieved {} invoice(s), total {} EUR".format(len(invoices), sum([decimal.Decimal(i.total) / 100 for i in invoices])))

        revenue_items = stripe_datev.invoices.createRevenueItems(invoices)

        charges = list(stripe_datev.charges.listChargesRaw(fromTime, toTime))
        print("Retrieved {} charge(s), total {} EUR".format(len(charges), sum([decimal.Decimal(c.amount) / 100 for c in charges])))

        direct_charges = list(filter(lambda charge: not stripe_datev.charges.chargeHasInvoice(charge), charges))
        revenue_items += stripe_datev.charges.createRevenueItems(direct_charges)

        overview_dir = os.path.join(out_dir, "overview")
        if not os.path.exists(overview_dir):
            os.mkdir(overview_dir)

        if since_mode:
            overview_name = "overview-since-{}.csv".format(fromTime.strftime("%Y-%m-%d"))
        else:
            overview_name = "overview-{:04d}-{:02d}.csv".format(year, month)

        with open(os.path.join(overview_dir, overview_name), "w", encoding="utf-8") as fp:
            fp.write(stripe_datev.invoices.to_csv(invoices))
            print("Wrote {} invoices      to {}".format(str(len(invoices)).rjust(4, " "), os.path.relpath(fp.name, os.getcwd())))

        monthly_recognition_dir = os.path.join(out_dir, "monthly_recognition")
        if not os.path.exists(monthly_recognition_dir):
            os.mkdir(monthly_recognition_dir)

        if since_mode:
            recognition_name = "monthly_recognition-since-{}.csv".format(fromTime.strftime("%Y-%m-%d"))
        else:
            recognition_name = "monthly_recognition-{}.csv".format(thisMonth)

        with open(os.path.join(monthly_recognition_dir, recognition_name), "w", encoding="utf-8") as fp:
            fp.write(stripe_datev.invoices.to_recognized_month_csv2(revenue_items))
            print("Wrote {} revenue items to {}".format(str(len(revenue_items)).rjust(4, " "), os.path.relpath(fp.name, os.getcwd())))

        datevDir = os.path.join(out_dir, 'datev')
        if not os.path.exists(datevDir):
            os.mkdir(datevDir)

        # Revenue accounting records

        records = []
        for revenue_item in revenue_items:
            records += stripe_datev.invoices.createAccountingRecords(revenue_item)

        records_by_month = {}
        for record in records:
            rec_month = record["date"].strftime("%Y-%m")
            records_by_month[rec_month] = records_by_month.get(rec_month, []) + [record]

        # Charge accounting records

        charge_records = stripe_datev.charges.createAccountingRecords(charges)

        charges_by_month = {}
        for record in charge_records:
            rec_month = record["date"].strftime("%Y-%m")
            charges_by_month[rec_month] = charges_by_month.get(rec_month, []) + [record]

        # Payouts and contributions

        payoutObjects = list(stripe_datev.payouts.listPayouts(fromTime, toTime))
        print("Retrieved {} payout(s), total {} EUR".format(len(payoutObjects), sum([r["amount"] for r in payoutObjects])))

        payout_records = stripe_datev.payouts.createAccountingRecords(payoutObjects)

        balance_transactions = list(stripe.BalanceTransaction.list(
            created={
                "lt": int(toTime.timestamp()),
                "gte": int(fromTime.timestamp()),
            },
            type="contribution",
        ).auto_paging_iter())
        print("Retrieved {} contribution(s), total {} EUR".format(len(balance_transactions), sum([-decimal.Decimal(b["amount"]) / 100 for b in balance_transactions])))

        contribution_records = stripe_datev.payouts.createAccountingRecordsContributions(balance_transactions)

        # Cancelled invoices (since mode only)
        # Finds invoices voided, marked uncollectible, or credited since fromTime that are
        # NOT already included in the regular fetch above (those were finalized after fromTime).
        # Only emits records dated >= fromTime to avoid re-booking the original invoice.

        cancelled_invoices = []
        if since_mode:
            already_fetched = {inv.id for inv in invoices}
            cancelled_invoices = [
                inv for inv in stripe_datev.invoices.listCancelledInvoicesSince(fromTime)
                if inv.id not in already_fetched
            ]
            print("Found {} cancelled/voided/credited invoice(s) since {}".format(
                len(cancelled_invoices), fromTime.strftime("%Y-%m-%d")))

            if cancelled_invoices:
                cancelled_items = stripe_datev.invoices.createRevenueItems(cancelled_invoices)
                from_ts = fromTime.timestamp()
                for item in cancelled_items:
                    for record in stripe_datev.invoices.createAccountingRecords(item):
                        if record["date"].timestamp() >= from_ts:
                            rec_month = record["date"].strftime("%Y-%m")
                            records_by_month[rec_month] = records_by_month.get(rec_month, []) + [record]

        # Write DATEV files

        for rec_month, month_records in records_by_month.items():
            if rec_month == thisMonth:
                name = "EXTF_{}_Revenue.csv".format(thisMonth)
            else:
                name = "EXTF_{}_Revenue_From_{}.csv".format(rec_month, thisMonth)
            stripe_datev.output.writeRecords(os.path.join(datevDir, name), month_records, bezeichung="Stripe Revenue {} from {}".format(rec_month, thisMonth))

        for rec_month, month_records in charges_by_month.items():
            if rec_month == thisMonth:
                name = "EXTF_{}_Charges.csv".format(thisMonth)
            else:
                name = "EXTF_{}_Charges_From_{}.csv".format(rec_month, thisMonth)
            stripe_datev.output.writeRecords(os.path.join(datevDir, name), month_records, bezeichung="Stripe Charges/Fees {} from {}".format(rec_month, thisMonth))

        stripe_datev.output.writeRecords(
            os.path.join(datevDir, "EXTF_{}_Payouts.csv".format(thisMonth)),
            payout_records,
            bezeichung="Stripe Payouts {}".format(thisMonth)
        )
        stripe_datev.output.writeRecords(
            os.path.join(datevDir, "EXTF_{}_Contributions.csv".format(thisMonth)),
            contribution_records,
            bezeichung="Stripe Contributions {}".format(thisMonth)
        )

        # Invoice PDFs

        pdfDir = os.path.join(out_dir, 'pdf')
        if not os.path.exists(pdfDir):
            os.mkdir(pdfDir)

        for invoice in invoices:
            pdfLink = invoice.invoice_pdf
            finalized_date = datetime.fromtimestamp(invoice.status_transitions.finalized_at, timezone.utc).astimezone(stripe_datev.config.accounting_tz)
            fileName = "{} {}.pdf".format(finalized_date.strftime("%Y-%m-%d"), invoice.number)
            filePath = os.path.join(pdfDir, fileName)
            if os.path.exists(filePath):
                continue
            print("Downloading {} to {}".format(pdfLink, filePath))
            r = requests.get(pdfLink)
            if r.status_code != 200:
                print("HTTP status {}".format(r.status_code))
                continue
            with open(filePath, "wb") as fp:
                fp.write(r.content)

        # Credit note PDFs for cancelled invoices

        for invoice in cancelled_invoices:
            if invoice.post_payment_credit_notes_amount > 0:
                for cn in stripe.CreditNote.list(invoice=invoice.id).data:
                    cn_date = datetime.fromtimestamp(cn.created, timezone.utc).astimezone(stripe_datev.config.accounting_tz)
                    fileName = "{} {}_credit_note.pdf".format(cn_date.strftime("%Y-%m-%d"), cn.number or cn.id)
                    filePath = os.path.join(pdfDir, fileName)
                    if os.path.exists(filePath):
                        continue
                    print("Downloading credit note {} to {}".format(cn.pdf, filePath))
                    r = requests.get(cn.pdf)
                    if r.status_code != 200:
                        print("HTTP status {}".format(r.status_code))
                        continue
                    with open(filePath, "wb") as fp:
                        fp.write(r.content)

        # Save timestamp so --since last works on the next run
        with open(last_download_file, 'w') as f:
            f.write(now.isoformat())

    def validate_customers(self, argv):
      stripe_datev.customer.validate_customers()

    def fill_account_numbers(self, argv):
      pass

    def list_accounts(self, argv):
      pass

    def opos(self, argv):
      if len(argv) > 0:
        ref = datetime(*list(map(int, argv))) + timedelta(days=1) - timedelta(seconds=1)
        status = None
      else:
        ref = datetime.now()
        status = "open"

      print("Unpaid invoices as of", stripe_datev.config.accounting_tz.localize(ref))

      invoices = stripe.Invoice.list(
        created={
          "lte": int(ref.timestamp()),
          "gte": int((ref - datedelta.YEAR).timestamp()),
        },
        status=status,
        expand=["data.customer"]
      ).auto_paging_iter()

      totals = []
      for invoice in invoices:
        finalized_at = invoice.status_transitions.get("finalized_at", None)
        if finalized_at is None or datetime.utcfromtimestamp(finalized_at) > ref:
          continue
        marked_uncollectible_at = invoice.status_transitions.get("marked_uncollectible_at", None)
        if marked_uncollectible_at is not None and datetime.utcfromtimestamp(marked_uncollectible_at) <= ref:
          continue
        voided_at = invoice.status_transitions.get("voided_at", None)
        if voided_at is not None and datetime.utcfromtimestamp(voided_at) <= ref:
          continue
        paid_at = invoice.status_transitions.get("paid_at", None)
        if paid_at is not None and datetime.utcfromtimestamp(paid_at) <= ref:
          continue

        customer = stripe_datev.customer.retrieveCustomer(invoice.customer)
        due_date = datetime.utcfromtimestamp(invoice.due_date if invoice.due_date else invoice.created)
        total = decimal.Decimal(invoice.total) / 100
        totals.append(total)
        print(invoice.number.ljust(13, " "), format(total, ",.2f").rjust(10, " "), "EUR", customer.email.ljust(35, " "), "due", due_date.date(), "({} overdue)".format(ref - due_date) if due_date < ref else "")

      total = reduce(lambda x, y: x + y, totals, decimal.Decimal(0))
      print("TOTAL        ", format(total, ",.2f").rjust(10, " "), "EUR")

if __name__ == '__main__':
    StripeDatevCli().run(sys.argv)