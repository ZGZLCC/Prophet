# Material extraction prompt

Use the relevant section only.

## A. Extract one Chunk

You receive one JSON object containing:

- chunk_id, period, target, start_time, end_time;
- messages with id, time, sender, and text.

Return a JSON array containing exactly one envelope:

~~~json
[
  {
    "chunk_id": "chunk_000001",
    "materials": [
      {
        "type": "interaction",
        "observation": "目标人物表达学习压力，对方以玩笑回应，目标人物继续顺着玩笑交流。",
        "context": "双方正在讨论作业进度。",
        "tags": ["学习压力", "玩笑回应"],
        "message_ids": ["msg_000000001", "msg_000000003"]
      }
    ]
  }
]
~~~

Rules:

1. Return 0–3 Materials. Use an empty materials array when nothing is useful.
2. Discuss the target only; use the other speaker solely to explain context.
3. Describe what is directly observable in this Chunk.
4. Preserve the concrete subject or event (for example physics homework, sleep loss, a missed reply, a promised task, or arranging a trip) and the target's observable sequence of actions. Do not collapse it into “学习”“生活”“沟通” when the messages support a more specific description.
5. observation should normally contain “specific scene → observable response”; include order or adjustment when visible, such as asking, checking, pausing, resuming, reminding, refusing, or changing an arrangement.
6. Do not infer personality, MBTI, attachment style, diagnosis, hidden motive, cause, or future behavior.
7. Use only language, emotion, interaction, conflict, support, or event as type.
8. observation must be time-local and neutral. Do not write “总是”“本质上”“说明其性格”.
9. context may be empty. Do not fill missing background.
10. Use 1–6 exact message_ids from this Chunk and include at least one target message.
11. Prefer the smallest evidence set that supports the observation.
12. Do not copy message text into the JSON; the report builder retrieves exact evidence.
13. Return JSON only.

## B. Abstract one period

You receive one period and its compact Material records. Each Material includes its chunk_id. Summarize the target's observable patterns rather than repeating individual messages or merely naming broad categories.

Return one JSON object:

~~~json
{
  "period": "2023-10",
  "summary": "本期抽样材料涉及物理作业、考试复习、睡眠不足和一次未及时回应的争论。目标人物在任务场景中会连续确认条件并拆解下一步；出现疲劳时会说明状态并调整安排；在分歧中会指出具体未满足的期待并约定后续处理。",
  "patterns": [
    {
      "dimension": "学习追问与任务拆解",
      "summary": "在物理作业和考试复习等任务中，目标人物会连续询问条件或步骤，得到解释后继续核对理解并安排下一步。",
      "conditions": "主要见于本期已抽样的课程学习和共同完成具体任务场景；不能外推到其他决策。",
      "material_ids": ["mat_000183_01", "mat_000201_01"],
      "counterexample_ids": []
    }
  ]
}
~~~

Style contract:

1. Build the period summary from concrete behavioral threads. Name the actual tasks, topics, events, bodily states, or disagreements represented in the evidence. A compact synthesis is wanted; a quotation list is not.
2. Each pattern must preserve this hierarchy:
   - dimension: a plain-text “specific scene/topic + observable action” label, such as “学习追问与任务拆解” or “分歧中的具体边界表达”; never use Markdown and never use a bare category such as “沟通方式”“情绪表达”“互动模式”.
   - summary: state at least two concrete scenes or topics when available, followed by what the target observably does, including sequence, adjustment, or response when supported.
   - conditions: state where the pattern appears and where the evidence does not reach. Avoid the empty boilerplate “仅限抽样材料” without naming the actual contexts.
   - material_ids: cite the supporting evidence; counterexample_ids: retain conflicting or limiting observations.
3. Group Materials by a repeated behavioral thread, not by the six Material types. Prefer meaningful detail such as “物理、数学和照片处理任务” over “学习和生活”.
4. Each pattern needs at least two distinct Material IDs from at least two different chunk_ids in this period. Multiple Materials extracted from one conversation do not establish repetition.
5. Use as many patterns as the evidence genuinely supports, normally 2–6 for a rich period. Do not fill a quota, merge unrelated behaviors, or repeat the same evidence under renamed headings.
6. Put conflicting evidence in counterexample_ids instead of hiding it. Preserve behaviors that differ by scene.
7. If evidence is sparse, write a cautious, concrete summary and return patterns as [].
8. Do not infer personality essence, diagnosis, hidden motive, cause, improvement, deterioration, or permanence.
9. Return plain JSON only. Do not put `**`, bullets, headings, or other Markdown inside JSON strings.

## C. Abstract across periods

You receive compact period summaries and their evidence IDs.

Return one JSON object:

~~~json
{
  "summary": "现有材料显示，目标人物在压力场景中通常会说明状态，但处理分歧的方式随时期和情境不同。",
  "recurring_patterns": [
    {
      "dimension": "说明当前状态",
      "summary": "多个时期都出现目标人物直接说明压力或不适状态的情况。",
      "conditions": "证据集中在学习或身体不适场景。",
      "material_ids": ["mat_000183_01", "mat_000407_01"],
      "counterexample_ids": []
    }
  ],
  "time_variations": [
    {
      "dimension": "分歧处理方式",
      "summary": "较早时期直接指出不满；较晚时期出现先暂停、稍后恢复沟通的做法。",
      "earlier_material_ids": ["mat_000211_01"],
      "later_material_ids": ["mat_000519_01"]
    }
  ],
  "uncertainties": [
    "冲突场景数量较少，不能判断哪种处理方式更稳定。"
  ]
}
~~~

Rules:

1. Lead with abstractions supported by multiple Materials; do not merely restate period summaries.
2. Keep the same “concrete scenes → observable actions → boundary → evidence” style used for period patterns. Retain named topics or events when they materially define the pattern; do not replace them with bare categories.
3. A recurring pattern must cite at least two periods.
4. A time variation must cite at least one earlier and one later Material.
5. Preserve contextual or contradictory behavior rather than averaging it away.
6. Do not claim improvement, deterioration, causation, diagnosis, or fixed personality.
7. Put missing coverage and competing explanations in uncertainties.
8. Use plain text in all fields; do not add Markdown formatting.
9. Return JSON only.
