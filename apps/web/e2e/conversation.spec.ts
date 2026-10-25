import { expect, test, type Locator, type Page } from '@playwright/test'
import {
  announcements,
  ask,
  askAndWaitForAnswer,
  askButton,
  assistantMessage,
  assistantMessages,
  BUDGET_DAILY_TEXT,
  BUDGET_SANDBOX_TEXT,
  composerBox,
  composerLine,
  countTurnRequests,
  currentConversation,
  focusPageStart,
  PERSONAL_DATA_TEXT,
  panels,
  QUESTIONS,
  statusLog,
  STILL_ANSWERING_TEXT,
  stopButton,
  stubConversation,
  tabStops,
  userMessages,
  waitForTurnSaved,
  watchAnnouncements,
  watchStatusLines,
} from './conversation-helpers'
import {
  holdNextTurnStream,
  pushSearchSteps,
  SICK_LEAVE_CITATION,
  SICK_LEAVE_SENTENCE,
} from './held-stream'
import { greetingHeading, problem, scan, startAs, switchTo, themeColor } from './helpers'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// One test per acceptance criterion of docs/design/screens/07-conversation/notes.md (the table in
// docs/plans/2026-10-14-phase-4-assistant-core.md, "Self-review: acceptance criteria to tasks"),
// each with an axe scan of the state it shows, plus the Phase 4 demo steps. The page is the real
// one, against the real API with the scripted model, so no question costs anything.
//
// Not tests here, and where each is proved instead:
//  - "Every state matches its screenshot at 1440 px": the capture report (make captures).
//  - "Usable at 390 px ... nothing scrolling sideways", the 85% and two-row rules, and the docked
//    panel's size: conversation-layout.spec.ts.
//  - "Answers render the Markdown subset as React elements. Raw HTML and bare URLs show as text":
//    the scripted model never writes any, so the renderer's own unit tests (answer.test.tsx) prove
//    it, and the source holds no dangerouslySetInnerHTML.
//  - "Markers appear while text streams. Chips and feedback appear only after the answer
//    finishes": the scripted answer streams in milliseconds, so the unit tests of the message and
//    the store prove the timing. Here the streaming state shows no chips and no feedback.
//  - The per-state axe scans of the gallery's frames: gallery-conversation.spec.ts.
//
// STUB tests are named so. They answer the conversation's GET with the real response after
// changing a field, for the states the scripted model can't reach (a budget stop, a long
// conversation). Nothing else is faked.

const assistantLabel = (message: Locator) => message.getByText('AI', { exact: true })

/** Every assistant message starts with the "AI" label and "Open Door", has no bubble, and is at most 680 px. */
async function expectAssistantChrome(message: Locator) {
  await expect(assistantLabel(message)).toBeVisible()
  await expect(message.getByText('Open Door', { exact: true })).toBeVisible()
  await expect(message).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await expect(message).toHaveCSS('border-top-width', '0px')
  await expect.poll(async () => (await message.boundingBox())?.width ?? 0).toBeLessThanOrEqual(680)
}

async function expectNoViolations(page: Page) {
  expect((await scan(page)).violations).toEqual([])
}

test.describe('the demo steps', () => {
  // The scripted model cites a state addendum when its search returns one (and otherwise the first
  // result), so the two people are cited different sections for the same question: Priya, in
  // Oakland, CA-4.3, and Mateo, in Austin, whose search never returns it, §4.3.
  test('Priya and Mateo ask about sick leave and are cited different sections: CA-4.3 for Priya, §4.3 for Mateo', async ({
    browser,
  }) => {
    const retrieved: Record<string, string> = {}
    for (const [name, chip, marker] of [
      [
        'Priya',
        'Handbook CA-4.3 · California addendum',
        'Source 1: Handbook CA-4.3, California addendum',
      ],
      ['Mateo', 'Handbook §4.3 · Time off', 'Source 1: Handbook §4.3, Time off'],
    ] as const) {
      const context = await browser.newContext()
      try {
        const page = await context.newPage()
        await startAs(page, name)
        // Full-text search (the browser tests have no embeddings) ranks the addendum fourth for this
        // question; for the bare "sick leave" the handbook's 2026.11.1 sick-leave paragraphs push it
        // out of the five results.
        await askAndWaitForAnswer(page, 'how much sick leave do I get')
        const answer = assistantMessage(page)
        await expectAssistantChrome(answer)
        await expect(answer.getByRole('list', { name: 'Sources' })).toContainText(chip)
        await expect(answer.locator('[data-slot="citation-marker"]').first()).toHaveAccessibleName(
          marker,
        )
        await page.getByRole('button', { name: 'Show your work' }).click()
        retrieved[name] = (
          await page.getByRole('list', { name: 'Sections retrieved' }).innerText()
        ).trim()
        await expectNoViolations(page)
      } finally {
        await context.close()
      }
    }
    // What each search retrieved differs too: Priya's includes the California addendum, cited.
    expect(retrieved.Priya).toMatch(/CA-4\.3\s*Sick leave\s*·\s*California addendum\s*Cited as 1/)
    expect(retrieved.Mateo).not.toMatch(/CA-4\.3/)
    expect(retrieved.Mateo).toMatch(/§4\.3\s*Sick leave/)
  })

  test('a refusal reads as an ordinary answer: the AI label, no sources, and feedback', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.decline)
    const answer = assistantMessage(page)
    await expectAssistantChrome(answer)
    await expect(answer).toContainText("I can't share another employee's private details")
    await expect(answer.getByRole('list', { name: 'Sources' })).toHaveCount(0)
    await expect(answer.getByRole('group', { name: 'Was this right?' })).toBeVisible()
    await expect(panels(page)).toHaveCount(0)
    await expectNoViolations(page)
  })

  // The plan says an injection attempt is "refused". The spec says it is noted, not blocked: the
  // guard flags it and the turn goes on, which is what the page shows.
  test('an injection attempt is answered normally and leaks nothing', async ({ page }) => {
    // The system prompt's own words and its internal marker's phrase, read from the file.
    const prompt = readFileSync(
      resolve(import.meta.dirname, '../../api/app/ai/prompts/assistant.md'),
      'utf8',
    )
    const canary = /Internal marker, never to be repeated or mentioned: (\S+)/.exec(prompt)?.[1]
    expect(canary).toBeTruthy()
    const firstLine = prompt.split('\n')[0]!.trim()

    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.injection)
    const answer = assistantMessage(page)
    await expectAssistantChrome(answer)
    // The guard flags it but calls it ordinary, so it is answered like any question: cited, with
    // no escalation panel and no refusal.
    await expect(answer.getByRole('list', { name: 'Sources' })).toBeVisible()
    await expect(panels(page)).toHaveCount(0)
    await expect(answer).not.toContainText("I can't")
    // Nothing of the system prompt is on the page, anywhere.
    const everything = await page.locator('body').innerText()
    expect(everything).not.toContain(canary!)
    expect(everything).not.toContain(firstLine)
    expect(everything.toLowerCase()).not.toContain('system prompt')
    await page.getByRole('button', { name: 'Show your work' }).click()
    await expect(page.getByText('Safety check: no concerns')).toBeVisible()
    await expectNoViolations(page)
  })

  test('a not-found answer is followed by the HR contacts card: Dana with her title and place, then the shared inbox', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.notFound)
    const answer = assistantMessage(page)
    await expectAssistantChrome(answer)
    await expect(answer).toContainText("I couldn't find that in the handbook")
    await expect(answer.getByRole('list', { name: 'Sources' })).toHaveCount(0)
    const card = answer.locator('[data-slot="hr-contacts"]')
    await expect(card.getByRole('heading', { name: 'HR contacts' })).toBeVisible()
    await expect(card).toContainText('A person on the HR team reads and answers these, not the AI.')
    const rows = card.getByRole('listitem')
    await expect(rows).toHaveCount(2)
    await expect(rows.nth(0)).toContainText('Dana Whitfield')
    await expect(rows.nth(0)).toContainText('HR Business Partner · Denver HQ')
    await expect(rows.nth(0).getByRole('link')).toHaveAttribute(
      'href',
      'mailto:dana.whitfield@juniperrow.example',
    )
    await expect(rows.nth(1)).toContainText('HR team')
    await expect(rows.nth(1)).toContainText('Shared inbox')
    await expect(rows.nth(1).getByRole('link')).toHaveAttribute(
      'href',
      'mailto:hr@juniperrow.example',
    )
    // The card is the offer, and the answer still has its feedback.
    await expect(answer.getByRole('group', { name: 'Was this right?' })).toBeVisible()
    await expectNoViolations(page)
  })
})

test.describe('the escalation panels', () => {
  test('a sensitive question gets the answer, then the HR panel, then "Show your work" kept to 680 px', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await watchAnnouncements(page)
    await askAndWaitForAnswer(page, QUESTIONS.sensitive)
    const answer = assistantMessage(page)
    await expectAssistantChrome(answer)
    const panel = page.getByRole('region', { name: 'A person in HR handles this, not the AI' })
    await expect(panel).toBeVisible()
    await expect(panels(page)).toHaveCount(1)
    // No AI label, sources, or "Was this right?" in the panel.
    await expect(panel.getByText('AI', { exact: true })).toHaveCount(0)
    await expect(panel.getByRole('list', { name: 'Sources' })).toHaveCount(0)
    await expect(panel.getByText('Was this right?')).toHaveCount(0)
    // The assistant's answer comes first, then the panel.
    const [answerBox, panelBox] = await Promise.all([answer.boundingBox(), panel.boundingBox()])
    expect(panelBox!.y).toBeGreaterThanOrEqual(answerBox!.y + answerBox!.height - 1)
    // The event's fixed text, verbatim, and focus stays in the composer.
    await expect(panel).toContainText(
      'A person on the HR team should help with this, and they handle it confidentially. Their contact details are below.',
    )
    await expect(composerBox(page)).toBeFocused()
    // The panel's band is surface-sunken, with the fixed text and the link to §7.2.
    await expect(panel.locator('[data-slot="escalation-band"]')).toHaveCSS(
      'background-color',
      await themeColor(page, 'surface-sunken'),
    )
    await expect(
      panel.getByRole('link', { name: 'How confidential HR cases work, §7.2' }),
    ).toHaveAttribute('href', '/handbook/7.2')
    // Contacts: the directory's HR person, then the shared inbox.
    const rows = panel.locator('[data-slot="hr-contacts"]').getByRole('listitem')
    await expect(rows).toHaveCount(2)
    await expect(rows.nth(0)).toContainText('Dana Whitfield')
    await expect(rows.nth(0)).toContainText('HR Business Partner · Denver HQ')
    await expect(rows.nth(1)).toContainText('Shared inbox')
    // "Show your work" is under the panel, no wider than the assistant's 680 px, and routed.
    const toggle = page.getByRole('button', { name: 'Show your work' })
    const toggleBox = (await toggle.boundingBox())!
    expect(toggleBox.y).toBeGreaterThan(panelBox!.y + panelBox!.height - 1)
    const footer = page.locator('[data-slot="answer-footer"]').last()
    expect((await footer.boundingBox())!.width).toBeLessThanOrEqual(680)
    await toggle.click()
    await expect(page.getByText('Routed to HR guidance')).toBeVisible()
    await expect(
      page.getByText('Questions like this also go to a person on the HR team.'),
    ).toBeVisible()
    await expect(toggle).toBeFocused()
    // The arrival was announced once, politely, and focus stayed in the composer.
    const said = (await announcements(page)).filter(
      (entry) => entry.text === 'A person in HR handles this, not the AI',
    )
    expect(said).toEqual([{ text: 'A person in HR handles this, not the AI', live: 'polite' }])
    await expectNoViolations(page)
  })

  test('a crisis shows only the crisis panel: an ink band, no AI label, tel: links, and the chat link', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await watchAnnouncements(page)
    await ask(page, QUESTIONS.crisis)
    const panel = page.getByRole('region', { name: 'Reach a person right now' })
    await expect(panel).toBeVisible()
    // Only the panel answers: no assistant message, no AI label, no sources, no feedback.
    await expect(assistantMessages(page)).toHaveCount(0)
    await expect(page.getByText('AI', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Was this right?')).toHaveCount(0)
    await expect(panel.locator('[data-slot="escalation-band"]')).toHaveCSS(
      'background-color',
      await themeColor(page, 'ink'),
    )
    // The bullets are a list, with a tel: link for 911, 988, and the EAP, and the chat link.
    await expect(panel.getByRole('list').first().getByRole('listitem')).toHaveCount(4)
    await expect(panel.getByRole('link', { name: 'call 911' })).toHaveAttribute('href', 'tel:911')
    await expect(panel.getByRole('link', { name: 'Call or text 988' })).toHaveAttribute(
      'href',
      'tel:988',
    )
    await expect(panel.getByRole('link', { name: '1-800-555-0137' })).toHaveAttribute(
      'href',
      'tel:+18005550137',
    )
    await expect(panel.getByRole('link', { name: 'chat.988lifeline.org' })).toHaveAttribute(
      'href',
      'https://chat.988lifeline.org',
    )
    // The contacts follow, and say a person reads them.
    await expect(panel).toContainText(
      'A person on the HR team reads and answers these, not the AI.',
    )
    await expect(panel.locator('[data-slot="hr-contacts"]').getByRole('listitem')).toHaveCount(2)
    // Red is nowhere on this panel's header, and the composer keeps focus.
    await expect(panel.locator('[data-slot="escalation-band"] svg').first()).not.toHaveCSS(
      'color',
      await themeColor(page, 'danger'),
    )
    await expect(composerBox(page)).toBeFocused()
    // The arrival was announced once, assertively.
    await expect
      .poll(async () =>
        (await announcements(page)).filter((entry) => entry.text === 'Reach a person right now'),
      )
      .toEqual([{ text: 'Reach a person right now', live: 'assertive' }])
    await expectNoViolations(page)
  })

  test('"can\'t answer right now" has a surface-sunken band with the only red icon, Try again, and the contacts', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.guardFailure)
    const panel = page.getByRole('region', { name: "Can't answer right now" })
    await expect(panel).toBeVisible()
    await expect(assistantMessages(page)).toHaveCount(0)
    await expect(panel.getByText('AI', { exact: true })).toHaveCount(0)
    const band = panel.locator('[data-slot="escalation-band"]')
    await expect(band).toHaveCSS('background-color', await themeColor(page, 'surface-sunken'))
    // Red is the can't-answer icon alone: the sensitive and crisis panels' icons are not red.
    await expect(band.locator('svg').first()).toHaveCSS('color', await themeColor(page, 'danger'))
    await expect(panel.getByRole('link', { name: 'call 911' })).toHaveAttribute('href', 'tel:911')
    await expect(panel.getByRole('link', { name: 'call or text 988' })).toHaveAttribute(
      'href',
      'tel:988',
    )
    await expect(panel.locator('[data-slot="hr-contacts"]').getByRole('listitem')).toHaveCount(2)
    await expect(composerBox(page)).toBeFocused()
    await expectNoViolations(page)

    // Try again asks the same question again, and the guard fails again, once the server has
    // saved the first turn.
    await waitForTurnSaved(page, 0, ['guard_unavailable'])
    await panel.getByRole('button', { name: 'Try again' }).click()
    await expect(page.getByRole('region', { name: "Can't answer right now" })).toHaveCount(2)
    await expect(userMessages(page)).toHaveCount(2)
  })

  test('a panel read back from the server is silent: a reload announces nothing', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.crisis)
    await expect(page.getByRole('region', { name: 'Reach a person right now' })).toBeVisible()
    await page.reload()
    await watchAnnouncements(page)
    await expect(page.getByRole('region', { name: 'Reach a person right now' })).toBeVisible()
    await page.waitForTimeout(400)
    expect(await announcements(page)).toEqual([])
  })
})

test.describe('the answer under way', () => {
  test('a failure partway through shows the API text as an alert inside the message, with Retry', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.midStreamError)
    const answer = assistantMessage(page)
    const alert = answer.getByRole('alert')
    await expect(alert).toBeVisible()
    await expectAssistantChrome(answer)
    // The text the API's error event carries, shown as written, with the partial answer above it.
    await expect(alert).toContainText(
      "I can't reach the assistant service right now. Please try again in a moment, or ask the HR team directly.",
    )
    await expect(answer).toContainText('Let me check the handbook for that.')
    await expect(alert.getByRole('button', { name: 'Retry' })).toBeVisible()
    // An incomplete answer has no feedback, and the composer is free again.
    await expect(answer.getByText('Was this right?')).toHaveCount(0)
    await expect(askButton(page)).toBeVisible()
    await expectNoViolations(page)

    // Retry asks the same question again, once the server has saved the failed turn (a question
    // sent before is refused as "still answering").
    await waitForTurnSaved(page, 0, ['failed'])
    await alert.getByRole('button', { name: 'Retry' }).click()
    await expect(page.getByRole('alert')).toHaveCount(2)
    await expect(userMessages(page)).toHaveCount(2)
  })

  test('a streaming answer is busy: a status line, Stop in the place of Ask, and no sources or feedback yet', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.silence)
    const answer = assistantMessage(page)
    await expectAssistantChrome(answer)
    // The status line is a polite live region, in the page and ready from the start.
    const status = answer.locator('[data-slot="status-line"]')
    await expect(status).toHaveAttribute('role', 'status')
    await expect(status).toHaveAttribute('aria-live', 'polite')
    await expect(answer.locator('[data-slot="answer-live"]')).toHaveAttribute('aria-busy', 'true')
    await expect(stopButton(page)).toBeVisible()
    await expect(askButton(page)).toHaveCount(0)
    await expect(answer.getByRole('list', { name: 'Sources' })).toHaveCount(0)
    await expect(answer.getByText('Was this right?')).toHaveCount(0)
    await expectNoViolations(page)
    await stopButton(page).click()
  })

  // STUB (a held stream): the scripted model finishes in milliseconds, so a held stream is the way
  // to look at an answer while it is still arriving.
  test('markers appear while the text streams, and the chips, feedback, and work trace wait for the end (STUB: held stream)', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    const stream = await holdNextTurnStream(page)
    await ask(page, QUESTIONS.cited)
    await pushSearchSteps(stream)
    await stream.push('text.delta', { text: SICK_LEAVE_SENTENCE })
    await stream.push('citation', {
      ...SICK_LEAVE_CITATION,
      offsetUtf16: SICK_LEAVE_SENTENCE.length,
    })
    await stream.push('text.delta', { text: ' This is the company rule for' })
    const answer = assistantMessage(page)
    await expect(stopButton(page)).toBeVisible()
    await expect(answer.locator('[data-slot="answer-live"]')).toHaveAttribute('aria-busy', 'true')
    // The marker is in the text already, numbered and named for its source.
    await expect(
      answer.getByRole('button', { name: 'Source 1: Handbook §4.3, Time off' }),
    ).toHaveCount(1)
    await expect(answer.getByRole('list', { name: 'Sources' })).toHaveCount(0)
    await expect(page.getByRole('group', { name: 'Was this right?' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Show your work' })).toHaveCount(0)
    await expectNoViolations(page)
    await stopButton(page).click()
  })

  test('a stopped answer keeps its partial text and its marker, with Stopped and Ask again (STUB: held stream)', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    const stream = await holdNextTurnStream(page)
    await ask(page, QUESTIONS.cited)
    await pushSearchSteps(stream)
    await stream.push('text.delta', { text: SICK_LEAVE_SENTENCE })
    await stream.push('citation', {
      ...SICK_LEAVE_CITATION,
      offsetUtf16: SICK_LEAVE_SENTENCE.length,
    })
    await stream.push('text.delta', { text: ' This is the company rule for' })
    await expect(page.getByText('This is the company rule for')).toBeVisible()
    await stopButton(page).click()
    const answer = assistantMessage(page)
    await expect(answer).toContainText(SICK_LEAVE_SENTENCE)
    await expect(answer).toContainText('This is the company rule for')
    await expect(answer.getByRole('button', { name: /^Source 1:/ })).toHaveCount(1)
    await expect(answer.getByText('Stopped', { exact: true })).toBeVisible()
    await expect(answer.getByRole('button', { name: 'Ask again' })).toBeVisible()
    await expect(answer.locator('[data-slot="answer-live"]')).toHaveAttribute('aria-busy', 'false')
    await expect(composerBox(page)).toBeFocused()
    await expectNoViolations(page)
  })

  test('the working note is taken back: it shows as a status line, never in the final answer', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await watchStatusLines(page)
    await askAndWaitForAnswer(page, QUESTIONS.workingNote)
    const log = await statusLog(page)
    // The note the model wrote before searching was shown in the status line (with a spinner while
    // it was current), and every step lives in a polite status region.
    expect(log.map((entry) => entry.text)).toContain('Let me look that up in the handbook first.')
    expect(log.every((entry) => entry.role === 'status')).toBe(true)
    expect(log.some((entry) => entry.spinner)).toBe(true)
    // A finished step has a check and its words in the past tense ("Searched", not "Searching").
    const finished = log.filter((entry) => entry.check)
    expect(finished.map((entry) => entry.text)).toContainEqual(
      expect.stringMatching(/^Searched the handbook/),
    )
    expect(finished.every((entry) => !/ing\b/.test(entry.text.split(' ')[0]!))).toBe(true)
    const answer = assistantMessage(page)
    await expect(answer).not.toContainText('Let me look that up in the handbook first.')
    await expect(answer).toContainText('According to')
    // The finished answer has no status line any more.
    await expect(answer.locator('[data-slot="status-line"]')).toHaveCount(0)
    await expectNoViolations(page)
  })

  test('Enter while an answer streams shows "still answering", sends nothing, and keeps the draft', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.silence)
    await expect(stopButton(page)).toBeVisible()
    const sent = countTurnRequests(page)
    await composerBox(page).fill('A different question, typed while it streams')
    await composerBox(page).press('Enter')
    const line = composerLine(page)
    await expect(line).toHaveText(STILL_ANSWERING_TEXT)
    await expect(line).toHaveAttribute('role', 'alert')
    await expect(composerBox(page)).toHaveValue('A different question, typed while it streams')
    // Give a stray request time to leave before the count is read.
    await page.waitForTimeout(300)
    expect(sent).toEqual([])
    await expect(userMessages(page)).toHaveCount(1)
    await expectNoViolations(page)
    await stopButton(page).click()
  })

  test('Stop returns focus to the composer and shows Stopped with Ask again; a reload shows it still, and a new question works', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.silence)
    await expect(stopButton(page)).toBeVisible()
    await stopButton(page).click()
    await expect(composerBox(page)).toBeFocused()
    const answer = assistantMessage(page)
    await expect(answer.getByText('Stopped', { exact: true })).toBeVisible()
    await expect(answer.getByRole('button', { name: 'Ask again' })).toBeVisible()
    await expect(askButton(page)).toBeVisible()
    await expect(stopButton(page)).toHaveCount(0)
    await expectNoViolations(page)

    // The server saves the dropped stream as stopped; wait for that, then reload.
    await expect
      .poll(async () => (await currentConversation(page))?.turns.at(0)?.status)
      .toBe('stopped')
    await page.reload()
    await expect(assistantMessage(page).getByText('Stopped', { exact: true })).toBeVisible()
    await expect(assistantMessage(page).getByRole('button', { name: 'Ask again' })).toBeVisible()
    await expectNoViolations(page)

    // The conversation is free: the next question is answered.
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await expect(assistantMessages(page)).toHaveCount(2)
    await expect(assistantMessage(page, 1)).toContainText('According to')
  })

  test('Ask again after Stop asks the stopped question again', async ({ page }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.silence)
    await stopButton(page).click()
    await expect(assistantMessage(page).getByRole('button', { name: 'Ask again' })).toBeVisible()
    await waitForTurnSaved(page, 0)
    await assistantMessage(page).getByRole('button', { name: 'Ask again' }).click()
    await expect(userMessages(page)).toHaveCount(2)
    await expect(stopButton(page)).toBeVisible()
    await stopButton(page).click()
  })

  test('switching persona while an answer streams shows nothing of the old answer to the new person, even from a late event', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    // STUB: a held stream, so there is an event to send after the switch.
    const stream = await holdNextTurnStream(page)
    await ask(page, QUESTIONS.cited)
    await pushSearchSteps(stream)
    await stream.push('text.delta', { text: 'Priya-only words that must not reach Mateo.' })
    await expect(page.getByText('Priya-only words')).toBeVisible()
    await expect(stopButton(page)).toBeVisible()

    await switchTo(page, 'Mateo')
    await expect(greetingHeading(page, 'Mateo')).toBeVisible()
    // The old stream sends more after the switch. None of it is shown to the new person.
    await stream.push('text.delta', { text: ' More Priya-only words, sent late.' })
    await stream.push('citation', { ...SICK_LEAVE_CITATION, offsetUtf16: 5 })
    await stream.push('turn.completed', {
      turnId: '00000000-0000-4000-8000-000000000001',
      servedBy: 'scripted',
      usage: { inputTokens: 0, outputTokens: 0 },
    })
    await page.waitForTimeout(500)
    // The home, as for anyone with no conversation: no question, no Stop, no answer.
    await expect(page.getByText('Priya-only')).toHaveCount(0)
    await expect(userMessages(page)).toHaveCount(0)
    await expect(stopButton(page)).toHaveCount(0)
    await expect(assistantMessages(page)).toHaveCount(0)
    await expect(greetingHeading(page, 'Mateo')).toBeVisible()
    expect(await currentConversation(page)).toBeNull()
    await expectNoViolations(page)
  })
})

test.describe('a cited answer', () => {
  test('user messages sit on the right on surface-hover; assistant messages have no bubble; markers and chips are numbered and named by source', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const user = userMessages(page).first()
    await expect(user).toHaveText(`You asked: ${QUESTIONS.cited}`)
    await expect(user).toHaveCSS('background-color', await themeColor(page, 'surface-hover'))
    const thread = (await page.locator('[data-slot="conversation-thread"]').boundingBox())!
    const userBox = (await user.boundingBox())!
    expect(Math.abs(userBox.x + userBox.width - (thread.x + thread.width))).toBeLessThanOrEqual(1)
    const answer = assistantMessage(page)
    await expectAssistantChrome(answer)
    // Marker 1 and chip 1 are the same section, and each is a button named for it.
    const name = 'Source 1: Handbook §4.3, Time off'
    const sources = answer.getByRole('button', { name })
    await expect(sources).toHaveCount(3)
    for (const source of await sources.all()) {
      await expect(source).toHaveAttribute('aria-expanded', 'false')
    }
    await expect(
      answer.getByRole('list', { name: 'Sources' }).getByRole('button', { name }),
    ).toContainText('Handbook §4.3 · Time off')
    // The composer's disclosure stays under the box.
    const disclosure = page.getByText(/Open Door is an AI assistant\./).first()
    await expect(disclosure).toBeVisible()
    await expectNoViolations(page)
  })

  test('"Show your work" is a disclosure: collapsed, aria-controls, focus stays, and it lists the tools and the sections', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const toggle = page.getByRole('button', { name: 'Show your work' })
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    const controlled = await toggle.getAttribute('aria-controls')
    expect(controlled).toBeTruthy()
    await expect(page.locator(`[id="${controlled}"]`)).toBeHidden()
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await expect(toggle).toBeFocused()
    await expect(page.locator(`[id="${controlled}"]`)).toBeVisible()
    await expect(page.getByText('Safety check: no concerns')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Tools called' })).toBeVisible()
    await expect(page.getByRole('list', { name: 'Tools called' })).toContainText(
      `Searched the handbook: ${QUESTIONS.cited}`,
    )
    const sections = page.getByRole('list', { name: 'Sections retrieved' })
    await expect(sections.getByRole('listitem').first()).toContainText(/§4\.3\s*Sick leave/)
    await expect(sections.getByRole('listitem').first()).toContainText('Cited as 1')
    await expect(sections).toContainText('Not cited')
    await expectNoViolations(page)
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(toggle).toBeFocused()
  })

  test('an answer that never searched lists "None" for its tools and sections', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.decline)
    await page.getByRole('button', { name: 'Show your work' }).click()
    await expect(page.getByText('Safety check: no concerns')).toBeVisible()
    await expect(page.getByText('None', { exact: true })).toHaveCount(2)
    await expectNoViolations(page)
  })
})

test.describe('the source panel (1440 px, docked)', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  const marker = (page: Page, turn = 0) =>
    assistantMessage(page, turn).locator('[data-slot="citation-marker"]').first()
  const panel = (page: Page) => page.getByRole('complementary', { name: 'Handbook passage' })

  test('a marker opens its passage with ?source= in the URL and focus on its title; Escape closes it and focus returns to the marker', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await expect(marker(page)).toHaveAttribute('aria-expanded', 'false')
    await marker(page).click()
    await expect(panel(page)).toBeVisible()
    // The first result is §4.3's "Notes and notice" chunk (its first passage is p5) since the
    // handbook's 2026.11.1 sick-leave paragraphs joined it.
    await expect(page).toHaveURL(/\/ask\?source=4\.3(~|%7E)p5$/i)
    await expect(panel(page).getByRole('heading', { level: 2, name: 'Sick leave' })).toBeFocused()
    await expect(marker(page)).toHaveAttribute('aria-expanded', 'true')
    // It takes the rail's place, beside the thread, and is not modal.
    await expect(page.getByRole('complementary', { name: 'Sandbox status' })).toHaveCount(0)
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expectNoViolations(page)

    await page.keyboard.press('Escape')
    await expect(panel(page)).toHaveCount(0)
    await expect(page).toHaveURL('/ask')
    await expect(marker(page)).toBeFocused()
    await expect(marker(page)).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByRole('complementary', { name: 'Sandbox status' })).toBeVisible()
  })

  test('Close, the same marker again, and Back each close the panel and return focus to the marker', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)

    await marker(page).click()
    await panel(page).getByRole('button', { name: 'Close passage' }).click()
    await expect(panel(page)).toHaveCount(0)
    await expect(marker(page)).toBeFocused()

    await marker(page).click()
    await expect(panel(page)).toBeVisible()
    await marker(page).click()
    await expect(panel(page)).toHaveCount(0)
    await expect(marker(page)).toBeFocused()

    await marker(page).click()
    await expect(panel(page)).toBeVisible()
    await page.goBack()
    await expect(panel(page)).toHaveCount(0)
    await expect(page).toHaveURL('/ask')
    await expect(marker(page)).toBeFocused()
  })

  test('a chip opens the passage cited from its section, and a different marker replaces it', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await askAndWaitForAnswer(page, QUESTIONS.otherSection)
    const chip = assistantMessage(page, 0)
      .getByRole('list', { name: 'Sources' })
      .getByRole('button')
    await chip.click()
    const title = panel(page).getByRole('heading', { level: 2 })
    await expect(title).toBeFocused()
    const firstUrl = page.url()
    await expect(chip).toHaveAttribute('aria-expanded', 'true')

    // The second answer's marker replaces the passage (a different one, so the address changes),
    // and focus goes to the title again.
    await marker(page, 1).click()
    await expect.poll(() => page.url()).not.toBe(firstUrl)
    await expect(title).toBeFocused()
    await expect(chip).toHaveAttribute('aria-expanded', 'false')
    await expect(marker(page, 1)).toHaveAttribute('aria-expanded', 'true')

    // The same marker again closes it, and focus returns to the newest opener.
    await marker(page, 1).click()
    await expect(panel(page)).toHaveCount(0)
    await expect(marker(page, 1)).toBeFocused()
  })

  test('the URL is the source of truth: a reload keeps the passage open, and Escape closes it', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await marker(page).click()
    await expect(panel(page)).toBeVisible()
    await page.reload()
    await expect(panel(page)).toBeVisible()
    await expect(panel(page).getByRole('heading', { level: 2, name: 'Sick leave' })).toBeVisible()
    await expect(marker(page)).toHaveAttribute('aria-expanded', 'true')
    await page.getByRole('button', { name: 'Close passage' }).click()
    await expect(panel(page)).toHaveCount(0)
    await expect(page).toHaveURL('/ask')
  })
})

test.describe('feedback', () => {
  test('Yes moves focus to "Thanks for the feedback.", which is a status, and it is saved', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await page.getByRole('button', { name: 'Yes' }).click()
    const thanks = page.getByText('Thanks for the feedback.')
    await expect(thanks).toBeFocused()
    await expect(thanks).toHaveJSProperty('tagName', 'OUTPUT')
    await expect(
      page.getByRole('status').filter({ hasText: 'Thanks for the feedback.' }),
    ).toBeVisible()
    await expect
      .poll(async () => (await currentConversation(page))?.turns[0]?.feedback)
      .toEqual(expect.objectContaining({ helpful: true }))
    await expectNoViolations(page)
    // Read back from the server after a reload, with the thank-you in place of the question.
    await page.reload()
    await expect(page.getByText('Thanks for the feedback.')).toBeVisible()
    await expect(page.getByRole('group', { name: 'Was this right?' })).toHaveCount(0)
  })

  test('a failed feedback send keeps what was typed, shows the error, and Send tries again (STUB: the feedback POST)', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    let failing = true
    await page.route('**/api/v1/assistant/turns/*/feedback', (route) =>
      failing
        ? route.fulfill({
            status: 500,
            contentType: 'application/problem+json',
            body: problem(500, 'Internal Server Error'),
          })
        : route.fallback(),
    )
    await page.getByRole('button', { name: 'No' }).click()
    const reason = page.getByRole('textbox', { name: /What was wrong/ })
    await reason.fill('It cited the wrong state')
    await page.getByRole('button', { name: 'Send feedback' }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'Something went wrong' })).toBeVisible()
    // The form is still open, with what was typed.
    await expect(reason).toHaveValue('It cited the wrong state')
    await expect(page.getByText('Thanks for the feedback.')).toHaveCount(0)
    await expectNoViolations(page)
    // Sending again, once the API answers, works.
    failing = false
    await page.getByRole('button', { name: 'Send feedback' }).click()
    await expect(page.getByText('Thanks for the feedback.')).toBeFocused()
  })

  test('No opens the reason form with focus in the box, and Cancel returns focus to No', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const no = page.getByRole('button', { name: 'No' })
    await no.click()
    const reason = page.getByRole('textbox', { name: /What was wrong/ })
    await expect(reason).toBeFocused()
    await expect(page.getByText('0 of 500 characters')).toBeVisible()
    await expect(reason).toHaveAttribute('placeholder', 'For example, it cited the wrong state')
    await expectNoViolations(page)
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(no).toBeFocused()
    await expect(reason).toHaveCount(0)
  })

  test('No, a reason, and Send feedback saves it and moves focus to "Thanks for the feedback."', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await page.getByRole('button', { name: 'No' }).click()
    await page.getByRole('textbox', { name: /What was wrong/ }).fill('It cited the wrong state')
    await expect(page.getByText('24 of 500 characters')).toBeVisible()
    await page.getByRole('button', { name: 'Send feedback' }).click()
    await expect(page.getByText('Thanks for the feedback.')).toBeFocused()
    await expect
      .poll(async () => (await currentConversation(page))?.turns[0]?.feedback)
      .toEqual(expect.objectContaining({ helpful: false, reason: 'It cited the wrong state' }))
    await expectNoViolations(page)
  })
})

test.describe('the header and the conversation', () => {
  test('"Start a new conversation" clears the view and returns to the home', async ({ page }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await expect(page.locator('[data-slot="retention-line"]:visible')).toHaveText(
      'Conversations are deleted with your sandbox after 24 hours.',
    )
    await expect(
      page.locator('[data-slot="sandbox-indicator"]').locator('visible=true'),
    ).toHaveCount(1)
    await page.getByRole('button', { name: 'Start a new conversation' }).click()
    await expect(greetingHeading(page, 'Priya')).toBeVisible()
    await expect(userMessages(page)).toHaveCount(0)
    await expect(assistantMessages(page)).toHaveCount(0)
    // A question now starts a fresh conversation, with none of the old turns in it.
    await askAndWaitForAnswer(page, QUESTIONS.decline)
    await expect(userMessages(page)).toHaveCount(1)
    await expect(userMessages(page)).toContainText(QUESTIONS.decline)
    await expectNoViolations(page)
  })

  test('the Tab order runs: the nav, the persona switcher, "Start a new conversation", the thread, the composer, Ask, then the rail', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await focusPageStart(page)
    const stops = await tabStops(page, 14)
    const source = 'Source 1: Handbook §4.3, Time off'
    expect(stops.map((stop) => stop.name)).toEqual([
      'Ask',
      'Directory',
      'Handbook',
      'Switch persona. Current: Priya Raman, Visual Merchandiser',
      'Start a new conversation',
      // The thread in reading order: the markers in the text, the chip, Yes, No, Show your work.
      source,
      source,
      source,
      'Yes',
      'No',
      'Show your work',
      'Ask Open Door',
      'Ask',
      // The rail comes last.
      expect.stringMatching(/Handbook updated\. Open Handbook$/),
    ])
    expect(stops[11]!.tag).toBe('TEXTAREA')
    expect(stops[12]!.slot).toBe('composer-ask')
  })

  test("while an answer streams, Stop takes Ask's place in the Tab order", async ({ page }) => {
    await startAs(page, 'Priya')
    await ask(page, QUESTIONS.silence)
    await expect(stopButton(page)).toBeVisible()
    await composerBox(page).focus()
    const stops = await tabStops(page, 2)
    expect(stops[0]).toMatchObject({ name: 'Stop', slot: 'composer-stop' })
    expect(stops[1]!.name).toMatch(/Handbook updated\. Open Handbook$/)
    await stopButton(page).click()
  })
})

test.describe('the composer', () => {
  test("the personal-data warning is an alert with the API's words, and nothing is sent", async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    const sent = countTurnRequests(page)
    await composerBox(page).fill('My number is 123-45-6789, is that ok?')
    // The check runs when the question is sent, in the browser, so the number never leaves it.
    await composerBox(page).press('Enter')
    const warning = page.getByRole('alert').filter({ hasText: PERSONAL_DATA_TEXT })
    await expect(warning).toHaveText(PERSONAL_DATA_TEXT)
    await expect(composerBox(page)).toHaveValue('My number is 123-45-6789, is that ok?')
    await expectNoViolations(page)
    // Ask is aria-disabled while the warning stands, so Playwright needs the click forced.
    await askButton(page).click({ force: true })
    await page.waitForTimeout(300)
    expect(sent).toEqual([])
    await expect(userMessages(page)).toHaveCount(1)
    // Taking the number out clears the warning, and the question sends.
    await composerBox(page).fill('My number is hidden, is that ok?')
    await expect(warning).toHaveCount(0)
    await askButton(page).click()
    await expect(userMessages(page)).toHaveCount(2)
    expect(sent).toHaveLength(1)
  })

  test('the personal-data warning also shows on the home, before any conversation', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    const sent = countTurnRequests(page)
    await composerBox(page).fill('123-45-6789')
    await askButton(page).click()
    await expect(page.getByRole('alert').filter({ hasText: PERSONAL_DATA_TEXT })).toBeVisible()
    await page.waitForTimeout(300)
    expect(sent).toEqual([])
    await expect(greetingHeading(page, 'Priya')).toBeVisible()
    await expectNoViolations(page)
  })

  test("from 1,800 characters a count shows, past 2,000 the question can't be sent, and a follow-up has its own placeholder", async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await expect(composerBox(page)).toHaveAttribute('placeholder', 'Ask a follow-up question')
    const sent = countTurnRequests(page)
    await composerBox(page).fill('a'.repeat(1799))
    await expect(composerLine(page)).toHaveCount(0)
    await composerBox(page).fill('a'.repeat(1962))
    await expect(composerLine(page)).toHaveText('1,962 of 2,000 characters')
    await expectNoViolations(page)
    await composerBox(page).fill('a'.repeat(2001))
    await expect(composerLine(page)).toHaveText(
      '2,001 of 2,000 characters. Shorten your question to send it.',
    )
    await composerBox(page).press('Enter')
    await page.waitForTimeout(300)
    expect(sent).toEqual([])
    await expectNoViolations(page)
  })
})

// The states below can't be reached with the scripted model, so the conversation GET is STUBBED:
// the real response, with the budget or length fields changed.
test.describe('budget and length states (STUB: the conversation GET)', () => {
  /** Tab stops from the top of the page until the focus leaves the last control. */
  async function allTabStops(page: Page) {
    await focusPageStart(page)
    return tabStops(page, 18)
  }

  for (const kind of ['sandbox', 'daily'] as const) {
    test(`the ${kind} banner shows the API's text, disables the composer, skips it by Tab, and keeps the Handbook and Directory links (STUB: GET)`, async ({
      page,
    }) => {
      const message = kind === 'sandbox' ? BUDGET_SANDBOX_TEXT : BUDGET_DAILY_TEXT
      await startAs(page, 'Priya')
      await askAndWaitForAnswer(page, QUESTIONS.cited)
      await stubConversation(page, (body) => {
        const reached = kind === 'sandbox' ? 'sandboxReached' : 'dailyReached'
        body.budget = { ...body.budget, [reached]: true, banner: { kind, message } }
      })
      await page.reload()

      const banner = page.locator('[data-slot="banner"]').filter({ hasText: message.slice(0, 40) })
      await expect(banner).toBeVisible()
      await expect(banner).toContainText(message)
      await expect(banner.getByRole('link', { name: 'call 911' })).toHaveAttribute(
        'href',
        'tel:911',
      )
      await expect(banner.getByRole('link', { name: 'call or text 988' })).toHaveAttribute(
        'href',
        'tel:988',
      )
      const startNew = banner.getByRole('button', { name: 'Start a new sandbox' })
      if (kind === 'sandbox') await expect(startNew).toBeVisible()
      else await expect(startNew).toHaveCount(0)

      // The composer and Ask are off, and the placeholder says why.
      await expect(composerBox(page)).toBeDisabled()
      await expect(composerBox(page)).toHaveAttribute(
        'placeholder',
        kind === 'sandbox'
          ? "The assistant isn't available in this sandbox."
          : "The assistant isn't available until tomorrow.",
      )
      await expect(askButton(page)).toBeDisabled()
      const links = page.locator('[data-slot="composer-line"]')
      await expect(links).toHaveText('You can still use the Handbook and the Directory.')
      await expect(links.getByRole('link', { name: 'Handbook' })).toHaveAttribute(
        'href',
        '/handbook',
      )
      await expect(links.getByRole('link', { name: 'Directory' })).toHaveAttribute(
        'href',
        '/directory',
      )
      // A failed answer would offer Retry, which would only fail again; and the thread is still read-only.
      await expectNoViolations(page)

      // Tab: the nav, the persona switcher, the banner action, "Start a new conversation", the
      // thread, then the two links in place of the composer, and the rail. The box and Ask are skipped.
      const stops = await allTabStops(page)
      const names = stops.map((stop) => stop.name)
      expect(names.slice(0, 4)).toEqual([
        'Ask',
        'Directory',
        'Handbook',
        'Switch persona. Current: Priya Raman, Visual Merchandiser',
      ])
      // The banner comes before the page: its two emergency links, then (sandbox only) its action.
      const afterSwitcher = names.slice(4)
      expect(afterSwitcher.slice(0, 2)).toEqual(['call 911', 'call or text 988'])
      if (kind === 'sandbox') expect(afterSwitcher[2]).toBe('Start a new sandbox')
      expect(afterSwitcher[kind === 'sandbox' ? 3 : 2]).toBe('Start a new conversation')
      expect(stops.some((stop) => stop.tag === 'TEXTAREA')).toBe(false)
      expect(stops.some((stop) => stop.slot === 'composer-ask')).toBe(false)
      const handbookAt = names.indexOf('Handbook', 4)
      expect(handbookAt).toBeGreaterThan(names.indexOf('Show your work'))
      expect(names[handbookAt + 1]).toBe('Directory')
      expect(names[handbookAt + 2]).toMatch(/Handbook updated\. Open Handbook$/)
    })
  }

  test('"Start a new sandbox" in the sandbox banner starts a fresh sandbox (STUB: GET)', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await stubConversation(page, (body) => {
      body.budget = {
        ...body.budget,
        sandboxReached: true,
        banner: { kind: 'sandbox', message: BUDGET_SANDBOX_TEXT },
      }
    })
    await page.reload()
    await page.getByRole('button', { name: 'Start a new sandbox' }).click()
    // A new sandbox is a new company with no conversation, so the home shows. The stub changes
    // nothing for a person with no conversation, so the banner is gone with the old sandbox.
    await expect(greetingHeading(page, 'Priya')).toBeVisible()
    await expect(page.getByText(BUDGET_SANDBOX_TEXT.slice(0, 40))).toHaveCount(0)
  })

  test('the long-conversation notice offers "Start a new conversation" above the box (STUB: GET)', async ({
    page,
  }) => {
    await startAs(page, 'Priya')
    await askAndWaitForAnswer(page, QUESTIONS.cited)
    await stubConversation(page, (body) => {
      body.longHistory = true
    })
    await page.reload()
    const notice = page.locator('[data-slot="composer-notice"]')
    await expect(notice).toContainText(
      'This conversation is getting long, so answers may miss details from earlier messages. A new conversation starts clean.',
    )
    const noticeBox = (await notice.boundingBox())!
    const boxBox = (await composerBox(page).boundingBox())!
    expect(noticeBox.y + noticeBox.height).toBeLessThanOrEqual(boxBox.y)
    // The composer still works under the notice.
    await expect(composerBox(page)).toBeEnabled()
    await expectNoViolations(page)
    await notice.getByRole('button', { name: 'Start a new conversation' }).click()
    await expect(greetingHeading(page, 'Priya')).toBeVisible()
  })
})
