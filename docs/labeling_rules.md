# Answer-key labeling rules (rubric v1.0, frozen 2026-08-01)

Sections 1-7 of the rubric every answer key was labeled under. Sections on the corpus,
anonymization, logistics and working notes are internal and omitted. Document names are
replaced by SOL-NN tokens; no rule was changed.

## 1. The labeling unit

### 1.1 ⚠️ ONE ROW = ONE TASK

**Read this before anything else.** Each row in the golden CSV represents exactly one discrete task. Not one document, not one section, not one work area with its children folded in. A document producing 26 tasks produces 26 rows.

*(This rule is stated first because v0.2 only implied it, and the first pilot document was initially labeled as a single merged row holding the entire document — friction item F1.)*

### 1.2 What counts as a task

A **task** is a single, discrete piece of work the document requires to be performed.

**INCLUDE when it is:**
- **A unit of work** with an action verb (design, develop, migrate, operate, maintain, test, deliver, provide, support, compile, author).
- **Discrete** — it could stand as its own line in a work breakdown; it would be planned or staffed separately.
- **Work the contractor performs**, not administrative mechanics constraining a reader's response.

**EXCLUDE:**
- Background, definitions, boilerplate, evaluation criteria.
- The issuer's own obligations ("the Government will…").
- Third-party engagement examples (R9).
- Submission mechanics that constrain how a reader responds (R10).

### 1.3 Granularity & hierarchy

- A broad work area → **parent task**; the concrete items under it → **child tasks**.
- Mirror the document's own structure where it has one (3.1 / 3.1.1). Do not invent sub-levels the document doesn't support.
- Split when children have genuinely separate work; merge trivial restatements. See R1.

---

## 2. Label schema (9 fields, one row per task)

| Field | Required? | Definition | Labeling note |
|---|---|---|---|
| `task_id` | yes | Stable ID within the doc, e.g. `D07-T03` | Sequential in reading order |
| `task` | yes | Normalized one-line statement of the work | Clean imperative; no invented detail |
| `parent_task_id` | yes | `task_id` of the parent, or `ROOT` | This encodes the tree |
| `methodology` | yes | Method **as stated in the doc**, else `NOT_SPECIFIED` | ⚠️ STRICT — never infer (R-METH) |
| `tools_tech` | yes | Tools/tech **as stated in the doc**, else `NOT_SPECIFIED` | ⚠️ STRICT — never infer (R-TOOL) |
| `task_summary` | **SUBSAMPLE ONLY** (see §2.1) | 1–2 sentences grounded in the doc | Paraphrase only what the text supports. On non-subsample docs write the literal token `OUT_OF_SCOPE` |
| `source_file` | yes | Filename + **section/heading** (page optional) | Multiple locations allowed, separated by `;` (R5) |
| `label_confidence` | yes | `high` / `medium` / `low` | Flag your own uncertainty; feeds QC (§7) |
| `notes` | optional | Rationale for a hard call; cite the rule applied | Also where conditionality is recorded (R11) |

**Schema is closed.** No additional columns. *(Decision 2026-08-01: a sensitivity-analysis flag column was considered and declined — the strict rule is scored as-is. If a sensitivity analysis is ever needed, it can be re-derived after the fact from `parent_task_id` plus the parent's `methodology` value, at the cost of a second pass.)*

---

## 2.1 `task_summary` scope decision — SUBSAMPLE (user decision, 2026-08-05)

**Rule:** `task_summary` is labeled in full on **every 3rd document in the order documents are actually labeled**, starting with the 1st. On every other document, write the literal token **`OUT_OF_SCOPE`**. All other fields are labeled on every row of every document, unchanged.

**Pre-committed before any Saturday labeling, deliberately.** The subsample is defined by *position in the labeling order* — which is recorded in `session-log.csv` as it happens — not by document content, not by agency, and not by which documents turned out to be interesting. Choosing it after seeing results is how a subsample becomes cherry-picking, and this is the same discipline the 45-doc draw used (`SELECTION-RULE_LOCKED_2026-08-02.md`).

**D01 already qualifies** — it was the 1st document labeled and carries `task_summary` on all 26 rows. Nothing to redo.

**Why.** The human labeling budget is the binding constraint on this study, and `task_summary` is the most expensive cell to write per row while carrying the least weight in the paper's central claim. That claim is about `methodology` and `tools_tech` — fields where the strict from-document-only rule makes an invented value a *counted hallucination*. `task` and `parent_task_id` are also labeled everywhere, because they are what make extraction precision/recall and tree-structure error measurable. Spending the same hours on full-coverage summaries would have bought a lower document count, and document count is what N depends on.

**What this costs, stated plainly so it is not discovered at review:** `task_summary` fidelity is reported as a **secondary measure on a subsample**, with its own smaller N stated alongside it, and is not eligible to carry a headline claim. That is a scope limitation, and it belongs in the paper's limitations section in those words.

**Not a rule change, not a version bump.** No labeling rule moved and no existing label changed — this allocates labeling effort. Recorded here rather than only in the ledger because a labeler reading §2 would otherwise fill the column on every row.

---

**`source_file` grain (resolves §10 Q1).** Section/heading is **required**; page number is **optional**. Pilot finding: headings are cheap to capture while labeling, page numbers required a second pass and would have eaten the time budget. Where one task legitimately cites two locations, record both separated by `;`.

**Normalization** (so scoring isn't tripped by cosmetics): trim whitespace; collapse newlines; consistent casing in `tools_tech`; use the literal token `NOT_SPECIFIED` — not blank, not "N/A", not "None" — so it scores unambiguously.

---

## 3. Procedure (per document)

1. **Read the whole document once** before labeling anything.
2. **Sketch the tree:** broad work areas = parents, concrete items = children. Assign `task_id` / `parent_task_id`.
3. **Fill the fields per task.** For `methodology` and `tools_tech`, copy or condense **only what the text states at that task**; if silent, `NOT_SPECIFIED`.
4. **Normalize `task`** to a clean imperative line. Keep `task_summary` to what the document supports.
5. **Self-review:** any real task missed? anything written the document doesn't state?
6. **Log the document** in `labeling-ledger.csv` the same session — doc ID, pages, task count, `NOT_SPECIFIED` counts, minutes, low-confidence count, rubric version.
7. **Add any hesitation** to `friction-log.md` as a one-liner and keep moving.

**Blind labeling.** Required for the QC subset (§7) and for anything compared against pre-existing labels. Optional elsewhere now that the rubric is frozen — blind labeling mattered most while the rules were still being calibrated.

---

## 4. Decision rules

Apply the lowest-numbered rule that fits; cite it in `notes`.

- **R1 — Split vs. merge.** Split when parts have separate work, deliverables, or skills. Merge restatements of one work item. Tie-breaker: would the team staff or plan them separately? If yes → split.
- **R-HIER — Parent vs. child vs. sibling.** Mirror the document's own structure. A task is a *child* only if genuinely inside the parent's scope; peers share a parent (or `ROOT`). Never invent intermediate layers.
- **R-METH — Methodology (STRICT).** Record a methodology **only if the document states how that task is done.** Otherwise `NOT_SPECIFIED`. An "obvious" method any engineer would assume, but the document doesn't state, is `NOT_SPECIFIED`.
- **R-TOOL — Tools & Technologies (STRICT).** Record a tool **only if the document names it at that task**, or unambiguously requires it ("must run on AWS GovCloud"). A tool that would *typically* be used but isn't named is `NOT_SPECIFIED`.
- **R-INHERIT — No inheritance. ⚠️ Highest-leverage rule in the rubric.** `methodology` and `tools_tech` **do not inherit from parent to child.** Each row stands alone and is judged only against the text at that task. If a parent task cites FAR Part 7 and its five children restate nothing, the children get `NOT_SPECIFIED` — all five. *(Resolves friction item F3. Rationale: the measurement is what the document states at a task, not what a careful human could infer across the tree. Inheritance would erase a large share of `NOT_SPECIFIED` values, which is the exact quantity the paper measures. Applied identically to all documents, no exceptions.)*
- **R-DOCLEVEL — Document-level tool lists do not distribute.** A tool named only in a document-wide section (a global "Tools & Software" list, a boilerplate environment paragraph) attaches to **no task**. Tools count **only where named at the task itself.** *(Resolves friction item F4. Same rationale as R-INHERIT: the unit of measurement is the task, and a global list is not a per-task statement. Applied identically to all documents.)*
- **R-STANDARD — A standard is not a tool.** A **tool** is something you *operate* (Excel, SharePoint, MS Project, Adobe, a named portal or system). A **standard** is something you *conform to* (NIST SP 800-53, FIPS 140-2, HSPD-12, Section 508, FAR clauses). Standards belong in `methodology`, never in `tools_tech` — and only when stated at the task, per R-METH and R-INHERIT. *(Resolves friction item F2.)*
- **R2 — Implied tasks.** Label only work that is stated or unambiguously entailed. No "good practice" additions — that is task-level hallucination in the baseline.
- **R5 — Duplicates / restatements.** One work item restated in several places is **one** task; record all locations in `source_file` separated by `;`. A summary table repeating body tasks creates nothing new.
- **R6 — Incorporated references (FAR, attachments).** If a referenced document imposes a concrete work item, label it once pointing at the reference, `label_confidence = medium`. Pure legal incorporation with no work: exclude.
- **R7 — Ambiguous / unreadable source.** Label your best reading, `label_confidence = low`, note the ambiguity. Never silently guess.
- **R8 — Out-of-scope content.** Issuer obligations, evaluation methodology, background. Exclude; if borderline, exclude and note why.
- **R9 — Third-party engagement examples are out of scope.** Documents sometimes include "client highlight" or case-study passages describing a *different* engagement — D01, a solicitation, contained a client-highlight passage. These are not tasks under this document. Exclude, note R9. *(Resolves friction item F7. Rule unchanged by the 2026-08-03 §0.2 correction; only its rationale wording was generalized from "narrative documents" — solicitation packages do this too, typically in attachments and background sections.)*
- **R10 — Direction-of-obligation test for submission mechanics.** *Exclude* mechanics that constrain **how a reader responds** (page limits, font requirements, portal upload steps). *Include* them when the contractor **produces** the material — authoring evaluation factors, compiling exhibits, building bidder mailing lists, assembling the solicitation package. Direction of the obligation is the test, not the subject matter. *(Resolves §10 Q3; the v0.2 blanket exclusion would have wrongly dropped real staffed work in the pilot document.)*
- **R11 — Document bundles.** A listed set of documents produced under **one** obligation is **one** task (e.g. "prepare LOAs, analysis of alternatives, D&F, and IT acquisition approval documents"). Split only when the document assigns separate deliverables, dates, or owners to the items. Cite R1 + R11 in `notes`. *(Resolves friction item F5.)*
- **R12 — Conditional tasks count.** A task qualified by "upon request," "as needed," or "if required" is a task. Conditionality changes when the work happens, not whether it is work the contractor must be prepared to perform. Include it, and write `conditional` in `notes`. *(Resolves friction item F6.)*

**Golden rule.** Torn between inventing and omitting → **omit and flag** `low`. Torn between a value and `NOT_SPECIFIED` → **`NOT_SPECIFIED`**. A miss is a measurable recall loss; an invented label corrupts the baseline you are measuring against.

---

## 5. Matching & scoring (golden ↔ AI output)

**Task match:** an AI task matches a golden task if they refer to the **same underlying work item** — normalized-text similarity of `task` ≥ a threshold **AND** consistent `source_file` location. Tune the threshold on the first 3–5 scored documents, freeze it, report it in the paper.

- **True positive** — golden task with a matching AI task.
- **False negative** — golden task the AI didn't produce (recall loss).
- **False positive** — AI task with no golden match (task-level hallucination).

**Per matched task, grade the fields:**
- **Hierarchy** — is `parent_task` correct, allowing for name variation? Reported separately.
- **Methodology / Tools (the headline)** — each scored as:
  - **Correct** — matches the doc-stated value, *or* correctly emits nothing where golden = `NOT_SPECIFIED`.
  - **Hallucinated** — AI gives a value where golden = `NOT_SPECIFIED`. ← **key metric.**
  - **Wrong** — golden has a stated value, AI's differs.
  - **Missed** — golden has a stated value, AI left it blank.
- **Task Summary** — adequate / inadequate by semantic faithfulness (no contradictions, no invented scope).

**Headline metrics:** task precision / recall / F1; task-level invented rate; **methodology hallucination rate**; **tools hallucination rate**; hierarchy accuracy; summary adequacy.

**Pilot signal to watch (D01):** `tools_tech` = `NOT_SPECIFIED` on 24 of 26 rows (92%), `methodology` on 17 of 26 (65%). If that ratio holds across the corpus, the hallucination surface is very large — the extractor has two columns to fill and the documents mostly do not supply them.

**Consistency probe (harness step 3):** run each document 5× at fixed prompt; measure variance of the emitted task set (mean pairwise Jaccard) and of methodology/tools values. Reuses the match definition above. Needs no golden labels.

---

## 6. Judge-audit error taxonomy (harness step 4 — the novel measurement)

Feed the devil's-advocate checker outputs with **known** errors; measure catch-rate and false-pass rate.

**(a) Natural errors** — real AI mistakes surfaced by §5, tagged by type.
**(b) Injected synthetic errors** — corrupt a *correct* golden list, one error per variant:

| Code | Injected error | Example |
|---|---|---|
| `E-OMIT` | Delete a real task | Drop a required data-migration task |
| `E-INVENT` | Add a task not in the doc | Add "user training" when never required |
| `E-METH` | Invent/alter a methodology | "Agile Scrum" where golden = `NOT_SPECIFIED` |
| `E-TOOL` | Invent/alter a tool | "Kubernetes" where the doc names no tool |
| `E-HIER` | Wrong parent / nesting | Move a child under the wrong parent |
| `E-SUMMARY` | Summary contradicts the doc | Summary adds scope not in the source |
| `E-SPLITMERGE` | Wrong granularity | Merge two independent tasks into one |

Record per variant: error code, whether the judge **caught** it, whether it **false-passed**. Report catch-rate per error type — the judge is likely far better at catching `E-INVENT` than `E-METH`/`E-TOOL`, and that contrast is a paper highlight. Keep injected variants in separate files (`_injected` suffix) so they never contaminate the §5 baseline.

---

## 7. Quality control

- **Self-consistency re-labeling:** re-label a random **~15%** of documents cold (blind to your first labels and the AI output) after a ≥48-hour gap. Compute intra-rater task-level F1. Target ≥ **0.90**; below that, the rubric is underspecified. Report the number in the paper.
- **Second labeler (stretch):** a ~10% overlap sample labeled by anyone else yields inter-rater agreement (Cohen's κ or task-F1). Big credibility boost, optional-if-time.
- **Freeze & version:** see the freeze-discipline note at the top.
- **Confidence audit:** before freeze, a final pass over every `label_confidence = low` row and every `NOT_SPECIFIED` call. That is where reviewers poke hardest.
