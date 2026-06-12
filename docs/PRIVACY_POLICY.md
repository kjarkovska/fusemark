# Privacy Policy

_Last updated: 2026-06-11_

FuseMark is a local desktop application. It is designed so your meeting audio never
leaves your computer. This document explains exactly what data the app handles and
where it goes.

## What the developer collects

**Nothing.** FuseMark has no analytics, no telemetry, and no developer-operated
servers. The developer cannot see your recordings, transcripts, notes, or settings.

## What stays on your machine

- **Audio recordings** — captured and processed entirely locally; never uploaded.
  Stored in `%APPDATA%\FuseMark\recordings\` and optionally auto-deleted after
  processing.
- **Transcripts and generated notes** — saved to your chosen output folder / Obsidian
  vault, and in the local job database (`%APPDATA%\FuseMark\jobs.db`).
- **Settings** — `%APPDATA%\FuseMark\config.json`.
- **Logs** — `%APPDATA%\FuseMark\logs\fusemark.log` (local only).
- **Whisper transcription model** — downloaded once to `%LOCALAPPDATA%\FuseMark\models\`.
- **API keys** — stored in the **Windows Credential Manager**, never in files or config.

## What leaves your machine

1. **Transcript text + the notes/context you type → your chosen LLM provider.**
   To generate a structured meeting note, the app sends the transcript and any
   scratch notes/context you entered to the LLM provider you configured (Anthropic,
   OpenAI, or Mistral), using **your own API key**. Raw audio is never sent. Your use
   of that provider is governed by their privacy policy:
   - Anthropic — <https://www.anthropic.com/legal/privacy>
   - OpenAI — <https://openai.com/policies/privacy-policy>
   - Mistral — <https://mistral.ai/terms/>

2. **Transcription model download → Hugging Face.** The first time you use a Whisper
   model, it is downloaded from Hugging Face Hub (a normal HTTPS file download).

3. **Update check → GitHub.** If enabled (Settings → Updates), the app periodically
   asks the public GitHub Releases API whether a newer version exists. This is a
   normal HTTPS request; no personal data is sent beyond what any web request
   includes (your IP address and the app version in the User-Agent).

You can disable the update check in Settings. You can avoid the LLM step entirely by
not generating notes.

## Your responsibilities (GDPR)

Because all processing is local and uses your own API keys, **you are the data
controller** for any recordings and transcripts you create. If meetings include
other people, follow applicable laws on recording and consent in your jurisdiction.

## Data deletion

To remove all app data, uninstall the app and delete the `%APPDATA%\FuseMark\` and
`%LOCALAPPDATA%\FuseMark\` folders. Notes already written to your vault are yours to
keep or delete.

## Contact

Questions about this policy: `<support-email>` _(fill in before publishing)_.
