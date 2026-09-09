# How {{ cookiecutter.friendly_name }} is evaluated

Read this page if you decide what this service is allowed to say. The metrics, the bars, the
cases and the quality floors below are generated from the artifacts that actually gate the build,
so they cannot drift from what runs: `make evals-doc-check` fails the build when this page and
those artifacts disagree.

## How to run it

```sh
make eval             # the deterministic half, offline, no credentials
make eval-narrative   # the judged half, offline by default, no model server
make evals-doc-check  # this page is still true
```

All three run inside `make gate`, which is what CI runs on every change.

## Two kinds of scoring, and why both

Most of what matters here is decided by deterministic code and is scored by rules: whether the
triage reached the severity a reviewer assigned, whether anything personal survived into the
audit trail. Those are questions with answers, and a judge would only add noise to them.

They leave a gap. A narrative can be correctly banded, correctly redacted, and still omit the
fact the reviewer needed, cite nothing, or assert a certainty nobody has. Deciding that is a
judgement, so it is judged, and the judge is held to the same standard as everything else: it
must be shown able to fail before anything it certifies is believed.

The judged half runs offline by default, so it is inside the gate with no model server and no
credentials. A real model judge is opt-in on the command line and never from the environment: a
gate whose scorer a stray variable could swap is not a gate.

## What is measured, and against what bar

Every bar below lives in `eval/rubrics/*.yaml` next to the argument for it, and the
runner reads it from there. A metric with no reviewed bar, and a bar nothing measures,
both fail the build.

The third column is the denominator rule, and it applies only to a metric whose score
is a FRACTION over scored cases: such a threshold `t` tolerates a single miss only over
at least `1/(1-t)` cases, and below that the bar is arithmetically identical to 1.0
while reading as though it had headroom. A metric that is 1.0-or-0.0 for the whole run
is marked `all or nothing`: it already refuses a single failure, so a bigger corpus
changes nothing about what its bar means. Each rubric declares which it is, in
`denominator.kind`, rather than the rule being guessed from the number.

| Metric | Bar | Needs at least | Corpus has | What it measures |
|---|---|---|---|---|
| `decision_accuracy` | 0.8 | 5 cases | 6 | Fraction of golden cases whose triaged severity equals the severity a reviewer assigned by reading the case. |
| `pii_safety` | 0.99 | all or nothing | 6 | 1.0 unless a raw identifier survives into any audit record, scanned two independent ways: the shared pii-kit pack the runtime redactor masks with, and the case's own planted literal. |

## What is exercised

- **6 golden triage cases** in `eval/datasets/golden_cases.jsonl`, each
  carrying the severity a reviewer assigned by reading it. The expectation is the
  dataset's, never the service's own verdict: a metric that compared the engine with
  itself would be a tautology with a threshold.
- **2 of them plant a raw identifier**, so the leak metric has a target it
  could miss. A corpus that plants nothing scores a vacuous 1.0, and the runner refuses
  one for that reason.
- **2 judged narrative cases** in `eval/datasets/narrative_golden.jsonl`, each written once per profile with the band
  it is expected to land in. A profile that quietly got BETTER fails too, because a
  band nobody predicted is a change nobody reviewed.

## Where the quality bars come from

`config/quality-floors.toml` is owned by model risk. A **floor** refuses: below it a
profile must not serve that vertical, which is not the same as serving it worse. A
**target** is full quality. Between the two is DEGRADED, the band a portability claim
describes in adjectives and which nothing measures until a floor exists.

| Vertical | Floor | Target | Why |
|---|---|---|---|
| `{{ cookiecutter.project_slug }}` | 0.6 | 0.85 | A triage narrative a reviewer reads before anything is acted on. |

## What is NOT measured here

Naming this is part of the page, because an unmeasured claim that goes unmentioned reads as a
measured one.

- **A real model's words.** Every metric above scores a deterministic core. The moment this
  repository binds a generation port, metrics named `groundedness` or `citation_accuracy` become
  measurements of the VALIDATOR rather than of the model's restraint, and they will stay green
  through a model swap or a prompt regression. `eval/replay_generation.py` and
  `scripts/record_model_fixtures.py` are the scaffold for closing that: record once by hand
  against the managed profile, scrub the whole batch, commit it, replay it offline forever.
- **Retrieval quality.** Nothing here retrieves yet. When it does, recall@k and precision@k
  belong in this gate as their own metrics (`agent_eval_kit.retrieval`), scored upstream of what
  the model did with what it retrieved: a knowledge base that silently stops returning the right
  document still produces a clean citation set.
- **Production traffic.** Everything here is a golden set. Nothing samples live requests.

## How a metric is prevented from being decoration

Four rules, each closing a way a gate reports a confident number over something it did not
measure. They are enforced by `eval/run_eval.py` itself, not by review:

1. **The bars are read from the rubrics, in both directions.** A metric scored with no reviewed
   bar fails the build, and so does a bar that names no metric. The second is the one that rots
   quietly, because a rubric for a deleted metric still reads as governance.
2. **The falsification proof runs first, in this process.** `prove_before_scoring` executes each
   metric's red case before a single golden score is trusted. Run only in `tests/`, a proof says
   the metric could have gone red on some machine at some point.
3. **The denominator is checked against the bar.** A 0.80 accuracy bar over four cases is a 1.0
   wearing a 0.80 label, and nothing else in a repository compares a threshold with a corpus size.
4. **The leak scan reads what the service persisted.** Building a string in the eval and scanning
   that would score the redactor against itself, over text the service never produced.
