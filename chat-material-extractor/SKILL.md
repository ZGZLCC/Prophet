---
name: chat-material-extractor
description: Turn exported two-person text chat JSON into full and reader-focused Markdown reports that abstract one person's recurring and changing behavioral patterns for later personality analysis. Use for chat preprocessing, sampling, period summaries, or targeted material retrieval; do not use it for diagnosis or final personality profiling.
---

# Chat Material Extractor V1.2

Create two evidence-grounded Markdown reports: a full report and a reader-focused `_core` report. Both abstract a user-selected target speaker's recurring, conditional, and changing behavior across time. Treat the other speaker only as conversational context. Raw quotations belong only in the full report's evidence appendix.

## Required input

- A local exported chat JSON or JSONL file containing time, sender, and text. A top-level export object whose `messages` field contains the message array is also supported; its other top-level fields are metadata.
- The exact sender name to analyze.
- A destination Markdown path.

If the target sender is unclear, run:

~~~text
python scripts/extract.py inspect <chat-file>
~~~

Show the discovered sender names and ask the user to choose. Never guess.

## Workflow

When this Skill is being executed by Codex or another reasoning agent, use the manual workflow below. The current agent performs the extraction and abstraction itself. Do not check for, request, or require an API key, and do not run the `run` command.

The `run` command is only an optional standalone entry point for a human or non-reasoning automation that wants the Python process to call an external Responses API:

~~~text
python scripts/extract.py run <chat-file> --target <sender> --output <report.md> --keep-work
~~~

Its configuration comes from `.env` (see `.env.example`) or environment variables. Never print, copy into prompts, or persist `LLM_API_KEY`.

1. Prepare deterministic data:

~~~text
python scripts/extract.py prepare <chat-file> --target <sender> --work-dir <work-dir>
~~~

2. When the user names a focus such as conflict, anger, support, or a specific event, add matching Chunks before annotation:

~~~text
python scripts/extract.py search --work-dir <work-dir> --query <keywords>
~~~

Use --after or --before when the request has a time boundary. This is the V1.2 targeted-search path.

3. Read [prompts/extract_material.md](prompts/extract_material.md), then fetch the next pending Chunk:

~~~text
python scripts/extract.py next --work-dir <work-dir>
~~~

For that Chunk, create a JSON array following the prompt and save it to a temporary batch file. Record it:

~~~text
python scripts/extract.py record --work-dir <work-dir> <batch-file>
~~~

Repeat next and record until next returns an empty array. Record an envelope even when a Chunk contains no valid Material; an empty materials array marks it complete.

4. Abstract each period separately. Fetch one pending period:

~~~text
python scripts/extract.py summary-next --work-dir <work-dir>
~~~

Use section B of the prompt, save its JSON, and record it:

~~~text
python scripts/extract.py record-summary --work-dir <work-dir> <period-summary.json>
~~~

Repeat until summary-next returns an empty array. A period pattern needs at least two Materials; keep patterns empty when only a single observation exists.

For every period, follow section B's style contract exactly: preserve concrete scenes or topics, describe the target's observable sequence of actions, state the evidence boundary, and cite Materials from at least two different Chunks. Do not replace this with bare category sentences. If `record-summary` rejects a generic label, Markdown decoration, short summary, or single-Chunk pattern, revise the abstraction rather than bypassing validation.

5. Prepare the compact cross-period input:

~~~text
python scripts/extract.py overall-input --work-dir <work-dir> --output <overall-input.json>
~~~

Use section C of the prompt to create and record the overall abstraction:

~~~text
python scripts/extract.py record-overall --work-dir <work-dir> <overall.json>
~~~

Do not force recurring patterns or changes when the evidence is insufficient.

6. Build both reports:

~~~text
python scripts/extract.py build --work-dir <work-dir> --output <report.md> --keep-work
~~~

The command creates `<report.md>` as the full report and `<report_core.md>` as the reader-focused version without evidence appendix or indexes. These two Markdown files are the public deliverables. Keep the hidden work directory for V1.2 follow-up searches; omit --keep-work only when the user explicitly wants all generated cache removed.

For a later targeted question, run search against the retained work directory, complete the new next, summary-next, and overall steps, then rebuild with --force --keep-work.

## Invariants

- Never send the complete chat file to the model. Work one selected Chunk at a time.
- Abstract multiple observations into evidence-bounded behavioral patterns, but do not turn them into diagnoses, hidden motives, causes, predictions, or timeless traits.
- Keep contradictory observations from different periods; never average them into one timeless claim.
- Every Material must cite 1–6 message_ids from its own Chunk, including at least one target message.
- Every period pattern must cite at least two Materials. Every cross-period recurring pattern must cite at least two periods.
- Period pattern evidence must span at least two different Chunks. Write labels as plain “specific scene/topic + observable action” phrases, not broad type names or Markdown-formatted headings.
- Use only the six supported types: language, emotion, interaction, conflict, support, event.
- Preserve exact evidence wording and timestamps. Do not invent missing context.
- Let the script validate evidence and assemble the Markdown; do not hand-edit the finished report.

Read [references/report-format.md](references/report-format.md) only when changing or auditing the report contract.

## Check

After modifying this Skill or its script, run:

~~~text
python scripts/extract.py self-test
~~~
