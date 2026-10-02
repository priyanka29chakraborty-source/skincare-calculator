# Going live with paid credits

Everything in this document is a step only you can take — it needs accounts,
keys and decisions that cannot be made from the code.

`GET /api/readiness` is the check. It reports `ready_to_charge: true` only when
the ledger is durable, sessions survive a restart, Razorpay is configured, and
`DEV_UNLOCK_ALL` is off. Hit it after each change below.

---

## 0. Switching the paywall on (and what it covers)

Everything is visible today. One variable closes the gate:

```
PAYWALL_ENABLED=1
```

Unset, `_resolve_entitlement` returns `True` for every request and no credit is
ever spent. Set, it reads the signed session cookie and spends one credit per
product. Both states are covered by tests — `test_paid_flow.py` runs with it on,
`test_paywall_off.py` with it off — so this is a configuration change, not a
development project.

`GET /api/readiness` reports `paywall_enabled` and `currently_charging`.

### What is free, and why

Free is everything about the **product**: the formulation score and the full
reasoning behind it, the ingredient list and identified actives, price and
value, pH, conflicts, and all safety warnings. That answer is identical for
every reader, which makes it cacheable, shareable and the reason anyone finds
the site. Gating it would make the tool useless as a reference and kill the
thing that brings people in.

Pregnancy warnings and declared-allergen warnings are **always** free, even
with the paywall on. Charging someone to learn a product may be unsafe for them
in pregnancy is not a business model.

### What a credit buys

Everything about **you** — in `PAID_KEYS` in `backend/entitlement.py`:

| Gated now | Key |
|---|---|
| How well it treats your concerns | `skin_concern_fit` |
| Whether it suits your skin type | `skin_type_compatibility`, `skin_type_details`, `skin_type_risk_level` |
| Pore-clogging and allergen risk for you | `comedogenic_warnings`, `allergen_warnings` |
| What would suit you better | `better_suited`, `upgrade_suggestions` |
| The three personalisation questions | `personalisation` |

### Still to gate

These are built but not behind the gate yet, because you have now said they
should be. Each needs a decision from you about *how*, not whether:

- **PDF export.** The report is generated in the browser from data already
  sent, so gating it means gating the data, not the button. Simplest honest
  version: the report renders only for a product the account has unlocked —
  which, given billing is per product, it already has if they paid for it.
  So this falls out for free once the paywall is on.
- **Comparison.** Currently free and deliberately so, because it compares
  formulation scores and those are free. If it is to be paid, the natural
  line is: the score table stays free, and the parts that depend on *you* —
  per-concern comparison, layering advice, `choose_if` — cost a credit. That
  keeps the free half useful enough to attract people.
- **Personalisation.** `personalisation` is already in `PAID_KEYS`, but the
  "Answer 3 questions" card is shown to everyone and the re-analysis is free.
  With the paywall on it will return a locked card; the card needs copy that
  says so before the questions, not after.

Tell me which of those three you want and I will wire them.

---

## 1. The credit ledger must be on PostgreSQL

**This is the one that loses money if you skip it.**

Without `AIVEN_PG_URL` the ledger runs on a SQLite file next to the code. That
is correct for local development. On Render it is not: the filesystem is
ephemeral unless you have explicitly attached a disk, so a restart — a deploy,
a crash, a platform migration — deletes the file and with it every credit a
customer has paid for. They would have no record and you would have no way to
restore one.

```
AIVEN_PG_URL=postgres://user:pass@host:port/dbname?sslmode=require
```

The app already uses this variable for its analytics tables, so if the backend
is logging to Postgres today the ledger will use the same database. Tables are
created on first use; nothing to migrate.

Readiness reports this as `ledger_durable`.

---

## 2. Session secret

```
SESSION_SECRET=<64+ random characters>
```

Generate it once and never change it:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Without it the server generates a random secret at startup, which is safe but
signs every customer out on every deploy. Changing it later has the same
effect. Readiness reports this as `session_secret_persistent`.

---

## 3. Razorpay

You need a Razorpay account with KYC completed before live keys are issued;
test keys work immediately.

```
RAZORPAY_KEY_ID=rzp_live_xxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxxxxx
```

In the Razorpay dashboard, add a webhook:

- **URL** — `https://<your-backend>/api/credits/webhook`
- **Event** — `payment.captured` (that one only)
- **Secret** — whatever you set as `RAZORPAY_WEBHOOK_SECRET`

The webhook is not optional. It is the only path that delivers credits when a
customer closes the tab mid-redirect, which is exactly when a payment is most
likely to be charged and least likely to be confirmed in the browser.

Verify end to end in test mode before switching to live keys: buy a pack with
Razorpay's test card, confirm the balance moves, then replay the same webhook
from the dashboard and confirm the balance does **not** move again.

With no keys set, the app says payments are not switched on rather than
offering a button that fails. That is a safe state to deploy in.

---

## 4. Email delivery for sign-in codes

```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM="Urancal <hello@urancal.com>"
```

Use a transactional provider (Resend, Postmark, SES, Brevo) rather than a
personal mailbox — a Gmail account will start dropping sign-in codes as volume
grows, and the customer's experience of that is "the code never arrived".

Set up SPF and DKIM on the sending domain. Six-digit codes from an
unauthenticated domain land in spam, and you will read that as "nobody is
signing up".

`MAIL_DEV_ECHO=1` prints codes to the log instead of sending them. It exists
for local development. **Never set it in production** — it would write login
codes into your logs. It is deliberately a separate variable rather than a
fallback for missing SMTP, so a misconfiguration fails loudly instead of
quietly echoing codes.

---

## 5. Turn off the development unlock

```
DEV_UNLOCK_ALL=    (unset it entirely)
```

While it is on, every caller gets the paid analysis for free. Readiness reports
it as a warning.

---

## 6. Amazon affiliate (optional, and separate)

Only `amazon.in` is configured, with the tag `pc2920-21`:

```
AMAZON_TAG_IN=pc2920-21
```

Associates IDs are **per locale**. An India tag on `amazon.com` earns nothing
and breaches the per-locale enrolment requirement, so other stores are left
untagged until you enrol in each one and set its variable
(`AMAZON_TAG_COM`, `AMAZON_TAG_UK`, and so on — see `affiliate.py`).

Two things worth knowing:

- Amazon requires the disclosure to be displayed. The app attaches it
  automatically to any response containing a tagged link, so it cannot ship
  tagged links without it.
- New Associates accounts are closed if they do not make qualifying sales
  within 180 days.

---

## Still outstanding before charging money

These are not code problems, and none of them can be closed from here.

1. **The 21 pregnancy-safety contradictions were resolved by rule, not by a
   clinician.** Where the JSON and CSV disagreed, the JSON won. That is a
   consistent rule, not a medical judgement. Before you take money from someone
   who is pregnant and relying on this, have those 21 entries reviewed against
   AAD/ACOG guidance by someone qualified to do it.

2. **About 96% of ingredient records carry no citation.** The scoring is
   defensible and the method is documented, but "evidence quality" as a scored
   dimension invites the question "according to what", and right now most
   entries have no answer. This is the gap between a good tool and one a
   dermatologist would recommend — and it is what you are charging for.

3. **Indian GST.** Razorpay is a payment gateway, not a merchant of record, so
   the tax obligation on these sales is yours. Worth an accountant's half hour
   before the first live payment rather than after.

4. **A refund policy, and the page that states it.** The ledger supports
   refunds (`wallet.refund`), but there is no published policy and no customer
   route to request one.
