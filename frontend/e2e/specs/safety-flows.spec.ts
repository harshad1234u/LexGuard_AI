import { expect, test, type Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

import { BRAND } from '../../src/config/brand'

/**
 * The safety-critical browser flows.
 *
 * What these assert is narrow and deliberate: that the browser shows the user
 * what the backend decided, and never something friendlier. They are not a
 * test of verification - that is the Python suite's job - they are a test of
 * the last few inches between a release decision and a person's eyes.
 *
 * The workspace is tabbed, and an inactive tab's panel is `hidden`, which
 * removes it from the accessibility tree. Two rules follow, and every flow
 * below keeps them:
 *
 *   - An assertion that something IS shown opens the tab it belongs to first.
 *   - An assertion that something is NOT shown by role (`getByRole(...)
 *     .toHaveCount(0)`) is made on the tab where that thing would appear.
 *     Made anywhere else it would pass because the panel is hidden, not
 *     because the thing is absent - a test that cannot fail.
 *
 * Text lookups (`getByText`) see hidden panels too, so a text that must not
 * appear anywhere is checked without opening a tab.
 */

const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures')

type Tab = 'Overview' | 'Findings & Clauses' | 'Values & Dates' | 'Ask Document'

/**
 * The upload input is `sr-only` inside a label, and a native file chooser is
 * awkward to drive reliably. Setting the input directly is what a user's click
 * ends up doing anyway.
 */
async function upload(page: Page, filename: string) {
  await page.setInputFiles('input[type=file]', resolve(FIXTURES, filename))
}

async function readDocument(page: Page) {
  await page.getByRole('button', { name: 'Read the document' }).click()
}

async function analyse(page: Page) {
  await page.getByRole('button', { name: 'Analyse this document' }).click()
}

async function openTab(page: Page, name: Tab) {
  const tab = page.getByRole('tab', { name })
  await tab.click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
}

const findingsTab = (page: Page) => openTab(page, 'Findings & Clauses')

const valuesPanel = (page: Page) => page.getByRole('region', { name: 'Values & Dates' })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('banner')).toContainText(BRAND.name)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(BRAND.tagline)
})

test('1. an invalid upload is refused and no analysis starts', async ({ page }) => {
  await upload(page, 'notes.txt')

  await expect(page.getByRole('alert')).toContainText('not a PDF')
  // Still on the upload screen: no workspace, nothing to analyse.
  await expect(page.getByRole('button', { name: 'Analyse this document' })).toHaveCount(0)
  await expect(page.getByRole('tablist')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Upload a legal document' })).toBeVisible()
})

test('2. an incomplete document blocks analysis and says why', async ({ page }) => {
  await upload(page, 'incomplete.pdf')
  await readDocument(page)

  await expect(page.getByText('Coverage: Incomplete')).toBeVisible()
  await expect(page.getByText('2 of 3 pages processed')).toBeVisible()
  await expect(page.getByText(/Pages with no readable text: 3/)).toBeVisible()

  // The block is structural: the button is not rendered at all, so there is
  // nothing for a user to click past.
  await expect(page.getByRole('button', { name: 'Analyse this document' })).toHaveCount(0)
  await expect(page.getByText(/Verified against document evidence/)).toHaveCount(0)

  // The findings view says the same thing, and offers no way round it.
  await findingsTab(page)
  await expect(page.getByText('Analysis is blocked for this document')).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(0)
})

test('3. a verified finding shows its evidence and claims no legal advice', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)
  await findingsTab(page)

  const finding = page.getByRole('article').first()
  await expect(finding).toContainText('Verified against document evidence')
  await expect(finding).toContainText("30 days' written notice")

  // The evidence is never collapsed: quote, page and section sit with the claim.
  await expect(finding.locator('blockquote')).toContainText('Either party may terminate')
  await expect(finding).toContainText('Page 2')

  await expect(page.getByText(/Verified means the quoted text was found on the cited page/))
    .toBeVisible()
  await expect(
    page.getByText(/not a substitute for advice from a qualified legal professional/),
  ).toBeVisible()
})

test('4. a withheld finding is never shown as verified', async ({ page }) => {
  await upload(page, 'withheld.pdf')
  await readDocument(page)
  await analyse(page)
  await findingsTab(page)

  await expect(page.getByText(/No verified findings could be established/)).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(0)

  // The withholding is reported by reason, and does not claim the document is safe.
  await expect(page.getByText('2 statements were withheld')).toBeVisible()
  await expect(page.getByText('1 contradicted by the document')).toBeVisible()
  await expect(page.getByText(/does not mean the document carries no risk/)).toBeVisible()
})

test('5. an unsupported question falls back and keeps the disclaimer', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await openTab(page, 'Ask Document')

  await page
    .getByRole('textbox', { name: /question/i })
    .fill("Which country's governing law applies?")
  await page.getByRole('button', { name: 'Ask', exact: true }).click()

  await expect(page.getByText(/Couldn't confirm this from the document/)).toBeVisible()
  await expect(page.getByText(/only that nothing could be confirmed/)).toBeVisible()
  await expect(page.getByText(/not legal advice/)).toBeVisible()
})

test('6. a provider failure shows a safe error and fabricates nothing', async ({ page }) => {
  await upload(page, 'provider-failure.pdf')
  await readDocument(page)
  await analyse(page)

  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')
  await expect(page.getByText('Analysis stopped')).toBeVisible()
  await expect(page.getByText('Not available')).toBeVisible()

  await findingsTab(page)
  await expect(page.getByRole('article')).toHaveCount(0)

  // Asking a question in the same state fails the same way.
  await openTab(page, 'Ask Document')
  await page.getByRole('textbox', { name: /question/i }).fill('What is the notice period?')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  await expect(page.getByRole('alert').last()).toContainText('temporarily unavailable')
  await expect(page.getByText(/30 days/)).toHaveCount(0)
})

test('7. an unverified explanation is labelled as interpretation', async ({ page }) => {
  await upload(page, 'interpretation.pdf')
  await readDocument(page)
  await analyse(page)
  await findingsTab(page)

  const finding = page.getByRole('article').first()
  await expect(finding).toContainText('Verified against document evidence')
  // The claim is verified; the explanation beneath it is not, and says so.
  await expect(finding).toContainText('Interpretation — not verified against the document')
})

test('8. extracted values are shown with page references and no surrounding prose', async ({
  page,
}) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await openTab(page, 'Values & Dates')

  const values = valuesPanel(page)
  await expect(values).toBeVisible()
  // The panel states what it is not, on the panel itself.
  await expect(values).toContainText('not a summary and not a risk assessment')

  // Grouped by what the value is, never by what it might mean.
  await expect(values.getByRole('heading', { name: 'Amounts' })).toBeVisible()
  await expect(values.getByRole('heading', { name: 'Time periods' })).toBeVisible()

  // Every value carries the page it was found on.
  await expect(values.getByText('Rs 50,000')).toBeVisible()
  await expect(values.getByText('Page 2').first()).toBeVisible()

  // An ambiguous date is reported as written and flagged, never resolved.
  await expect(values.getByText('04/05/2026')).toBeVisible()
  await expect(values.getByText('Date format unclear')).toBeVisible()

  // The index must not become a claim surface: no sentence from the document,
  // and none of the interpretive vocabulary this panel is forbidden to use.
  await expect(values).not.toContainText('shall pay')
  await expect(values).not.toContainText('Obligation')
  await expect(values).not.toContainText('Risk')
  await expect(values).not.toContainText('Deadline')
})

test('9. a document with no detectable values says so plainly', async ({ page }) => {
  await upload(page, 'novalues.pdf')
  await readDocument(page)
  await openTab(page, 'Values & Dates')

  const values = valuesPanel(page)
  await expect(values).toContainText('No supported values were detected in the extracted text.')

  // The document was read. Suggesting it might be scanned would be a guess,
  // and a reader acting on it would go looking for a problem that is not there.
  await expect(values).not.toContainText('scanned')
  await expect(values).not.toContainText('No readable text')
})

test('11. a document whose text could not be read is not called value-free', async ({
  page,
}) => {
  await upload(page, 'notext.pdf')
  await readDocument(page)
  await openTab(page, 'Values & Dates')

  const values = valuesPanel(page)

  // The failure this distinction exists to prevent: an unread document
  // reported as one that contains nothing. Same coverage, same empty list,
  // and the opposite meaning.
  await expect(values).toContainText('No readable text was extracted from this document.')
  await expect(values).toContainText('scanned')
  await expect(values).not.toContainText('No supported values were detected')
})

test('10. values remain available when the model provider has failed', async ({ page }) => {
  await upload(page, 'provider-failure.pdf')
  await readDocument(page)
  await analyse(page)

  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')

  // No findings, because the model never answered - but the document's own
  // values are still there, because reading them never needed the model.
  await findingsTab(page)
  await expect(page.getByRole('article')).toHaveCount(0)
  await openTab(page, 'Values & Dates')
  await expect(valuesPanel(page).getByText('Rs 50,000')).toBeVisible()
})


/**
 * Phase 18B: the four analysis states a user can land in.
 *
 * These are about what the screen says happened, not about verification -
 * the Python suite owns that. The distinction they protect is that a provider
 * failure is a failure of the *analysis*, not of the document, and that a
 * retry which succeeds leaves nothing of the failure behind.
 */

test('12. a successful analysis reaches results', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)

  await expect(page.getByText('Analysis complete')).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)

  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('13. a provider failure stops the analysis without blaming the document', async ({
  page,
}) => {
  await upload(page, 'provider-failure.pdf')
  await readDocument(page)
  await analyse(page)

  const alert = page.getByRole('alert')
  await expect(alert).toContainText('temporarily unavailable')

  // The document is not the thing that failed, and the user must not be left
  // thinking it was - they would re-upload a perfectly good file.
  await expect(alert).toContainText('Your document was read in full')
  await expect(alert).toContainText('No analysis results were released')

  // The progress view still shows where it stopped.
  await expect(page.getByText('Analysis stopped')).toBeVisible()
  await expect(page.getByText('Not available')).toBeVisible()

  // Raw provider internals never reach the screen.
  await expect(alert).not.toContainText('ResourceExhausted')
  await expect(alert).not.toContainText('Traceback')

  // Nothing was released.
  await findingsTab(page)
  await expect(page.getByRole('article')).toHaveCount(0)
})

test('14. a manual retry after a provider failure reaches results', async ({ page }) => {
  await upload(page, 'recovers.pdf')
  await readDocument(page)

  // First attempt: the provider is down.
  await analyse(page)
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')

  // The button now offers the retry, and the retry is the user's own action.
  const retry = page.getByRole('button', { name: 'Try the analysis again' })
  await expect(retry).toBeVisible()
  await retry.click()

  // Second attempt succeeds: results appear and the stale error is gone.
  await expect(page.getByText('Analysis complete')).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()
})

test('15. a retry that fails again still releases nothing', async ({ page }) => {
  await upload(page, 'provider-failure.pdf')
  await readDocument(page)

  await analyse(page)
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')

  await page.getByRole('button', { name: 'Try the analysis again' }).click()

  // Same honest failure, and still no findings invented to fill the gap.
  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')
  await expect(page.getByText('Not available')).toBeVisible()
  await findingsTab(page)
  await expect(page.getByRole('article')).toHaveCount(0)
})

test('16. questions stay available while the analysis has stopped', async ({ page }) => {
  await upload(page, 'provider-failure.pdf')
  await readDocument(page)
  await analyse(page)

  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')

  // Q&A is independently grounded in the document, so a failed analysis does
  // not take it offline - and the question box is still offered.
  await openTab(page, 'Ask Document')
  await expect(page.getByRole('heading', { name: 'Ask your document' })).toBeVisible()
  await expect(page.getByRole('textbox', { name: /question/i })).toBeEnabled()
})


/**
 * Phase 19: a question that fails, beside an analysis that did not.
 *
 * The screenshot that opened this phase showed a completed analysis, five
 * withheld statements, and underneath them the sentence "The analysis service
 * is temporarily unavailable." Only the question had failed. These flows are
 * about which of the two things in the workspace a failure is allowed to speak
 * for, and about what must still be there afterwards.
 */

const askPanel = (page: Page) => page.getByRole('region', { name: 'Ask your document' })

async function askAbout(page: Page, question: string) {
  await openTab(page, 'Ask Document')
  await page.getByRole('textbox', { name: /question/i }).fill(question)
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
}

test('17. a question answered beside a completed analysis shows both', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)
  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()

  await askAbout(page, 'What is the termination notice period?')

  const ask = askPanel(page)
  await expect(ask).toContainText('Answered from the document')
  await expect(ask.locator('blockquote')).toContainText('30 days')
  await expect(page.getByRole('alert')).toHaveCount(0)

  // The analysis is still the analysis.
  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('18. a question the document does not answer is not shown as a failure', async ({
  page,
}) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)
  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()

  await askAbout(page, "Which country's governing law applies?")

  // The backend's own not-found wording, in the answer's own tone - a verdict
  // about the document, not a red service failure.
  await expect(askPanel(page)).toContainText(/Couldn't confirm this from the document/)
  await expect(page.getByRole('alert')).toHaveCount(0)

  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()
})

test('19. a failed question does not report the completed analysis as failed', async ({
  page,
}) => {
  await upload(page, 'qa-failure.pdf')
  await readDocument(page)
  await analyse(page)
  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()

  await askAbout(page, 'What is the termination notice period?')

  const alert = askPanel(page).getByRole('alert')
  await expect(alert).toContainText('Question not answered')
  await expect(alert).toContainText('question service is temporarily unavailable')
  await expect(alert).toContainText('No answer was generated or shown')

  // The sentence that caused this phase. It named the wrong feature.
  await expect(alert).not.toContainText('analysis service')
  await expect(alert).not.toContainText('ResourceExhausted')

  // And the analysis it wrongly spoke for is still there, unchanged.
  await expect(alert).toContainText('Your document analysis is unaffected')
  await expect(page.getByText('Analysis stopped')).toHaveCount(0)
  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()
  await openTab(page, 'Values & Dates')
  await expect(valuesPanel(page).getByText('Rs 50,000')).toBeVisible()
})

test('20. asking again clears the question error and leaves the analysis alone', async ({
  page,
}) => {
  await upload(page, 'qa-recovers.pdf')
  await readDocument(page)
  await analyse(page)
  await findingsTab(page)
  const finding = page.getByRole('article').first()
  await expect(finding).toBeVisible()

  await askAbout(page, 'What is the termination notice period?')
  await expect(askPanel(page).getByRole('alert')).toContainText('Question not answered')

  // The retry is the user's own action, and it is only the question. Nothing
  // re-runs the analysis, and the finding never leaves the workspace.
  await askAbout(page, 'What is the termination notice period?')

  await expect(askPanel(page).getByRole('alert')).toHaveCount(0)
  await expect(askPanel(page)).toContainText('Answered from the document')
  await findingsTab(page)
  await expect(finding).toBeVisible()
})

test('21. a failed analysis and a failed question each report themselves', async ({
  page,
}) => {
  await upload(page, 'provider-failure.pdf')
  await readDocument(page)
  await analyse(page)

  // The existing analysis-failure state, unchanged by this phase.
  await expect(page.getByText('Analysis stopped')).toBeVisible()
  await expect(page.getByText('Not available')).toBeVisible()

  await askAbout(page, 'What is the notice period?')

  // Two failures, two alerts, each about its own feature - and neither
  // borrowing the other's wording.
  const qa = askPanel(page).getByRole('alert')
  await expect(qa).toContainText('question service is temporarily unavailable')
  await expect(qa).not.toContainText('analysis service')
  // No analysis completed here, so the panel does not claim one did.
  await expect(qa).not.toContainText('Your document analysis is unaffected')

  await openTab(page, 'Overview')
  await expect(page.getByText('Analysis stopped')).toBeVisible()
  await findingsTab(page)
  await expect(page.getByRole('article')).toHaveCount(0)
})


/**
 * Phase 21: the document overview.
 *
 * The overview is a projection of findings that already passed the output
 * gate, so these flows are not about whether it is correct about the document
 * — the Python suite owns that. They are about the two things a browser can
 * get wrong with it: publishing something the gate did not, and letting an
 * empty topic read as a statement about the contract.
 */

const overviewPanel = (page: Page) =>
  page.getByRole('region', { name: 'Verified findings by topic' })

test('22. the overview groups released findings and claims nothing more', async ({
  page,
}) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)

  const overview = overviewPanel(page)
  await expect(overview).toBeVisible()

  // The released finding, under its topic, with its evidence and page.
  const termination = overview.locator('section', {
    has: page.getByRole('heading', { name: 'Termination', exact: true }),
  })
  await expect(termination).toContainText('30 days')
  await expect(termination.locator('blockquote')).toContainText('Either party may terminate')
  await expect(termination).toContainText('Page 2')

  // It says what it is not, on the panel itself.
  await expect(overview).toContainText('not a legal assessment')
  await expect(overview).toContainText('not a complete summary')

  // No assessment layer: no risk badge, no attention level, no ownership.
  await expect(overview).not.toContainText('high')
  await expect(overview).not.toContainText('Risk')
  await expect(overview).not.toContainText('Your obligations')
  await expect(overview).not.toContainText('obligation')
})

test('23. an empty topic reports the analysis, never the document', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)

  const overview = overviewPanel(page)

  // Topics nothing was released for are still shown — a reader should see
  // what was not established — but only ever in these words.
  await expect(
    overview.getByText('No verified finding was released for this category.').first(),
  ).toBeVisible()

  // The words that would turn "we released nothing" into "the contract lacks it".
  for (const word of ['Missing', 'Not present', 'Not included', 'Absent', 'Deficient']) {
    await expect(overview).not.toContainText(word)
  }

  // And the sentence that makes the distinction explicit.
  await expect(overview).toContainText('not that the document does not cover it')
})

test('24. nothing released means an overview with nothing in it', async ({ page }) => {
  await upload(page, 'withheld.pdf')
  await readDocument(page)
  await analyse(page)

  const overview = overviewPanel(page)
  await expect(overview).toBeVisible()

  // Every topic empty, the withheld count stated, and none of the two
  // withheld statements' content anywhere on the page.
  await expect(overview).toContainText('0 of 2 statements released')
  await expect(overview).toContainText('2 of 2 statements the model proposed were withheld')
  await expect(overview.locator('blockquote')).toHaveCount(0)
  await findingsTab(page)
  await expect(page.getByRole('article')).toHaveCount(0)
})

test('25. the overview never publishes what the findings list does not', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)

  // Every quote in the overview must also appear in a finding card.
  const overviewQuotes = await overviewPanel(page).locator('blockquote').allInnerTexts()
  expect(overviewQuotes.length).toBeGreaterThan(0)

  await findingsTab(page)
  await expect(page.getByRole('article').first()).toBeVisible()
  const findingQuotes = await page.getByRole('article').locator('blockquote').allInnerTexts()
  for (const quote of overviewQuotes) {
    expect(findingQuotes).toContain(quote)
  }
})

test('26. no overview before an analysis, and none when the analysis stops', async ({
  page,
}) => {
  await upload(page, 'provider-failure.pdf')
  await readDocument(page)

  // Extracted, not analysed: there is nothing released to group.
  await expect(overviewPanel(page)).toHaveCount(0)
  // Values do not need the model, and are there as before.
  await openTab(page, 'Values & Dates')
  await expect(valuesPanel(page)).toBeVisible()

  await openTab(page, 'Overview')
  await analyse(page)
  await expect(page.getByText('Analysis stopped')).toBeVisible()

  // A stopped analysis released nothing, so the panel stays absent rather than
  // rendering an empty structure that looks like a result.
  await expect(overviewPanel(page)).toHaveCount(0)
})

test('27. the overview survives a failed question', async ({ page }) => {
  await upload(page, 'qa-failure.pdf')
  await readDocument(page)
  await analyse(page)
  await expect(overviewPanel(page)).toBeVisible()

  await askAbout(page, 'What is the termination notice period?')
  await expect(askPanel(page).getByRole('alert')).toContainText('Question not answered')

  // Phase 19's isolation, extended to the overview.
  await openTab(page, 'Overview')
  await expect(overviewPanel(page)).toBeVisible()
  await expect(overviewPanel(page).locator('blockquote').first()).toBeVisible()
})


/**
 * The LexGuard workspace.
 *
 * The redesign moved the same backend states into a header, four tabs and an
 * evidence inspector. These flows check that the new surfaces report those
 * states and nothing else, and that they can be operated without a mouse.
 */

test('28. the header reports the document and the backend statuses', async ({ page }) => {
  await upload(page, 'verified.pdf')

  const header = page.getByRole('banner')
  await expect(header).toContainText('verified.pdf')
  await expect(header).toContainText('Not yet extracted')
  await expect(header).toContainText('Not read yet')

  await readDocument(page)
  await expect(header).toContainText('Complete')
  await expect(header).toContainText('Ready to analyse')

  await analyse(page)
  await expect(header).toContainText('Results ready')
  // The findings tab counts what was released, and nothing before that.
  await expect(page.getByRole('tab', { name: 'Findings & Clauses' })).toContainText('1')
})

test('29. the evidence inspector shows the backend verdict, quote and page', async ({
  page,
}) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)
  await findingsTab(page)

  const inspector = page.getByRole('region', { name: 'Evidence inspector' })
  await expect(inspector).toContainText('Exact quotation from the uploaded document.')
  await expect(inspector.locator('blockquote')).toContainText('Either party may terminate')
  await expect(inspector).toContainText('Verified against document evidence')

  // The reason is available on request, and names the check that was run.
  await inspector.getByText('Why this status?').click()
  await expect(inspector).toContainText('found on the cited page')
})

test('30. inspecting a finding from the overview opens that finding', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await analyse(page)

  await overviewPanel(page).getByRole('button', { name: 'Inspect evidence' }).first().click()

  await expect(page.getByRole('tab', { name: 'Findings & Clauses' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(
    page.getByRole('region', { name: 'Evidence inspector' }).locator('blockquote'),
  ).toContainText('Either party may terminate')
})

test('31. the workspace tabs are keyboard operable', async ({ page }) => {
  await upload(page, 'verified.pdf')

  const overview = page.getByRole('tab', { name: 'Overview' })
  await overview.focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Findings & Clauses' })).toBeFocused()
  await expect(page.getByRole('tab', { name: 'Findings & Clauses' })).toHaveAttribute(
    'aria-selected',
    'true',
  )

  await page.keyboard.press('End')
  await expect(page.getByRole('tab', { name: 'Ask Document' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await page.keyboard.press('Home')
  await expect(overview).toHaveAttribute('aria-selected', 'true')
})

test('32. discarding a document returns to the upload screen', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)
  await expect(page.getByText('Coverage: Complete')).toBeVisible()

  await page.getByRole('button', { name: 'Discard document' }).click()

  await expect(page.getByRole('heading', { name: 'Upload a legal document' })).toBeVisible()
  await expect(page.getByRole('tablist')).toHaveCount(0)
  await expect(page.getByRole('banner')).not.toContainText('verified.pdf')
})

test('33. a refused replacement leaves the current document in place', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await readDocument(page)

  // The header's upload control is the only file input in the workspace.
  await upload(page, 'notes.txt')

  const alert = page.getByRole('alert')
  await expect(alert).toContainText('The new document could not be uploaded')
  await expect(alert).toContainText('not a PDF')
  await expect(alert).toContainText('Your current document is unchanged')
  await expect(page.getByRole('banner')).toContainText('verified.pdf')
  await expect(page.getByText('Coverage: Complete')).toBeVisible()

  // An accepted replacement starts the new document from the beginning.
  await upload(page, 'withheld.pdf')
  await expect(page.getByRole('banner')).toContainText('withheld.pdf')
  await expect(page.getByRole('banner')).not.toContainText('verified.pdf')
  await expect(page.getByRole('button', { name: 'Read the document' })).toBeVisible()
})

test.describe('on a phone-sized screen', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('34. evidence opens in a sheet, with the same verdict and quote', async ({ page }) => {
    await upload(page, 'verified.pdf')
    await readDocument(page)
    await analyse(page)
    await findingsTab(page)

    // No side inspector at this width: the card carries the evidence itself.
    await expect(page.getByRole('region', { name: 'Evidence inspector' })).toHaveCount(0)
    const finding = page.getByRole('article').first()
    await expect(finding).toContainText('Verified against document evidence')
    await expect(finding.locator('blockquote')).toContainText('Either party may terminate')

    await finding.getByRole('button', { name: 'Inspect evidence' }).click()
    const sheet = page.getByRole('dialog', { name: 'Evidence inspector' })
    await expect(sheet).toBeVisible()
    await expect(sheet.locator('blockquote')).toContainText('Either party may terminate')
    await expect(sheet).toContainText('Verified against document evidence')

    await page.keyboard.press('Escape')
    await expect(sheet).toBeHidden()
  })
})
