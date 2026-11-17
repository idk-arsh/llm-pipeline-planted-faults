#!/usr/bin/env python3
"""
score.py — score an extractor's task-tree output against a hand-labeled answer key.

Drop one file per document into `model-output/` (.xlsx or .csv, whatever the pipeline
emits) named after the document, then run:

    python score.py                 # score everything present
    python score.py SOL-07
    python score.py --csv results   # also write results_*.csv for the paper

WHAT IT MEASURES
----------------
1. TASK EXTRACTION — precision / recall / F1 against `answers/<Name>.csv`.
   Matching is token-set overlap, not string equality: the pipeline and the human write
   the same task differently ("O&M Support" vs "Operations and Maintenance (O&M) Support").
   Threshold is reported with every number so it can be varied in the paper.

2. TREE STRUCTURE — for tasks matched to gold, does the parent match too? A flat list
   where the document has hierarchy is a real failure mode and this is the only thing
   that catches it.

3. FABRICATION — every tool the model names is searched for in the document text. A tool
   that appears NOWHERE in the document is a fabrication, full stop. This needs no labels
   at all, which is why it is the most defensible number in the paper: it cannot be
   argued with by disputing the answer key.

4. DOC-LEVEL TOOL AGREEMENT — model's tool set vs the user's `doc_level_tools`.
   Reported as overlap, NOT as precision: the user's list is what they judged worth
   recording, not an exhaustive enumeration, so a model tool absent from it is only
   evidence of fabrication if measure 3 also says it is absent from the document.

5. CONSISTENCY — if `model-output/` holds several runs of the same document
   (`<Name>__run2.xlsx`, `__run3`, ...), reports how much the task list moves run to run.

Nothing here reads a document to produce a label. The only document access is a string
search for scoring, which is mechanical.
"""

import argparse
import csv
import io
import re
import sys
from collections import defaultdict
from pathlib import Path

# Inputs live in ../data (answers/, pdfs/, model-output/); none are released.
G = Path(__file__).resolve().parents[1] / "data"
ANSWERS, PDFS, OUT = G / "answers", G / "pdfs", G / "model-output"

MATCH_THRESHOLD = 0.50   # token-set similarity needed to call two task strings the same

# --- SHORT-LABEL GUARD, decided 2026-09-01 ------------------------------------
# Szymkiewicz-Simpson divides by the SHORTER token set, so a two-token gold label
# ("O&M Support" -> {"o","m"}) matches any verbose model string that happens to
# contain both tokens. 9 of 59 counted level-1 matches were false that way,
# including one document's 1.000. Gold labels of SHORT_LABEL_TOKENS tokens or fewer are
# therefore matched by Jaccard, which charges for the length gap.
# BOTH numbers are computed and reported on every run: guarded is the headline,
# unguarded is disclosed beside it. --no-guard makes the old number the headline.
SHORT_LABEL_TOKENS = 3
GUARD = True

# The pipeline's six columns, plus the aliases seen in real exports.
COLUMN_ALIASES = {
    "task": ["task", "tasks", "task name", "task_name", "task title"],
    "parent": ["parent task", "parent_task", "parent", "parent task name", "parent_task_id"],
    "methodology": ["methodology", "methodologies", "method"],
    "tools": ["tools & technologies", "tools and technologies", "tools_tech",
              "tools", "technologies", "tools & technology"],
    "summary": ["task summary", "task_summary", "summary"],
    "source": ["source file", "source_file", "source"],
}

STOP = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "support",
        "services", "service", "activities", "activity"}


def norm_tokens(s):
    """Lowercase alphanumeric tokens, stopwords dropped. 'O&M' -> {'o','m'} is fine:
    both sides get the same treatment, so it still matches its own paraphrase."""
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t and t not in STOP}


def overlap(a, b):
    """Szymkiewicz-Simpson overlap: |A n B| / min(|A|,|B|).

    Deliberately not Jaccard. Gold tasks are terse ("O&M Support") and model tasks are
    often verbose restatements; Jaccard punishes the length gap and would under-count
    genuine matches, making the pipeline look worse than it is.
    """
    ta, tb = norm_tokens(a), norm_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def jaccard(ta, tb):
    """|A n B| / |A u B| — punishes the length gap, which is the point here."""
    return len(ta & tb) / len(ta | tb) if (ta or tb) else 0.0


def sim(a, b, guard=None):
    """Task-string similarity, with the short-label guard applied by default.

    Long labels keep Szymkiewicz-Simpson: the model genuinely does restate a task
    at greater length, and Jaccard would under-count those real matches. Short
    labels do not get that benefit, because for them "contains both tokens" is not
    evidence of anything — it is the whole label.
    """
    ta, tb = norm_tokens(a), norm_tokens(b)
    if not ta or not tb:
        return 0.0
    if (GUARD if guard is None else guard) and min(len(ta), len(tb)) <= SHORT_LABEL_TOKENS:
        return jaccard(ta, tb)
    return len(ta & tb) / min(len(ta), len(tb))


def read_table(path):
    """Read .csv or .xlsx into a list of dicts, keys lowercased and stripped."""
    if path.suffix.lower() in (".csv", ".txt"):
        rows = list(csv.DictReader(io.open(path, encoding="utf-8-sig")))
        return [{(k or "").strip().lower(): (v or "") for k, v in r.items()} for r in rows]

    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    header = None
    for row in it:
        if row and any(c is not None and str(c).strip() for c in row):
            header = [str(c or "").strip().lower() for c in row]
            break
    if not header:
        return []
    out = []
    for row in it:
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue
        out.append({header[i]: ("" if row[i] is None else str(row[i]))
                    for i in range(min(len(header), len(row)))})
    return out


def pick(row, key):
    for alias in COLUMN_ALIASES[key]:
        if alias in row:
            return row[alias]
    return ""


def split_multi(cell):
    """Tool/methodology cells arrive newline-, semicolon- or comma-separated."""
    parts = re.split(r"[\n;]+|,(?![^()]*\))", cell or "")
    return [p.strip(" .-•") for p in parts if p and p.strip(" .-•")]


def doc_text(name):
    """Full text of the document, for the fabrication search only."""
    cands = list(PDFS.glob(f"{name}.*"))
    if not cands:
        return None
    p = cands[0]
    try:
        if p.suffix.lower() == ".pdf":
            import fitz
            return "\n".join(pg.get_text() for pg in fitz.open(p))
        import docx
        d = docx.Document(str(p))
        bits = [q.text for q in d.paragraphs]
        for t in d.tables:
            for r in t.rows:
                bits.append(" ".join(c.text for c in r.cells))
        return "\n".join(bits)
    except Exception as e:
        print(f"    ! could not read {p.name}: {e}", file=sys.stderr)
        return None


def clean_term(term):
    """Strip the model's own gloss from a tool entry, leaving the thing being named.

    The pipeline writes "Nagios (monitoring)", "SharePoint lists", "NIST SP 800-53
    control mappings", "Knowledge Management (KM) repositories". In every case the
    named thing IS in the document and the trailing noun is the model describing what
    it is used for. Testing the whole string scores that gloss as a fabrication.

    The tail list is deverbal and abstract nouns only — a principled class, not an
    open-ended patch list. Note this deliberately UNDER-counts fabrication: it can
    forgive a gloss, it cannot invent grounding. "IBM SmartCloud" keeps both tokens
    and stays a fabrication, which is the case this measure exists to catch.
    """
    TAIL = (r"modules?|lists?|librar(?:y|ies)|workflows?|pages?|forms?|sites?|"
            r"site collections?|repositor(?:y|ies)|tracking|monitoring|reporting|"
            r"mechanisms?|mappings?|alignment|automation|compliance|integration|"
            r"management|administration|support|services?|standards?|formats?|"
            r"controls?|processes?|procedures?|capabilit(?:y|ies)|configuration")
    t = re.sub(r"\s*\([^)]*\)", " ", term)                 # drop "(...)"
    while True:
        nxt = re.sub(r"(?i)\s+(?:" + TAIL + r")\s*$", "", t)
        if nxt == t:
            break
        t = nxt
    return t.strip(" ,;-") or term.strip()


def is_tool_like(term):
    """Does this entry even claim to name a tool?

    Free-text obligations show up in the Tools column ("Change request tracking",
    "industry standard file formats", and one 300-character description of who the
    customers are). Those are a real defect, but they are a TYPE defect, not a
    fabrication — nobody claimed a product exists. Counted separately.
    """
    words = clean_term(term).split()
    if len(words) > 5:
        return False
    if len(words) >= 2 and not any(w[:1].isupper() or any(c.isdigit() for c in w)
                                   for w in words):
        return False                     # all-lowercase multiword phrase
    return True


def in_document(term, text):
    """Is this term named in the document? Returns True / False / None (untestable).

    Conservative BY DESIGN: it must be hard to call something a fabrication. A false
    fabrication is the one error this paper cannot survive, so anything short of clear
    evidence of absence resolves in the model's favour, and terms with nothing
    distinctive to test return None and are excluded from the denominator.

    Three passes, first hit wins:
      1. the whole term, contiguous, punctuation-insensitive
      2. the term minus generic qualifiers, contiguous
         ("OMB M-15-13" -> "m 15 13", which the document writes as "M-15-13")
      3. every distinctive token present somewhere in the document
         ("Agency.gov SOP and RTM" -> gov + sop + rtm all present -> grounded)

    Pass 3 requires ALL tokens, not any: "any" let a fabricated product name through on
    its vendor word alone ("IBM SmartCloud" grounded by a stray "IBM").
    """
    norm = lambda x: re.sub(r"[^a-z0-9]+", " ", x.lower()).strip()
    t = norm(clean_term(term))
    if len(t) < 3:
        return None                      # too short to test honestly
    hay = re.sub(r"[^a-z0-9]+", " ", text.lower())
    if re.search(r"\b" + re.escape(t) + r"\b", hay):
        return True

    # generic qualifiers: they carry no identity, and documents drop them freely
    QUAL = {"omb", "memorandum", "memorandums", "memo", "circular", "section",
            "act", "standard", "standards", "the", "and", "of", "for", "current",
            "version", "microsoft", "server", "framework", "platform", "tools",
            "tool", "suite", "software", "system", "systems", "services", "service"}
    core = [w for w in t.split() if w not in QUAL]
    if core and len(core) < len(t.split()):
        c = " ".join(core)
        if re.search(r"\b" + re.escape(c) + r"\b", hay):
            return True

    # distinctive tokens: keep digit-bearing ones at any length (508, 1194)
    toks = [w for w in core if len(w) > 3 or any(ch.isdigit() for ch in w)]
    if not toks:
        return None                      # nothing distinctive left — do not guess
    return all(re.search(r"\b" + re.escape(w) + r"\b", hay) for w in toks)


def load_gold(name):
    rows = list(csv.DictReader(io.open(ANSWERS / f"{name}.csv", encoding="utf-8")))
    return {
        "tasks": [r["task"] for r in rows if r.get("task")],
        "parent": {r["task"]: r.get("parent_task_id", "") for r in rows},
        "ids": {r.get("task_id", ""): r.get("task", "") for r in rows},
        "tools": split_multi(rows[0].get("doc_level_tools", "")) if rows else [],
        "meth": split_multi(rows[0].get("doc_level_methodology", "")) if rows else [],
    }


def match_sets(preds, golds, guard=None):
    """Greedy best-match between two task lists. One gold consumed at most once."""
    pairs, used = [], set()
    for pi, pt in enumerate(preds):
        best, bs = None, 0.0
        for gi, gt in enumerate(golds):
            if gi in used:
                continue
            sc = sim(pt, gt, guard)
            if sc > bs:
                best, bs = gi, sc
        if best is not None and bs >= MATCH_THRESHOLD:
            used.add(best)
            pairs.append((pi, best, bs))
    return pairs


def prf(tp, npred, ngold):
    p = tp / npred if npred else 0.0
    r = tp / ngold if ngold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


ROOTISH = ("", "ROOT", "NONE", "N/A", "NA", "-", "TOP", "TOP LEVEL")


def score_one(name, pred_path, gold, text):
    pred = read_table(pred_path)
    ptasks = [pick(r, "task") for r in pred if pick(r, "task").strip()]

    # --- 1a. LEVEL 1 — the comparison that is actually apples-to-apples.
    # The answer key records the document's top-level task headings. The pipeline
    # emits those headings in its `Parent Task` column and puts decomposed subtasks
    # in `Task`. Comparing every emitted row against a top-level-only key scores the
    # subtasks as false positives, which measures grain, not extraction. So level 1 is
    # scored on its own: the model's distinct parent labels (plus any row that declares
    # itself top-level) against the key's ROOT tasks.
    parents = [pick(r, "parent").strip() for r in pred]
    named_parents = [x for x in parents if x.upper() not in ROOTISH]
    self_roots = [pick(r, "task").strip() for r in pred
                  if pick(r, "task").strip() and pick(r, "parent").strip().upper() in ROOTISH]
    model_l1 = list(dict.fromkeys(named_parents + self_roots))

    gold_l1 = [t for t in gold["tasks"]
               if gold["parent"].get(t, "").strip().upper() in ROOTISH]
    if not gold_l1:                       # key has no ROOT marker — treat it all as level 1
        gold_l1 = list(gold["tasks"])

    pairs_l1 = match_sets(model_l1, gold_l1)                       # guarded — headline
    pairs_l1_u = match_sets(model_l1, gold_l1, guard=False)        # pre-2026-09-01
    p1, r1, f1_l1 = prf(len(pairs_l1), len(model_l1), len(gold_l1))
    p1u, r1u, f1u = prf(len(pairs_l1_u), len(model_l1), len(gold_l1))

    # --- 1c. FABRICATED CONTAINERS — parent labels the model invented.
    # Decided 2026-09-01. `StatementWork` on SOL-27 captured
    # all four gold roots verbatim, scored 0.000/0.000, and was counted nowhere: it is
    # neither a fabricated tool nor a missing task. A parent label that matches no gold
    # row AND appears nowhere in the document is a level the model manufactured.
    # Conservative in the model's favour, exactly like in_document(): the gold test uses
    # the UNGUARDED overlap and the document test is a full-text search rather than a
    # headings search, so both are easy to pass. `None` (untestable) never counts.
    containers = []
    if text:
        for lab in dict.fromkeys(x for x in named_parents if x):
            if any(overlap(lab, g) >= MATCH_THRESHOLD for g in gold["tasks"]):
                continue
            if in_document(lab, text) is False:
                containers.append((lab, sum(1 for x in parents if x.strip() == lab)))

    # --- 1b. LEAF GRAIN — every emitted row against the key. Recall is meaningful here
    # (did the model's output contain the recorded task at all); precision is NOT, while
    # the key stops at level 1. Reported for the record, not as the headline.
    pairs = match_sets(ptasks, gold["tasks"])
    tp = len(pairs)
    tp_u = len(match_sets(ptasks, gold["tasks"], guard=False))
    prec, rec, f1 = prf(tp, len(ptasks), len(gold["tasks"]))

    kids = len(ptasks) - len(self_roots)
    depth_ratio = round(kids / len(model_l1), 2) if model_l1 else ""

    # --- 2. tree structure on matched tasks
    # NOTE: if every gold row is ROOT, this measure cannot say anything — a matched
    # subtask correctly names a parent the key does not record. Flagged, not scored.
    gold_is_flat = all(gold["parent"].get(t, "").strip().upper() in ROOTISH
                       for t in gold["tasks"])
    parent_ok = parent_ok_u = parent_checked = 0
    for pi, gi, _ in ([] if gold_is_flat else pairs):
        gp_id = gold["parent"].get(gold["tasks"][gi], "")
        gp = gold["ids"].get(gp_id, "ROOT" if gp_id == "ROOT" else "")
        pp = pick(pred[pi], "parent").strip()
        if not gp and not gp_id:
            continue
        parent_checked += 1
        if gp_id == "ROOT":
            if not pp or pp.upper() in ("ROOT", "NONE", "-"):
                parent_ok += 1
                parent_ok_u += 1
        elif gp:
            if sim(pp, gp) >= MATCH_THRESHOLD:
                parent_ok += 1
            if overlap(pp, gp) >= MATCH_THRESHOLD:
                parent_ok_u += 1

    # --- 3. fabrication: model tools absent from the document
    model_tools = []
    for r in pred:
        model_tools += split_multi(pick(r, "tools"))
    model_tools = [t for t in dict.fromkeys(model_tools)
                   if t.upper() not in ("NOT_SPECIFIED", "N/A", "NA", "NONE", "")]
    fabricated, testable, prose = [], 0, []
    if text:
        for t in model_tools:
            if not is_tool_like(t):
                prose.append(t)
                continue
            hit = in_document(t, text)
            if hit is None:
                continue
            testable += 1
            if not hit:
                fabricated.append(t)

    # --- 3b. METHODOLOGY — abstention and grounding.
    # The document is usually silent on methodology, so the correct output is often
    # NOT_SPECIFIED. This measures whether the model is ever willing to say so, and
    # whether the methodology it does emit is traceable to the document. Mechanical,
    # needs no answer key — same standing as fabrication.
    ABSTAIN = ("NOT_SPECIFIED", "NOT SPECIFIED", "N/A", "NA", "NONE", "UNSPECIFIED", "-", "")
    meths = [pick(r, "methodology").strip() for r in pred if pick(r, "task").strip()]
    abstained = sum(1 for m in meths if m.upper() in ABSTAIN)
    stated = [m for m in meths if m.upper() not in ABSTAIN]
    meth_ungrounded = 0
    if text and stated:
        for m in stated:
            # a methodology string is grounded if every distinctive token of it
            # appears in the document; "Agile (ADLC) / Secure SDLC" fails on ADLC
            parts = [x for x in re.split(r"[/,;]| with | in accordance ", m) if x.strip()]
            if not all(in_document(x, text) for x in parts if len(x.strip()) > 3):
                meth_ungrounded += 1

    # --- 4. overlap with the user's document-level tool list
    gset = {tuple(sorted(norm_tokens(t))) for t in gold["tools"] if norm_tokens(t)}
    mset = {tuple(sorted(norm_tokens(t))) for t in model_tools if norm_tokens(t)}
    agree = len(gset & mset)

    return {
        "document": name,
        "gold_l1": len(gold_l1),
        "model_l1": len(model_l1),
        "matched_l1": len(pairs_l1),
        "precision_l1": round(p1, 3),
        "recall_l1": round(r1, 3),
        "f1_l1": round(f1_l1, 3),
        "matched_l1_unguarded": len(pairs_l1_u),
        "precision_l1_unguarded": round(p1u, 3),
        "recall_l1_unguarded": round(r1u, 3),
        "f1_l1_unguarded": round(f1u, 3),
        "containers": len(containers),
        "subtasks_per_l1": depth_ratio,
        "gold_tasks": len(gold["tasks"]),
        "model_tasks": len(ptasks),
        "matched": tp,
        "matched_unguarded": tp_u,
        "precision": round(prec, 3),
        "recall": round(rec, 3),
        "f1": round(f1, 3),
        "gold_flat": gold_is_flat,
        "parent_checked": parent_checked,
        "parent_correct": parent_ok,
        "parent_correct_unguarded": parent_ok_u,
        "model_tools": len(model_tools),
        "tools_testable": testable,
        "fabricated": len(fabricated),
        "prose_in_tools": len(prose),
        "meth_rows": len(meths),
        "meth_abstained": abstained,
        "meth_ungrounded": meth_ungrounded,
        "fabrication_rate": round(len(fabricated) / testable, 3) if testable else "",
        "user_tools": len(gset),
        "tools_agreeing": agree,
        "_fab_list": fabricated,
        "_container_list": containers,
    }


KEY_GRAIN = G / "key-grain.csv"


def load_key_grain():
    """Per-document answer-key grain flags from the 2026-08-24 audit.

    Three keys are not task lists at level-1 grain and must not reach corpus
    precision/recall: two hold past-performance capability names, one holds CPARS
    rating factors. They still contribute abstention and fabrication counts, which
    are row-level and grain-independent. No file means score everything, and say so.
    """
    if not KEY_GRAIN.exists():
        return {}, {}
    grain, scorable = {}, {}
    for r in csv.DictReader(io.open(KEY_GRAIN, encoding="utf-8-sig", newline="")):
        d = r["doc_id"].strip()
        grain[d] = r["key_grain"].strip()
        scorable[d] = r["scorable_level1"].strip().lower()
    return grain, scorable


def resolve_name(stem):
    """Map an output filename back to a document name.

    Strips a `__run2`-style suffix, then any decoration the pipeline appends
    (`_tasks`, `-output`, ` (1)` ...) — but only when that lands on a real
    answer key. Whatever the pipeline emits is fine; nothing gets renamed by hand.
    """
    base = re.sub(r"__run\d+$", "", stem)
    if (ANSWERS / f"{base}.csv").exists():
        return base
    trimmed = base
    while True:
        nxt = re.sub(r"(?i)([_\-. ]+(tasks?|output|extract(ion)?|result s?|final)|\s*\(\d+\))$", "", trimmed)
        if nxt == trimmed:
            break
        trimmed = nxt
        if (ANSWERS / f"{trimmed}.csv").exists():
            return trimmed
    return base


def main():
    global MATCH_THRESHOLD, GUARD
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--csv", metavar="PREFIX",
                    help="write PREFIX_per-document.csv, _fabrications.csv, _containers.csv")
    ap.add_argument("--threshold", type=float, default=MATCH_THRESHOLD)
    ap.add_argument("--no-guard", action="store_true",
                    help="headline numbers revert to unguarded overlap (pre-2026-09-01)")
    a = ap.parse_args()
    MATCH_THRESHOLD = a.threshold
    if a.no_guard:
        GUARD = False

    if not OUT.exists():
        sys.exit(f"no model output yet — create {OUT} and drop one file per document in it")

    runs = defaultdict(list)
    for p in sorted(OUT.iterdir()):
        if p.suffix.lower() not in (".csv", ".xlsx", ".txt") or p.name.startswith("~$"):
            continue
        base = resolve_name(p.stem)
        runs[base].append(p)
    if a.names:
        runs = {k: v for k, v in runs.items() if k in set(a.names)}
    if not runs:
        sys.exit(f"nothing to score in {OUT}")

    grain_of, scorable_of = load_key_grain()
    if not grain_of:
        print("WARNING: key-grain.csv not found. Every key is being scored as if it")
        print("         were document-heading grain. Three of them are not.")
        print("         See KEY-GRAIN-AUDIT_2026-08-24.md")
        print("")

    results, all_fabs, all_cont, missing = [], [], [], []
    for name, paths in sorted(runs.items()):
        if not (ANSWERS / f"{name}.csv").exists():
            missing.append(name)
            continue
        gold = load_gold(name)
        text = doc_text(name)
        for p in sorted(paths):
            r = score_one(name, p, gold, text)
            r["run"] = p.stem
            r["key_grain"]  = grain_of.get(name, "UNAUDITED")
            r["l1_counted"] = scorable_of.get(name, "unaudited")
            if text is None:
                r["fabrication_rate"] = "no document"
            results.append(r)
            all_fabs += [(name, p.stem, t) for t in r.pop("_fab_list")]
            all_cont += [(name, p.stem, lab, n) for lab, n in r.pop("_container_list")]

    if missing:
        print(f"skipped (no answer key): {', '.join(missing)}\n")

    hdr = ["document", "key_grain", "gold_l1", "model_l1", "matched_l1", "precision_l1",
           "recall_l1", "precision_l1_unguarded", "recall_l1_unguarded",
           "subtasks_per_l1", "containers", "fabricated"]
    lbl = ["document", "keygrain", "gold", "model", "match", "prec", "recall",
           "prec-u", "rec-u", "sub/L1", "cont", "fabr"]
    w = [30, 16, 5, 6, 6, 6, 6, 7, 6, 7, 5, 5]
    print("LEVEL 1 - top-level tasks, the grain the answer key records\n")
    print("  prec / recall are GUARDED (short gold labels matched by Jaccard);")
    print("  prec-u / rec-u are the same documents scored the old, unguarded way.")
    print("  cont = parent labels in no gold row and nowhere in the document text.")
    print("")
    print("".join(h[:c].ljust(c + 1) for h, c in zip(lbl, w)))
    print("-" * (sum(w) + len(w)))
    for r in results:
        print("".join(str(r.get(h, ""))[:c].ljust(c + 1) for h, c in zip(hdr, w)))

    # ---- corpus totals. Micro-averaged: one big pool, so a 2-task document does not
    # carry the same weight as a 17-task one.
    l1set    = [r for r in results if r.get("l1_counted") != "no"]
    excluded = [r for r in results if r.get("l1_counted") == "no"]
    g1 = sum(r["gold_l1"] for r in l1set)
    m1 = sum(r["model_l1"] for r in l1set)
    t1 = sum(r["matched_l1"] for r in l1set)
    t1u = sum(r["matched_l1_unguarded"] for r in l1set)
    gt = sum(r["gold_tasks"] for r in results)
    mt = sum(r["model_tasks"] for r in results)
    tp = sum(r["matched"] for r in results)
    pc = sum(r["parent_checked"] for r in results)
    po = sum(r["parent_correct"] for r in results)
    ft = sum(r["tools_testable"] for r in results)
    fb = sum(r["fabricated"] for r in results)
    P1, R1, F11 = prf(t1, m1, g1)
    P1u, R1u, F11u = prf(t1u, m1, g1)
    P, R, _ = prf(tp, mt, gt)

    print(f"\nCORPUS  ({len(results)} scored, threshold {MATCH_THRESHOLD})")
    print(f"\n  LEVEL 1 - the model's top-level tasks vs the answer key")
    print(f"    scored on {len(l1set)} of {len(results)} documents")
    for r in excluded:
        print(f"    EXCLUDED  {r['document']} - key is {r['key_grain']}, not scorable at level 1")
    # Mechanical key-grain detector. Needs no PDF and no human read. Two signatures
    # separate "the key is the wrong grain" from "the model did badly":
    #   (a) it emitted top-level tasks and matched NONE of the key   -> SOL-03
    #   (b) it emitted at least as many as the key and still matched -> SOL-42
    #       almost none of them
    # A model that under-emits (model < gold) and still matches some is failing at
    # extraction, not being mis-scored - SOL-20, which must NOT be flagged.
    def suspect_key(r):
        if r["matched_l1"] == 0 and r["model_l1"] >= 2:
            return True
        return (r["gold_l1"] >= 4 and r["model_l1"] >= r["gold_l1"]
                and r["recall_l1"] <= 0.35)

    for r in results:
        if not suspect_key(r):
            continue
        tail = "  (already excluded)" if r.get("l1_counted") == "no" else "  <-- NOT YET EXCLUDED"
        d, g, m, mm = r["document"], r["gold_l1"], r["model_l1"], r["matched_l1"]
        print(f"    SUSPECT KEY  {d} - matched {mm} of {g} gold while emitting {m}.{tail}")
    print(f"    tasks         gold {g1}  model {m1}  matched {t1}  (unguarded {t1u})")
    print(f"    precision     {P1:.3f}      (of the top-level tasks it named, how many are real)")
    print(f"    recall        {R1:.3f}      (of the recorded tasks, how many it found)")
    print(f"    F1            {F11:.3f}")
    if GUARD:
        print(f"    guard         ON - gold labels of <= {SHORT_LABEL_TOKENS} tokens are matched by")
        print(f"                  Jaccard, not by overlap. Unguarded, the same corpus reads")
        print(f"                  precision {P1u:.3f} / recall {R1u:.3f} / F1 {F11u:.3f}.")
        print(f"                  Report both columns - SCORING-DECISIONS_2026-09-01.md")
    else:
        print(f"    guard         OFF (--no-guard). Guarded, the same corpus reads")
        print(f"                  precision {P1u:.3f} / recall {R1u:.3f} / F1 {F11u:.3f}.")

    if m1:
        print(f"\n  DECOMPOSITION - the level the answer key does not record")
        print(f"    {mt} subtasks under {m1} top-level tasks = {mt/m1:.1f} per task")
        print(f"    Nothing to score them against. Leaf-grain precision {P:.3f} / recall {R:.3f}")
        print(f"    is kept for the record only: it counts every subtask as a false")
        print(f"    positive, so it measures grain mismatch, not extraction quality.")

    if all_cont:
        docs = sorted({c[0] for c in all_cont})
        print("")
        print(f"  FABRICATED CONTAINERS  {len(all_cont)} parent labels across {len(docs)} of "
              f"{len(results)} documents")
        print(f"                  appear in no gold row and nowhere in the document text.")
        print(f"                  A level the model manufactured: not a wrong task and not a")
        print(f"                  fabricated tool, so counted in neither measure until now.")
        for d, run, lab, n in all_cont:
            plural = "s" if n != 1 else ""
            print(f"    {d:<34} {lab!r} over {n} row{plural}")
    elif results:
        print("")
        print(f"  FABRICATED CONTAINERS  none - every parent label is in a gold row or the document")

    if all(r.get("gold_flat") for r in results):
        print(f"\n  TREE STRUCTURE  not scorable - every answer-key row is ROOT.")
    elif pc:
        print(f"\n  TREE STRUCTURE  parent correct {po}/{pc} = {po/pc:.3f}")

    mr = sum(r.get("meth_rows", 0) for r in results)
    ma = sum(r.get("meth_abstained", 0) for r in results)
    mu = sum(r.get("meth_ungrounded", 0) for r in results)
    if mr:
        print(f"\n  METHODOLOGY     abstained {ma}/{mr} = {ma/mr:.3f}  rows where it said NOT_SPECIFIED")
        print(f"                  ungrounded {mu}/{mr - ma} = {mu/(mr-ma) if mr>ma else 0:.3f}  of the rows where it named one")
    # v0.8 FIX (S20): model_tools already includes prose entries; the old
    # denominator (pr + model_tools) counted each prose entry twice.
    pr = sum(r.get("prose_in_tools", 0) for r in results)
    if pr:
        print(f"\n  TOOLS COLUMN    {pr} of {sum(r['model_tools'] for r in results)} entries are prose, not a tool name")
        print(f"                  (free-text obligations in the Tools & Technologies column)")
    if ft:
        print(f"\n  FABRICATION     {fb}/{ft} = {fb/ft:.3f}  tools named that appear nowhere")
        print(f"                  in the document (model vs document, needs no answer key)")

    if len(results) > len(runs):
        print("\nCONSISTENCY (same document, multiple runs)")
        byname = defaultdict(list)
        for r in results:
            byname[r["document"]].append(r)
        for n, rs in sorted(byname.items()):
            if len(rs) > 1:
                c = [r["model_tasks"] for r in rs]
                print(f"  {n:<34} task counts {c}  spread {max(c)-min(c)}")

    if a.csv:
        p1 = Path(__file__).resolve().parent / f"{a.csv}_per-document.csv"
        cw = csv.DictWriter(io.open(p1, "w", encoding="utf-8", newline=""),
                            fieldnames=list(results[0].keys()))
        cw.writeheader()
        cw.writerows(results)
        p2 = Path(__file__).resolve().parent / f"{a.csv}_fabrications.csv"
        cw2 = csv.writer(io.open(p2, "w", encoding="utf-8", newline=""))
        cw2.writerow(["document", "run", "tool_named_but_absent_from_document"])
        cw2.writerows(all_fabs)
        p3 = Path(__file__).resolve().parent / f"{a.csv}_containers.csv"
        cw3 = csv.writer(io.open(p3, "w", encoding="utf-8", newline=""))
        cw3.writerow(["document", "run", "invented_parent_label", "rows_filed_under_it"])
        cw3.writerows(all_cont)
        print("")
        print(f"wrote {p1.name}, {p2.name} ({len(all_fabs)} fabrications) and "
              f"{p3.name} ({len(all_cont)} invented containers)")


if __name__ == "__main__":
    main()
