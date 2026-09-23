# Browser tests

Thirty-four safety-critical flows, run in Chromium against the real frontend.

```bash
cd frontend
npm run test:e2e
```

That is the whole command. Playwright starts the stub backend and a Vite server
on private ports (8273 / 5273, deliberately not the development defaults), runs
the suite, and stops them again. No NVIDIA key is read and nothing leaves the
machine.

First run only:

```bash
npx playwright install chromium                                  # ~115 MB
../backend/.venv/Scripts/python.exe e2e/make_fixtures.py         # PDFs are gitignored
```

## Why the backend is a stub

The flows worth testing in a browser are the ones a user must not be misled by:
a withheld finding, an incomplete document, a provider failure, an unsupported
answer, an explanation that was not verified. Reaching those through the real
system means a real model call that may or may not produce that state on any
given day, and a test that only sometimes exercises the path it is named after
is not a test.

`stub_backend.py` mirrors `backend/app/schemas/` exactly. If a schema changes
and the stub is not updated, these tests fail — that is the intended signal.
The backend's own behaviour is covered by 1587 deterministic Python tests that
do use the real code, including `test_structural_safety.py`, which drives the
real endpoints end to end.

Scenario selection is by uploaded filename:

| Upload | Scenario |
|---|---|
| `notes.txt` | upload rejected |
| `incomplete.pdf` | a page could not be read; analysis blocked |
| `verified.pdf` | one verified finding, one withheld |
| `withheld.pdf` | nothing verified; two withheld |
| `interpretation.pdf` | verified claim, unverified explanation |
| `provider-failure.pdf` | the analysis and Q&A both fail |
| `qa-failure.pdf` | the analysis succeeds; only Q&A fails |
| `qa-recovers.pdf` | the analysis succeeds; Q&A fails once, then answers |
| any, asking about governing law | unsupported answer |

## What each test asserts

1. **Upload failure** — a `role="alert"` carries the backend's message, the
   upload panel stays, and no analysis control appears.
2. **Incomplete document** — coverage status, counts, explanation and the
   unreadable page number are all shown, and **no "Analyse this document"
   button is rendered at all**. The block is structural, not a warning to click
   past.
3. **Verified finding** — claim, badge, evidence quote, page, and the footer
   stating that verified means the quote was found on the page, *not* that the
   clause is fair, enforceable or complete.
4. **Withheld finding** — nothing rendered as a finding; the withholding is
   counted by reason and explicitly does not claim the document is risk-free.
5. **Unsupported Q&A** — the fallback, the withheld-quote count and the
   per-answer disclaimer.
6. **Provider failure** — progress marks Analysis stopped and Results not
   available, an alert carries the safe message, and no finding or answer text
   is rendered. Asking a question in the same state fails the same way.
7. **Unverified explanation** — the claim carries the verified badge and the
   explanation below it is labelled *Interpretation — not verified against the
   document*. This is the presentational half of the Phase 15 finding that the
   verifier cannot reliably judge explanation prose
   (`PHASE_15_REPORT.md` sec. 7).

Flows 8–11 cover the deterministic value index, 12–16 the four analysis states
and the manual retry, and 17–21 the Phase 19 separation between a failed
question and a completed analysis: that a question failure is reported inside
the Q&A panel in its own words, that the findings and values above it do not
move, that asking again clears only the question's error, and that two
simultaneous failures each still speak only for themselves.

Flows 22–27 cover the Phase 21 document overview. Two properties, since the
overview publishes nothing of its own: that every quote in it also appears in
a finding card (25), and that an empty topic reports what the
analysis released rather than what the document contains (23) — asserted by
checking that the words *missing*, *not present*, *not included*, *absent* and
*deficient* appear nowhere in the panel. The rest check that no risk badge or
obligation-ownership wording is rendered (22), that a result with nothing
released still produces a safe empty overview (24), that no overview appears
before an analysis or after one stops (26), and that a failed question leaves
it standing (27).

Flows 28–34 cover the LexGuard workspace introduced by the frontend redesign:
the header reports the document and the backend's own coverage and analysis
states (28); the evidence inspector shows the finding's quote, page and
backend verdict, and its "Why this status?" text names the check that ran
(29); inspecting a finding from the overview opens that finding (30); the tabs
work from the keyboard (31); discarding returns to the upload screen (32); a
refused replacement upload leaves the current document untouched and an
accepted one starts again from the beginning (33); and at 390 px the evidence
opens in a sheet carrying the same verdict and quote (34).

### Tabs, and what a negative assertion proves

The workspace is tabbed and an inactive panel is `hidden`, which takes it out
of the accessibility tree. So a flow that asserts something *is* shown opens
its tab first, and a flow that asserts something is *not* shown by role
(`getByRole('article')` with a count of 0, say) makes that assertion on the tab
where it would appear. Made on any other tab it would pass because the panel is
hidden, not because the thing is absent. Text lookups see hidden panels too,
so a phrase that must appear nowhere is checked without opening a tab.

## Status

All thirty-four pass. `npm run test:e2e` is a committed suite, not a manual
procedure — but note that **no CI service runs it**, because this repository
has no CI configuration at all. Adding one is a deployment decision rather than
a testing gap, and `PHASE_15_REPORT.md` sec. 9 says so rather than describing
this as continuous coverage.
