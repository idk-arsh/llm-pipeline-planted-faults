"""Shared loaders for the scorer-side tools. Reads ../data, which is not released.
Shared loaders for the v0.8 analyses. Read-only on golden-set/.

Everything scores the frozen outputs in golden-set/model-output/ with the matcher from
score.py (a copy of golden-set/score.py; see make_score.py). The 23-document
level-1 set is the one score.py itself uses: key-grain.csv scorable_level1 != "no".
"""
import csv
import io
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score as S  # noqa: E402

GS = S.G
SEED = 20260924
N_BOOT = 10_000
N_PERM = 10_000


def write_csv(name, rows, fields=None):
    rows = list(rows)
    if fields is None:
        fields = list(rows[0].keys()) if rows else []
    with io.open(HERE / name, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("wrote", name, f"({len(rows)} rows)")


def doc_type():
    return {r["doc_id"]: r for r in csv.DictReader(io.open(GS / "doc-type.csv", encoding="utf-8-sig"))}


def freeze_rows():
    return {r["document"]: r for r in
            csv.DictReader(io.open(HERE.parent / "results" / "per-document_scores.csv", encoding="utf-8-sig"))}


def output_path(name):
    for ext in (".xlsx", ".csv"):
        p = GS / "model-output" / f"{name}_tasks{ext}"
        if p.exists():
            return p
    raise FileNotFoundError(name)


def pdf_pages(name):
    """Page count as the extractor sees it (pdfplumber and fitz agree on page count)."""
    p = GS / "pdfs" / f"{name}.pdf"
    if not p.exists():
        return None
    import fitz
    return len(fitz.open(p))


def chunked(name):
    """True if the pinned extractor takes the chunked path for this document.

    app.py: PDF with > 40 pages -> chunk_pdf; DOCX with > 20,000 paragraph words ->
    chunk_docx. Every DOCX in the corpus is under 20,000 words.
    """
    n = pdf_pages(name)
    if n is not None:
        return n > 40
    import docx
    d = docx.Document(str(GS / "pdfs" / f"{name}.docx"))
    return sum(len(p.text.split()) for p in d.paragraphs) > 20000


def level1(name, threshold=0.5, guard=True):
    """Return (model_l1 labels, gold_l1 labels, matched pairs) exactly as score_one does."""
    gold = S.load_gold(name)
    pred = S.read_table(output_path(name))
    parents = [S.pick(r, "parent").strip() for r in pred]
    named = [x for x in parents if x.upper() not in S.ROOTISH]
    selfr = [S.pick(r, "task").strip() for r in pred
             if S.pick(r, "task").strip() and S.pick(r, "parent").strip().upper() in S.ROOTISH]
    model_l1 = list(dict.fromkeys(named + selfr))
    gold_l1 = [t for t in gold["tasks"] if gold["parent"].get(t, "").strip().upper() in S.ROOTISH]
    if not gold_l1:
        gold_l1 = list(gold["tasks"])
    old_t, old_g = S.MATCH_THRESHOLD, S.GUARD
    S.MATCH_THRESHOLD = threshold
    try:
        pairs = S.match_sets(model_l1, gold_l1, guard=guard)
    finally:
        S.MATCH_THRESHOLD, S.GUARD = old_t, old_g
    return model_l1, gold_l1, pairs


def band(markers):
    m = int(markers)
    return "0-2" if m <= 2 else ("3-4" if m <= 4 else "5+")


def docs(scope="23"):
    """Document list: '23' = level-1 set, '27' = every scored document."""
    fr = freeze_rows()
    if scope == "27":
        return sorted(fr)
    return sorted(d for d, r in fr.items() if r["l1_counted"] != "no")


def prf(tp, npred, ngold):
    p = tp / npred if npred else 0.0
    r = tp / ngold if ngold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)
