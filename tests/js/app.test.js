'use strict';

// static/app.js is a plain browser script (no module system, no bundler —
// it's served as-is by Flask). To load it under Node's test runner, this
// file stubs just enough of the DOM global for app.js's one piece of
// top-level (not-inside-a-function) DOM code — the DOMContentLoaded
// registration — to no-op instead of throwing on `document is not defined`.
//
// Scope: this suite covers app.js's pure/DOM-free logic layer only (string
// escaping, JSON parsing, formatting, the level-meter math, the glossary
// selection Set). Anything that actually touches document/fetch — renderJob,
// pollLevel, refreshJobs, the various submit* handlers — is not covered here
// and would need a real or simulated DOM (e.g. jsdom) to test meaningfully;
// deliberately not pulling in that dependency for a handful of functions.

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

global.document = {addEventListener() {}};
global.window = {
  STRINGS: {
    status_recording: 'Recording',
    status_queued: 'Queued',
    status_transcribing: 'Transcribing',
    status_generating: 'Generating',
    status_done: 'Done',
    status_error: 'Error',
  },
};

const app = require(path.join('..', '..', 'static', 'app.js'));

// ------------------------------------------------------------------
// esc()
// ------------------------------------------------------------------

test('esc escapes html-significant characters, including single quotes', () => {
  assert.equal(app.esc(`<script>&"'</script>`), '&lt;script&gt;&amp;&quot;&#39;&lt;/script&gt;');
});

test('esc coerces non-string input', () => {
  assert.equal(app.esc(42), '42');
});

// ------------------------------------------------------------------
// parseGlossaryTerms()
// ------------------------------------------------------------------

test('parseGlossaryTerms returns [] for falsy input', () => {
  assert.deepEqual(app.parseGlossaryTerms(''), []);
  assert.deepEqual(app.parseGlossaryTerms(null), []);
  assert.deepEqual(app.parseGlossaryTerms(undefined), []);
});

test('parseGlossaryTerms returns [] for invalid JSON rather than throwing', () => {
  assert.deepEqual(app.parseGlossaryTerms('not json'), []);
});

test('parseGlossaryTerms returns [] when the JSON is not an array', () => {
  assert.deepEqual(app.parseGlossaryTerms('{"a":1}'), []);
});

test('parseGlossaryTerms filters out non-object / missing-canonical entries', () => {
  const raw = JSON.stringify([
    {canonical: 'Jira', context: 'tracker'},
    'not an object',
    {no_canonical: true},
    null,
    42,
  ]);
  assert.deepEqual(app.parseGlossaryTerms(raw), [{canonical: 'Jira', context: 'tracker'}]);
});

// ------------------------------------------------------------------
// progressFromJob() / etaFromJob() / statusLabel()
// ------------------------------------------------------------------

test('progressFromJob defaults to 0 when absent', () => {
  assert.equal(app.progressFromJob({}), 0);
  assert.equal(app.progressFromJob({progress: 42}), 42);
});

test('etaFromJob formats seconds as mm:ss', () => {
  assert.equal(app.etaFromJob({eta: 125}), '02:05');
  assert.equal(app.etaFromJob({eta: 5}), '00:05');
});

test('etaFromJob returns null when eta is null or absent', () => {
  assert.equal(app.etaFromJob({}), null);
  assert.equal(app.etaFromJob({eta: null}), null);
});

test('statusLabel maps known statuses and falls back to the raw value', () => {
  assert.equal(app.statusLabel('done'), 'Done');
  assert.equal(app.statusLabel('some_unknown_status'), 'some_unknown_status');
});

// ------------------------------------------------------------------
// formatLocalDate()
// ------------------------------------------------------------------

test('formatLocalDate returns blank for falsy input', () => {
  assert.equal(app.formatLocalDate(''), '');
  assert.equal(app.formatLocalDate(null), '');
});

test('formatLocalDate formats an ISO string as "YYYY-MM-DD HH:MM"', () => {
  // Not asserting an exact clock time — that's timezone-dependent (local
  // time, by design, so the user sees their own wall clock) and would flake
  // between a dev machine and a CI runner in a different zone.
  assert.match(app.formatLocalDate('2026-01-15T09:05:00Z'), /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
});

// ------------------------------------------------------------------
// stripVtt()
// ------------------------------------------------------------------

test('stripVtt drops the WEBVTT header and timestamp cue lines', () => {
  const vtt = 'WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<v Speaker>Hello world</v>\n';
  assert.equal(app.stripVtt(vtt), 'Hello world');
});

test('stripVtt handles multiple cues', () => {
  const vtt = [
    'WEBVTT', '',
    '00:00:01.000 --> 00:00:02.000',
    '<v Alice>First line</v>',
    '00:00:03.000 --> 00:00:04.000',
    '<v Bob>Second line</v>',
  ].join('\n');
  assert.equal(app.stripVtt(vtt), 'First line\nSecond line');
});

// ------------------------------------------------------------------
// toggleGlossaryTerm() / glossarySelection
// ------------------------------------------------------------------

test('toggleGlossaryTerm adds/removes canonicals from the job selection Set', () => {
  app.glossarySelection['job-1'] = new Set(['Jira']);
  app.toggleGlossaryTerm('job-1', 'Kanban', true);
  assert.ok(app.glossarySelection['job-1'].has('Kanban'));
  app.toggleGlossaryTerm('job-1', 'Jira', false);
  assert.ok(!app.glossarySelection['job-1'].has('Jira'));
});

test('toggleGlossaryTerm is a no-op for a job id with no seeded selection', () => {
  delete app.glossarySelection['no-such-job'];
  assert.doesNotThrow(() => app.toggleGlossaryTerm('no-such-job', 'Whatever', true));
});

// ------------------------------------------------------------------
// levelToBarHeight()
// ------------------------------------------------------------------

test('levelToBarHeight floors silence to a visible sliver, not zero', () => {
  const {heightPx, opacity} = app.levelToBarHeight(0);
  assert.equal(heightPx, Math.round(0.06 * 16));
  assert.ok(opacity > 0);
});

test('levelToBarHeight caps at the full 16px bar height', () => {
  assert.equal(app.levelToBarHeight(1).heightPx, 16);
  assert.equal(app.levelToBarHeight(5).heightPx, 16); // over-driven input still clamps
});
