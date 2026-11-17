"""v0.8 analysis 9: the wrapper-marker counter, rewritten from its seven written rules (C14).

The original counting script was not retained; doc-type.csv holds its output (wrapper_markers,
markers_found). This re-implements the seven section types of Section IV-F as fixed text
patterns, written ONCE from the rule list before comparing to the recorded counts (no tuning
against the recorded counts), runs them on the held document text (score.py's doc_text), and
reports agreement per document and per marker type. Writes a09_marker_counts.csv and
a09_marker_agreement.csv.
"""
import re
from common import band, doc_type, docs, write_csv, S

RULES = {
    "far_clauses": [r"\b52\.2\d{2}-\d{1,3}\b", r"clauses? incorporated by reference"],
    "instructions_to_offerors": [r"instructions to (offerors|quoters|vendors)", r"\b52\.212-1\b"],
    "evaluation_factors": [r"evaluation (factors|criteria)", r"basis (of|for) award", r"\b52\.212-2\b"],
    "pricing_schedule": [r"(price|pricing) schedule", r"schedule of (supplies|prices)",
                         r"supplies or services and prices", r"\bCLIN\b"],
    "sf1449_form": [r"\bSF\s?-?\s?1449\b", r"standard form 1449",
                    r"solicitation/contract/order for commercial"],
    "proposal_submission": [r"(proposal|quot(e|ation)|offer)s? submission", r"submission of (proposals|quot(es|ations)|offers)",
                            r"submission instructions"],
    "reps_and_certs": [r"representations and certifications", r"offeror representations", r"\b52\.212-3\b"],
}
dt = doc_type()
rows, agree = [], {k: [0, 0] for k in RULES}
for d in docs("27"):
    t = S.doc_text(d) or ""
    found = [k for k, pats in RULES.items() if any(re.search(p, t, re.I) for p in pats)]
    rec = [x for x in dt[d]["markers_found"].split(";") if x]
    for k in RULES:
        agree[k][0] += int((k in found) == (k in rec))
        agree[k][1] += 1
    rows.append({"document": d, "recorded": int(dt[d]["wrapper_markers"]), "recount": len(found),
                 "recorded_band": band(dt[d]["wrapper_markers"]), "recount_band": band(len(found)),
                 "only_recorded": ";".join(sorted(set(rec) - set(found))),
                 "only_recount": ";".join(sorted(set(found) - set(rec)))})
write_csv("a09_marker_counts.csv", rows)
summ = [{"item": k, "agree_docs": f"{a}/{n}"} for k, (a, n) in agree.items()]
summ.append({"item": "exact count agreement", "agree_docs": f"{sum(r['recorded']==r['recount'] for r in rows)}/{len(rows)}"})
summ.append({"item": "same band", "agree_docs": f"{sum(r['recorded_band']==r['recount_band'] for r in rows)}/{len(rows)}"})
write_csv("a09_marker_agreement.csv", summ)
for r in rows:
    print(r)
print(summ)

# ---- Supplement: four documents where doc-type.csv `pages` (112/101/70/121) is not the held
# file's page count (25/27/50/44). The held file is an excerpt of a full solicitation package in
# `all soliciation/`. Recount on the full package, to test whether the recorded counts came
# from the package rather than from the file the pipeline read. Page counts and marker
# patterns only; no labels are derived from these files.
import fitz  # noqa: E402
from pathlib import Path  # noqa: E402

PKG = Path(S.G).parents[1] / "all soliciation"
FULL = {"SOL-17": "SOL-17.pdf",
        "SOL-27": "SOL-27.pdf",
        "SOL-25": "SOL-25.pdf",
        "SOL-24": "SOL-24.pdf"}
sup = []
for d, rel in FULL.items():
    doc = fitz.open(PKG / rel)
    t = "\n".join(p.get_text() for p in doc)
    found = [k for k, pats in RULES.items() if any(re.search(p, t, re.I) for p in pats)]
    rec = [x for x in dt[d]["markers_found"].split(";") if x]
    sup.append({"document": d, "package_pages": len(doc), "held_pages": len(fitz.open(S.G / "pdfs" / f"{d}.pdf")),
                "recorded": len(rec), "recount_package": len(found),
                "recount_held": next(r["recount"] for r in rows if r["document"] == d),
                "only_recorded": ";".join(sorted(set(rec) - set(found))),
                "only_recount": ";".join(sorted(set(found) - set(rec)))})
write_csv("a09_marker_package_recount.csv", sup)
for s_ in sup:
    print(s_)

# ---- Band table on the held-file recount (the text the pipeline read), beside the recorded bands.
import numpy as np  # noqa: E402


def spearmanr(a, b):
    ra = np.argsort(np.argsort(a, kind="stable")).astype(float)
    # average ranks for ties
    def rank(x):
        x = np.asarray(x, float); o = np.argsort(x, kind="stable"); r = np.empty(len(x)); i = 0
        while i < len(x):
            j = i
            while j + 1 < len(x) and x[o[j + 1]] == x[o[i]]:
                j += 1
            r[o[i:j + 1]] = (i + j) / 2.0
            i = j + 1
        return r
    class R: pass
    out = R(); out.correlation = float(np.corrcoef(rank(a), rank(b))[0, 1]); return out
from common import level1, prf  # noqa: E402

recount = {r["document"]: r["recount"] for r in rows}
per = []
for d in docs("23"):
    m, g, pairs = level1(d)
    per.append((d, int(dt[d]["wrapper_markers"]), recount[d], len(g), len(m), len(pairs)))
bt = []
for basis, idx in (("recorded (package)", 1), ("recount (held file)", 2)):
    for b in ("0-2", "3-4", "5+"):
        sel = [x for x in per if band(x[idx]) == b]
        G = sum(x[3] for x in sel); E = sum(x[4] for x in sel); M = sum(x[5] for x in sel)
        p, r, _ = prf(M, E, G)
        bt.append({"basis": basis, "band": b, "docs": len(sel), "gold": G, "emitted": E, "matched": M,
                   "P": round(p, 3), "R": round(r, 3), "emit": round(E / G, 2) if G else ""})
    rho = spearmanr([x[idx] for x in per], [x[5] / x[4] if x[4] else 0 for x in per]).correlation
    bt.append({"basis": basis, "band": "Spearman markers vs P (23)", "docs": 23, "P": round(float(rho), 3)})
write_csv("a09_bands_by_count_basis.csv", bt)
for b_ in bt:
    print(b_)
