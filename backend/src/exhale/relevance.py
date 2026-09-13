"""Is this a household obligation, or a company talking to a customer?

The credibility layer already asks how *authoritative* an artifact is
(:mod:`exhale.credibility`). This asks a different question: whether the fact
belongs to the household's logistics at all.

They come apart on retail mail. "Your Target Drive Up order is ready" is a
genuine CONFIRMATION with an explicit date — it clears every authority bar
and auto-commits. But nobody needs Exhale to remember it, and on a real
household it did two kinds of damage:

* it auto-committed, and then had to be corrected — the trust ledger read
  43% (20 of 35 auto-commits needed a fix), almost all of it retail noise;
* it taught the pattern learner a "rhythm": *"order on draw and get in
  lottery credits recurs on Mondays"* is a mailing schedule, not a family's.

So a transactional notice is held for a human rather than committed, and is
never allowed to teach a recurring rule.

The cue list is deliberately narrow. It targets notifications *about a
commercial relationship* — orders, shipments, statements, digests, account
security — and pointedly excludes words that also name real household
obligations: bare "payment" (tuition is a payment), "reminder" (the game
reminder is real), "appointment", "registration". A false positive here
costs one confirmation tap; a false negative puts junk in the graph and
teaches a fake rhythm.
"""

from __future__ import annotations

import re

# Notifications about a commercial/account relationship, not a family plan.
_TRANSACTIONAL = re.compile(
    r"\b("
    # fulfilment
    r"order|orders|ordered|shipment|shipped|shipping|delivery|delivered|"
    r"tracking|dispatched|out for delivery|drive ?up|curbside|"
    # money-as-account (NOT bare "payment": tuition is a payment)
    r"statement|invoice|receipt|autopay|auto-?pay|billing|refund|"
    # loyalty / promo
    r"rewards|loyalty|points|coupon|promo|promotion|sale ends|"
    # mailing-list machinery
    r"digest|unsubscribe|newsletter|weekly recap|"
    # account & security plumbing
    r"password|passkey|sign-?in|log ?in|verify your|account data|"
    r"security alert|two-factor"
    r")\b",
    re.IGNORECASE,
)


def is_transactional_notice(text: str | None) -> bool:
    """True when the text reads as a company notifying a customer.

    Judged on the extracted title, which is what both callers have: routing
    sees a payload, the learner sees a ledger entry.
    """

    return bool(text) and bool(_TRANSACTIONAL.search(text))
