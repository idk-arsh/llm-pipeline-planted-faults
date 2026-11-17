# Planted faults in a deployed LLM extraction pipeline: tools and results

Code and results for the paper *Output Scores Do Not Locate Where Errors Enter an LLM Pipeline: Planted Faults in a Deployed Extraction System* by Arshdeep Ghotra (2026, under review).

The paper asks whether an output score can locate the stage where an error entered a multi-stage LLM pipeline. This repository holds the scoring and checking tools the study used, the labeling rules for the answer keys, the attribution protocol applied in the planted-fault test, and the per-document scores and result tables behind the paper's numbers.

## Contents

| Path | What it is | Paper |
|---|---|---|
| `tools/score.py` | Top-level task scorer (token-set match with a short-label guard), tool and methodology grounding checks against the document text, and the answer-key auditor | Sections 4.2-4.4 |
| `tools/grounding_dual_reference.py` | Runs the grounding checks against both the source text and the model input | Sections 4.3, 5.5 |
| `tools/marker_counter.py` | Counts boilerplate section types (procurement-wrapper markers) per document | Sections 4.6, 5.4 |
| `tools/common.py` | Shared loaders for the tools above | |
| `docs/labeling_rules.md` | The rules every answer key was labeled under (rubric v1.0, sections 1-7) | Section 4.1 |
| `docs/attribution_protocol.md` | The score-triggered attribution protocol, applied blind to the planted faults | Sections 4.8, 5.6 |
| `docs/heading_exclusion_sentence.txt` | The amended-prompt sentence | Section 5.4 |
| `results/` | Per-document scores and result tables | Sections 5-7 |

In `results/`, `per-document_scores.csv` holds the headline scores, `doc-type.csv` and `key-grain.csv` the document types and key grain, and the `aNN_` tables the analyses. The experiments map to tables as follows: cleaning fix `a22`, heading instruction `a24`, prompt ablation `a21`, run-to-run reruns `a25`, planted faults `a23` and `a26`.

## What is not released, and why

The procurement documents, the extractor (including its prompt), the answer keys, the model outputs and the raw model responses are not released. The documents are not the author's to publish, and the extractor belongs to the organization that operates it. Documents appear as `SOL-01` to `SOL-44`; the mapping to the originals is not published. Tables whose rows quote task labels, tool strings or document lines are left out; the counts derived from them remain in the tables that are here.

The tools therefore run on your own pipeline's outputs and answer keys, and they cannot regenerate this paper's numbers without the withheld inputs. Run against those inputs on 2026-11-16, `tools/score.py` reproduces the paper's headline: top-level F1 0.578 and precision 0.459 over 23 documents. `grounding_dual_reference.py` also needs your pipeline's reader and cleaning stages to rebuild the model input.

## Running

Python 3.11 or later; no network access. Install `openpyxl`, `PyMuPDF`, `python-docx`, `pdfplumber` and `numpy`.

Place your inputs under `data/`:

```
data/answers/<document>.csv          one answer key per document (fields in docs/labeling_rules.md, section 2)
data/model-output/<document>_tasks.xlsx   the pipeline's output (.xlsx or .csv)
data/pdfs/<document>.pdf             the source document (.pdf or .docx), read only for grounding
```

Then, from `tools/`:

```
python score.py                 # score every document present
python score.py <document>      # one document
python score.py --csv mine      # also write mine_per-document.csv and companions
```

## License

Code (`tools/`): MIT, see `LICENSE`. Documentation and results (`docs/`, `results/`): CC BY 4.0.

## Citation

Ghotra, A. (2026). *Output Scores Do Not Locate Where Errors Enter an LLM Pipeline: Planted Faults in a Deployed Extraction System*: tools and results. Zenodo. DOI to be added on release.
