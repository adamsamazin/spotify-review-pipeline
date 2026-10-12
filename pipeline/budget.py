"""Spend ledger shared by every paid stage.

Spent money is recomputed from saved call usage x cost/rates.csv across *all* runs, so the
cap covers the whole assignment, not one run. Before each request the caller reserves an
estimated worst-case cost; work stops when spent + reserved + next reservation > cap.
"""

import csv
import os
import sqlite3
import threading
from pathlib import Path

from pipeline.contract import ROOT

RATES_PATH = ROOT / "cost" / "rates.csv"


class BudgetExceeded(Exception):
    pass


def load_rates(path=RATES_PATH):
    rates = {}
    with Path(path).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            rates[(r["model"], r["billing_item"])] = float(r["price_per_unit"])
    return rates


def call_cost(rates, model, input_tokens, output_tokens):
    """Mutually exclusive billing items x price per unit. Unknown model -> KeyError (never silently $0)."""
    if model and model.startswith("fake-") and (model, "input_tokens") not in rates:
        return 0.0  # offline test double: free unless a test gives it a price explicitly
    return (input_tokens or 0) * rates[(model, "input_tokens")] + (output_tokens or 0) * rates[(model, "output_tokens")]


def spent_across_runs(rates, runs_dir=ROOT / "runs"):
    """Known usage is repriced from current rates; calls with unknown usage count at their saved estimate."""
    total = 0.0
    for db_path in Path(runs_dir).glob("*/state.sqlite"):
        db = sqlite3.connect(db_path)
        try:
            rows = db.execute("SELECT model, input_tokens, output_tokens, cost_usd FROM calls").fetchall()
        except sqlite3.OperationalError:  # run not enriched yet
            rows = []
        db.close()
        total += sum(call_cost(rates, m, i, o) if i is not None else (c or 0) for m, i, o, c in rows)
    return total


class Ledger:
    def __init__(self, cap_usd=None, rates=None):
        self.rates = rates or load_rates()
        self.cap = float(cap_usd if cap_usd is not None else os.environ.get("SPEND_CAP_USD", "10"))
        self.spent = spent_across_runs(self.rates)
        self.reserved = 0.0
        self._lock = threading.Lock()

    def reserve(self, est_usd):
        with self._lock:
            if self.spent + self.reserved + est_usd > self.cap:
                raise BudgetExceeded(f"spent ${self.spent:.4f} + reserved ${self.reserved:.4f} + next "
                                     f"${est_usd:.4f} would exceed cap ${self.cap:.2f}")
            self.reserved += est_usd

    def settle(self, est_usd, model, input_tokens, output_tokens):
        with self._lock:
            self.reserved -= est_usd
            actual = call_cost(self.rates, model, input_tokens, output_tokens) if input_tokens is not None else est_usd
            self.spent += actual  # unknown usage (e.g. timeout) is charged at the reservation
            return actual
