# Stage-attribution protocol

Written as a procedure so it can be applied to another pipeline and tested on seeded faults
(`e05_seeded_faults.py`). The code that implements each step is named in brackets.

## Definitions

- **Stage.** A step of the pipeline with an input and an output that can be logged
  separately: reader, cleaner, chunker, prompt construction, model call, response parser,
  row filter, merge, writer. The model call is one stage among these.
- **Reference implementation of a stage.** The version of that stage the audit compares
  against: the previous release, a pinned copy, or a candidate fix. The protocol attributes
  a failure *relative to* a reference. It cannot attribute a fault that has no reference
  version to swap in.
- **Symptom.** A measured property of the final output that falls outside the range that
  repeated runs of the reference pipeline produce, widened by a stated tolerance
  [`e05.METRICS`, `e05.symptoms`].
- **Attributed.** A symptom is attributed to stage *s* when reverting *s*, and only *s*, to
  its reference implementation makes the symptom disappear while every other stage stays
  fixed.

## Procedure

1. **Log every stage's input and output** for every document and run: reader text, cleaned
   text, each model input, each raw model response, the served model id and generation id,
   rows dropped by each filter, and the merged output [`pipeline.process_document`].
2. **Measure the noise floor.** Run the reference pipeline at least twice on the document
   and record each symptom metric's range [`e05.attribute`, `--ref-runs`].
3. **Detect symptoms.** Score the output under test against the answer key and with the
   key-free grounding checks. Every metric outside the reference range plus tolerance is a
   symptom. With no symptom, stop: nothing to attribute.
4. **Run dual-reference grounding.** Run each grounding check twice: against the source
   document, and against the text the model received (step 1 logs). An item that fails
   against the source but passes against the model input entered *before* inference. This
   step narrows the candidate stages to those upstream of the model
   [`lib.score_output`: `fab_moved_to_preinference`, `cont_moved_to_preinference`].
5. **Diff text-stage outputs (no model call).** For each text stage in pipeline order,
   compare its output with the reference implementation's output on the same input. The
   first stage whose output differs is a candidate. This is a cheap pre-screen. It shows
   where the text changed, not that the change caused the symptom
   [`e05.text_stage_diff`].
6. **Intervene on one stage at a time.** For each candidate stage, in pipeline order, revert
   that stage alone to its reference implementation, rerun the pipeline, and re-measure the
   symptoms [`e05.revert`]. In validation, every non-model stage is tried, so the
   candidate list from steps 4-5 is tested rather than trusted.
7. **Attribute.**
   - Exactly one stage clears every symptom: attribute the failure to that stage.
   - Several stages each clear it: report "ambiguous" and name them.
   - No non-model stage clears it: report "not cleared by any non-model stage". The model,
     or a stage without a reference implementation, remains the candidate. This is the
     only route by which the protocol assigns a failure to the model.
8. **Report** the symptom, the intervention, the effect size, the number of runs, and the
   served model ids for every run involved.

## Validation on seeded faults (e05)

| Plant | Stage | What is planted | Document rule |
|---|---|---|---|
| F1 | cleaner | `clean_text` also deletes `" and "` | most `" and "` in the key's top-level labels |
| F2 | reader | page tables are not read (≤ 40-page PDF) | largest share of reader text from tables |
| F3 | prompt | tools field gets a default value | most testable tools in the freeze |
| F0 | none | nothing (false-alarm check) | largest key among the remaining documents |

`attribute()` receives the faulted and reference pipelines and never reads which stage was
planted. The plant is unblinded only after it returns. A hit is: the attributed stage equals
the planted stage (for F0, no symptom).

## Known limits

- The protocol needs a reference implementation for each stage. In an audit with no prior
  version, the reference is a candidate fix, and the attribution is only as good as that fix.
- Tolerances are fixed in advance (`e05.METRICS`). A fault whose effect is smaller than the
  run-to-run noise at temperature 0.2 will be reported as "no symptom", which counts as a miss.
- A fault can have no measurable effect on the scored fields (for example, a table drop on a
  document whose tasks are all in running text). That is a miss for the protocol and a
  finding about the metrics, and it is reported as such.
- Three plants and one null plant show that the procedure can localize known faults. They do
  not estimate its hit rate on unknown faults.
