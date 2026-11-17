# Report format contract

The public deliverables are two UTF-8 Markdown files: the full report and a `_core` reader version containing sections 1–4. Generated work files are implementation details.

## Required sections

1. 综合概括
2. 分期概括
3. 覆盖情况
4. 客观概览
5. 分期证据附录
6. 素材索引
7. 使用边界

## Material card

Each card contains:

- stable Material ID and one of six types;
- exact start and end time derived from cited messages;
- a neutral observation;
- optional immediate context;
- 1–6 exact evidence messages with message_id, time, sender, and text;
- concise tags.

The builder, not the model, derives periods, timestamps, IDs, and evidence text. Evidence cards are an appendix; the main report consists of period-level and cross-period abstractions.

## Time and scale

- Use natural months by default and natural weeks for short spans. Dense inputs automatically narrow to week, day, or hour buckets so one abstraction request does not exceed roughly 20,000 source messages.
- Keep every active target period in the coverage table.
- Select max(1, ceil(period_chunk_count × 20%)) Chunks in each active period.
- Split the quota between deterministic high-value ranking and uniform time coverage.
- Do not impose a fixed global report length.
- Keep different or contradictory periods side by side and link comparisons to Material IDs.
- Require at least two Materials for a period pattern and at least two periods for a recurring overall pattern.
- Require a period pattern's Materials to span at least two Chunks. Each period pattern preserves concrete scene/topic, observable action, boundary, and evidence instead of merely naming a broad category.

## Boundary

The report may generalize observable behavioral patterns when multiple pieces of evidence support them. It remains a sampled preparation artifact and cannot establish a diagnosis, hidden motive, cause, prediction, or timeless personality essence.
