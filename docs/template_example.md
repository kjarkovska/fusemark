# FuseMark — Template Guide

Templates let you customise the structure of the notes FuseMark generates. A template tells the LLM what sections to produce and what to put in each one. FuseMark ships with a built-in default template; you can add your own for different meeting types (1:1s, project kickoffs, retrospectives, etc.).

---

## Where to put templates

Save template files as `.md` files in your Obsidian vault at:

```
{your vault}/FuseMark/Templates/
```

The template name (without `.md`) will appear in the Template dropdown on the main screen and in the Import modals.

---

## How templates work

When FuseMark generates a note, it:

1. **Sends your template to the LLM as-is** — a vault template's `{date}`/`{title}` text is *not* substituted before the LLM sees it (that automatic substitution only applies to FuseMark's own built-in template). The LLM is instructed to use your template as the output structure and fills it in from the transcript, scratch notes, and context you provided — in practice it reliably fills the date/title fields itself, but write literal values there if you want to be certain.
2. **Enforces the frontmatter date afterward** — regardless of what the LLM wrote, the `date:` frontmatter field is always overwritten with the selected meeting date once generation finishes. This is guaranteed.
3. **Leaves sections empty when there is nothing to fill** — if the transcript has no relevant content for a section, the LLM leaves it blank rather than hallucinating.

---

## Available placeholders

`{date}` and `{title}` are conventional placeholders the LLM recognizes and fills from the meeting date / Meeting name field — but for a vault template, this is the LLM following the pattern, not automatic substitution FuseMark performs. The `date:` frontmatter field is the one exception: it's always overwritten with the real meeting date after generation, regardless of what the LLM wrote there.

Everything else in the template is **structure for the LLM** — section headings, bullet formats, checkbox syntax. The LLM reads the template and fills each section with content extracted from the transcript.

---

## Per-template instructions (optional)

A template can carry a few lines of extra behavioral instructions for the LLM, layered on top of its structural sections — for example, a sales-call template that should stay terse and call out competitor mentions. Wrap them in an HTML comment anywhere in the file:

```markdown
<!-- fusemark:prompt
Be terse. Extract objections and competitor mentions by name.
-->
```

This block is stripped out before the template is shown to the LLM as its output structure, so it never leaks into the generated note — it's appended separately as extra guidance. It's optional; a template with no block behaves exactly as before. Multiple blocks in one template are concatenated together.

---

## Frontmatter fields

These YAML frontmatter fields are recognised by Obsidian and can be included in any template:

| Field | Example | Notes |
|---|---|---|
| `date` | `{date}` | Always use `{date}` — FuseMark enforces this value |
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
date: {date}          ← always use {date} — FuseMark fills this in
type: meeting         ← static; change per template type
tags: [meeting]       ← static; add your own tags here
---

# {title}            ← always use {title} — FuseMark fills this in

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
