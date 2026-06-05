# ObsiNote — Template Guide

Templates let you customise the structure of the notes ObsiNote generates. A template tells the LLM what sections to produce and what to put in each one. ObsiNote ships with a built-in default template; you can add your own for different meeting types (1:1s, project kickoffs, retrospectives, etc.).

---

## Where to put templates

Save template files as `.md` files in your Obsidian vault at:

```
{your vault}/ObsiNote/Templates/
```

The template name (without `.md`) will appear in the Template dropdown on the main screen and in the Import modals.

---

## How templates work

When ObsiNote generates a note, it:

1. **Substitutes placeholders** — replaces `{date}` and `{title}` with the actual meeting date and name before sending anything to the LLM.
2. **Sends the template to the LLM** — the LLM sees the substituted template as its output target and fills every section based on the transcript, scratch notes, and context you provided.
3. **Enforces the frontmatter date** — the `date:` frontmatter field is always set to the selected meeting date after generation, regardless of what the LLM wrote. This is guaranteed.
4. **Leaves sections empty when there is nothing to fill** — if the transcript has no relevant content for a section, the LLM leaves it blank rather than hallucinating.

---

## Available placeholders

These are substituted **before** the LLM runs. Use standard Python format-string syntax: `{placeholder}`.

| Placeholder | Value | When set |
|---|---|---|
| `{date}` | Meeting date in `YYYY-MM-DD` format | Always — from the date picker, defaults to today |
| `{title}` | Meeting name / label | Always — from the Meeting name field, defaults to `"Meeting"` |

Everything else in the template is **structure for the LLM** — section headings, bullet formats, checkbox syntax. The LLM reads the template and fills each section with content extracted from the transcript.

---

## Frontmatter fields

These YAML frontmatter fields are recognised by Obsidian and can be included in any template:

| Field | Example | Notes |
|---|---|---|
| `date` | `{date}` | Always use `{date}` — ObsiNote enforces this value |
| `type` | `meeting` | Static; use any value meaningful to your vault |
| `tags` | `[meeting, 1on1]` | Static per template; Obsidian uses these for filtering |
| `project` | *(LLM fills)* | Leave blank — the LLM can infer from transcript if you ask |
| `status` | `open` | Static; useful for tracking follow-ups in Obsidian |

> **Note:** Only `date` is substituted automatically. All other frontmatter fields are either static (written exactly as-is) or filled by the LLM if you leave them blank with a comment like `# infer from transcript`.

---

## Sections the LLM can fill

Any `## Heading` in your template becomes a section the LLM will try to fill from the transcript. The more specific and consistently named the heading, the better the LLM output.

| Section heading | What the LLM extracts |
|---|---|
| `## Participants` | Names of people who spoke or were mentioned as present |
| `## Context` | Background, purpose, or project this meeting relates to |
| `## Summary` | Key points discussed; a few sentences or bullet points |
| `## Decisions` | Explicit decisions made in the meeting |
| `## Action Items` | Tasks, owners, and deadlines mentioned |
| `## Open Questions` | Questions raised but not resolved |
| `## Blockers` | Issues blocking progress |
| `## Feedback` | Feedback exchanged (useful for 1:1 templates) |
| `## Goals` | Goals or objectives discussed |
| `## Risks` | Risks or concerns raised |
| `## Next Steps` | Upcoming actions or next meeting agenda |
| `## Notes` | Anything that doesn't fit the other sections |

You can use any heading text — these are not magic keywords. The LLM adapts to whatever structure you define.

---

## Annotated example

```markdown
---
date: {date}          ← always use {date} — ObsiNote fills this in
type: meeting         ← static; change per template type
tags: [meeting]       ← static; add your own tags here
---

# {title}            ← always use {title} — ObsiNote fills this in

## Participants
                      ← LLM fills: names extracted from transcript

## Context
                      ← LLM fills: meeting purpose/background

## Summary
                      ← LLM fills: key points discussed

## Decisions
                      ← LLM fills: explicit decisions made

## Action Items
- [ ] Task — responsible person    ← LLM follows this format for each task

## Notes
                      ← LLM fills: anything else worth capturing
```

---

## Ready-to-use templates

### 1. Default meeting (mirrors the built-in)

```markdown
---
date: {date}
type: meeting
tags: [meeting]
---

# {title}

## Participants

## Context

## Summary

## Decisions

## Action Items
- [ ] Task — responsible person

## Notes
```

---

### 2. One-on-one (1:1)

```markdown
---
date: {date}
type: 1on1
tags: [meeting, 1on1]
---

# {title}

## Topics discussed

## Feedback

## Blockers

## Action Items
- [ ] Task — responsible person

## Next meeting agenda
```

---

### 3. Project / technical meeting

```markdown
---
date: {date}
type: meeting
tags: [meeting, technical]
---

# {title}

## Participants

## Context

## Summary

## Decisions

## Open Questions

## Risks

## Action Items
- [ ] Task — responsible person

## Next Steps
```

---

### 4. Retrospective

```markdown
---
date: {date}
type: retrospective
tags: [meeting, retrospective]
---

# {title}

## What went well

## What could be improved

## Action Items
- [ ] Improvement — responsible person

## Notes
```

---

## Tips

- **Keep section names consistent** across templates so your vault is queryable with Obsidian's Dataview.
- **Action items always use `- [ ]` format** — the LLM is instructed to follow the checkbox style it sees in the template.
- **Add Obsidian Dataview fields** in frontmatter if you use them: `project:`, `sprint:`, `quarter:` etc. Leave them blank and the LLM will attempt to fill them from the transcript, or set them as static values.
- **The LLM uses the glossary** regardless of the template — correct spellings of project names and abbreviations are applied across all sections.
- **Scratch notes and extra context** you provide in the UI are given to the LLM in addition to the template — they feed into every section.
