"""v0.8 analysis 14: grounding against the source vs against the model's input (R2 M5).

Rebuilds the text the model received with the ablation runner's copy of the pinned reader
(ablate.py read_file / clean_text / chunk_pdf / chunk_docx, which mirror app.py): pdfplumber
text + tables with non-ASCII stripped on the single-pass PDF path, text-only 20-page chunks
for PDFs over 40 pages, DOCX paragraphs only; then clean_text (en dash -> hyphen, delete
"Page " and " of "). Runs the three grounding checks of score.py (container, tool,
methodology) against (a) the source text score.py uses and (b) this model-input text, on all
27 frozen outputs, and lists every item whose status differs. Also counts documents with a
heading-like source line containing " of ".
Writes a14_status_changes.csv, a14_summary.csv, a14_of_headings.csv.
"""
import re
import sys
from common import GS, docs, output_path, write_csv, S

sys.path.insert(0, str(GS / "ablation"))
import ablate as A  # noqa: E402  (no API call is made; the client is built lazily)

ABSTAIN = ("NOT_SPECIFIED", "NOT SPECIFIED", "N/A", "NA", "NONE", "UNSPECIFIED", "-", "")


def model_input(d):
    p = next((GS / "pdfs").glob(f"{d}.*"))
    ext = p.suffix.lower()
    full = A.clean_text(A.read_file(p, ext))
    if ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(p) as pdf:
            n = len(pdf.pages)
        chunks = A.chunk_pdf(p) if n > 40 else [full]
    else:
        from docx import Document
        w = sum(len(x.text.split()) for x in Document(str(p)).paragraphs)
        chunks = A.chunk_docx(p) if w > 20000 else [full]
    return "\n".join(c for c in chunks if c and c.strip())


def meth_ungrounded(m, t):
    parts = [x for x in re.split(r"[/,;]| with | in accordance ", m) if x.strip()]
    return not all(S.in_document(x, t) for x in parts if len(x.strip()) > 3)


changes, summ, ofh = [], [], []
tot = {k: [0, 0, 0] for k in ("container", "tool", "methodology")}
for d in docs("27"):
    src = S.doc_text(d) or ""
    inp = model_input(d)
    pred = S.read_table(output_path(d))
    gold = S.load_gold(d)
    parents = [S.pick(r, "parent").strip() for r in pred]
    named = [x for x in parents if x.upper() not in S.ROOTISH]
    items = []
    for lab in dict.fromkeys(x for x in named if x):
        if any(S.overlap(lab, g) >= S.MATCH_THRESHOLD for g in gold["tasks"]):
            continue
        items.append(("container", lab, S.in_document(lab, src) is False, S.in_document(lab, inp) is False))
    tools = []
    for r in pred:
        tools += S.split_multi(S.pick(r, "tools"))
    for t in dict.fromkeys(tools):
        if t.upper() in ("NOT_SPECIFIED", "N/A", "NA", "NONE", "") or not S.is_tool_like(t):
            continue
        a, b = S.in_document(t, src), S.in_document(t, inp)
        items.append(("tool", t, a is False, b is False))
    for m in [S.pick(r, "methodology").strip() for r in pred if S.pick(r, "task").strip()]:
        if m.upper() in ABSTAIN:
            continue
        items.append(("methodology", m, meth_ungrounded(m, src), meth_ungrounded(m, inp)))
    for kind, x, fs, fi in items:
        tot[kind][0] += fs; tot[kind][1] += fi; tot[kind][2] += (fs != fi)
        if fs != fi:
            changes.append({"document": d, "check": kind, "item": x[:120],
                            "flagged_vs_source": fs, "flagged_vs_model_input": fi})
    heads = [ln.strip() for ln in src.split("\n")
             if " of " in ln and 2 <= len(ln.split()) <= 10
             and (ln.strip().isupper() or ln.strip().istitle() or re.match(r"^\s*(\d+(\.\d+)*|[A-Z]\.\d+|Section|Task)\b", ln.strip()))]
    ofh.append({"document": d, "heading_like_lines_with_of": len(heads), "example": heads[0][:80] if heads else ""})
write_csv("a14_status_changes.csv", changes)
for k, (a, b, c) in tot.items():
    summ.append({"check": k, "flagged_vs_source": a, "flagged_vs_model_input": b, "items_changing_status": c})
summ.append({"check": "docs with a heading-like ' of ' line (of 27)",
             "flagged_vs_source": sum(1 for o in ofh if o["heading_like_lines_with_of"])})
write_csv("a14_summary.csv", summ)
write_csv("a14_of_headings.csv", ofh)
for s_ in summ:
    print(s_)
for c in changes:
    print(c)
