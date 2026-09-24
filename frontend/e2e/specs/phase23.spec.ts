import { expect, test, type Page } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

import { BRAND } from '../../src/config/brand'

/**
 * Phase 23 browser flows: provenance, reasoning notes, translations, and the
 * provider-not-configured state.
 *
 * The same rules as safety-flows.spec.ts: open a tab before asserting that
 * something is shown on it, and make role-based absence checks on the tab
 * where the thing would appear.
 */

const FIXTURES = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures')
const NOTE_LABEL = 'Reasoning note — not independently verified'
const TAMIL_EXPLANATION = 'இரு தரப்பினரும் 30 நாட்கள் எழுத்துமூல அறிவிப்புடன் ஒப்பந்தத்தை முடிக்கலாம்.'
const TAMIL_ANSWER = 'இரு தரப்பினரும் 30 நாட்கள் எழுத்துமூல அறிவிப்புடன் முடிக்கலாம்.'
const QUOTE = "Either party may terminate this agreement by providing 30 days' written notice."

async function upload(page: Page, filename: string) {
  await page.setInputFiles('input[type=file]', resolve(FIXTURES, filename))
}

async function readAndAnalyse(page: Page) {
  await page.getByRole('button', { name: 'Read the document' }).click()
  await page.getByRole('button', { name: 'Analyse this document' }).click()
}

async function openTab(page: Page, name: string) {
  const tab = page.getByRole('tab', { name })
  await tab.click()
  await expect(tab).toHaveAttribute('aria-selected', 'true')
}

const notesRegion = (page: Page) => page.getByRole('region', { name: 'Reasoning notes' })

test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('banner')).toContainText(BRAND.name)
})

test('35. provenance says who analysed, who reasoned, and who verified', async ({ page }) => {
  await upload(page, 'reasoning.pdf')
  await readAndAnalyse(page)
  await openTab(page, 'Findings & Clauses')

  const strip = page.getByLabel('How this analysis was produced')
  await expect(strip).toContainText('Analysis: Gemini')
  await expect(strip).toContainText('Reasoning notes: Nemotron')
  await expect(strip).toContainText('Verification: application-controlled')
  // No model verifies its own output, so nothing may say it did.
  await expect(page.getByText(/AI[- ]verified/i)).toHaveCount(0)
})

test('36. a reasoning note is labelled, carries no verified badge, and is not a finding', async ({
  page,
}) => {
  await upload(page, 'reasoning.pdf')
  await readAndAnalyse(page)
  await openTab(page, 'Findings & Clauses')

  const notes = notesRegion(page)
  await expect(notes).toBeVisible()
  await expect(notes.getByText(NOTE_LABEL)).toBeVisible()
  await expect(notes).toContainText('fees may continue to fall due')
  await expect(notes).toContainText("The note’s conclusion was not checked")
  await expect(notes).toContainText('1 note was withheld')
  // The note is not a finding: two finding cards, no more.
  await expect(page.getByRole('article')).toHaveCount(2)
  // And no verification badge inside the notes.
  await expect(notes.getByText(/^Verified$/)).toHaveCount(0)
})

test('37. a note links to the findings it relates, via the keyboard', async ({ page }) => {
  await upload(page, 'reasoning.pdf')
  await readAndAnalyse(page)
  await openTab(page, 'Findings & Clauses')

  const link = notesRegion(page).getByRole('button', { name: 'f_002' })
  await link.focus()
  await expect(link).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.locator('#evidence-inspector')).toContainText('GBP 5,000 per month')
})

test('38. a failed reasoning stage leaves the released findings in place', async ({ page }) => {
  await upload(page, 'reasoning-failed.pdf')
  await readAndAnalyse(page)
  await openTab(page, 'Findings & Clauses')

  await expect(page.getByRole('article')).toHaveCount(2)
  await expect(notesRegion(page)).toContainText('Reasoning notes could not be produced this time')
  await expect(notesRegion(page)).toContainText('The findings above are unaffected')
})

test('39. a Tamil analysis sends the language and labels the translation', async ({ page }) => {
  await upload(page, 'tamil.pdf')
  await page.getByRole('button', { name: 'Read the document' }).click()
  await page.getByLabel('Explanation language').selectOption('ta')

  const sent = page.waitForRequest((r) => r.url().includes('/analyze') && r.method() === 'POST')
  await page.getByRole('button', { name: 'Analyse this document' }).click()
  expect(JSON.parse((await sent).postData() ?? '{}')).toEqual({ language: 'ta' })

  await openTab(page, 'Findings & Clauses')
  const card = page.getByRole('article').first()
  await expect(card.getByText('Translation (தமிழ்) — not independently checked')).toBeVisible()
  await expect(card.getByText(TAMIL_EXPLANATION)).toBeVisible()
  // The quote is the document's own English, untouched.
  await expect(card).toContainText(QUOTE)
})

test('40. an English analysis sends no body at all', async ({ page }) => {
  await upload(page, 'verified.pdf')
  await page.getByRole('button', { name: 'Read the document' }).click()
  const sent = page.waitForRequest((r) => r.url().includes('/analyze') && r.method() === 'POST')
  await page.getByRole('button', { name: 'Analyse this document' }).click()
  expect((await sent).postData()).toBeNull()
})

test('41. a Tamil question gets a labelled translation beside the checked answer', async ({
  page,
}) => {
  await upload(page, 'verified.pdf')
  await readAndAnalyse(page)
  await openTab(page, 'Ask Document')

  await page.getByLabel('Answer language').selectOption('ta')
  await page.getByLabel('Your question about this document').fill('எப்படி முடிக்கலாம்?')
  const sent = page.waitForRequest((r) => r.url().includes('/ask'))
  await page.getByRole('button', { name: 'Ask', exact: true }).click()
  expect(JSON.parse((await sent).postData() ?? '{}').language).toBe('ta')

  const answer = page.getByRole('region', { name: 'Answer' })
  await expect(answer.getByText('Translation (தமிழ்) — not independently checked')).toBeVisible()
  await expect(answer.getByText(TAMIL_ANSWER)).toBeVisible()
  await expect(answer).toContainText('Verification: application-controlled')
  await expect(answer).toContainText(QUOTE)
})

test('42. a missing analysis key is a clear stop, not a silent fallback', async ({ page }) => {
  await upload(page, 'gemini-missing.pdf')
  await readAndAnalyse(page)

  await expect(page.getByText('the service is not configured')).toBeVisible()
  await openTab(page, 'Findings & Clauses')
  await expect(page.getByRole('article')).toHaveCount(0)
})

for (const width of [390, 768, 1280, 1440]) {
  test(`43. reasoning notes fit at ${width}px without horizontal scrolling`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await upload(page, 'reasoning.pdf')
    await readAndAnalyse(page)
    await openTab(page, 'Findings & Clauses')

    await expect(notesRegion(page).getByText(NOTE_LABEL)).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
}
