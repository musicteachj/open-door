import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { GuardOut } from '@/api/generated'
import { SICK_LEAVE_SECTIONS, apiCitations, citation, toolCall } from '@/test/assistant-fixtures'
import * as sources from './sources'
import { numberBySection } from './sources'
import { WorkTrace, type WorkTraceProps } from './work-trace'

const ORDINARY: GuardOut = { category: 'ordinary' }
const SENSITIVE: GuardOut = { category: 'sensitive', kind: 'harassment' }

function renderTrace(props: Partial<WorkTraceProps> = {}) {
  return render(
    <WorkTrace
      guard={ORDINARY}
      toolCalls={[toolCall()]}
      sections={SICK_LEAVE_SECTIONS}
      citations={[
        citation({ marker: 1, sectionId: 'CA-4.3' }),
        citation({ marker: 2, sectionId: '4.3', passageId: '4.3~p3' }),
      ]}
      {...props}
    />,
  )
}

const toggle = () => screen.getByRole('button', { name: 'Show your work' })

async function open() {
  await userEvent.click(toggle())
  return document.getElementById(toggle().getAttribute('aria-controls')!)!
}

describe('WorkTrace: the disclosure', () => {
  it('is collapsed by default, with its panel out of sight', () => {
    renderTrace()
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('Safety check: no concerns')).not.toBeVisible()
  })

  it('opens expanded with defaultOpen, for a screen that draws that state, and still closes', async () => {
    renderTrace({ defaultOpen: true })
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Safety check: no concerns')).toBeVisible()
    await userEvent.click(toggle())
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
  })

  it('points aria-controls at the panel, and opens and closes it', async () => {
    renderTrace()
    const panelId = toggle().getAttribute('aria-controls')!
    expect(document.getElementById(panelId)).toContainElement(
      screen.getByText('Safety check: no concerns'),
    )
    await userEvent.click(toggle())
    expect(toggle()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('Safety check: no concerns')).toBeVisible()
    await userEvent.click(toggle())
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('Safety check: no concerns')).not.toBeVisible()
  })

  it('keeps focus on the button when it toggles', async () => {
    renderTrace()
    await userEvent.click(toggle())
    expect(toggle()).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    expect(toggle()).toHaveFocus()
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
  })
})

describe('WorkTrace: the safety check', () => {
  it('says no concerns for an ordinary question, with no routing note', async () => {
    renderTrace({ guard: ORDINARY })
    const panel = await open()
    expect(within(panel).getByText('Safety check: no concerns')).toBeVisible()
    expect(within(panel).queryByText(/also go to a person/)).not.toBeInTheDocument()
  })

  it('says it was routed to HR guidance for a sensitive one, with the note', async () => {
    renderTrace({ guard: SENSITIVE })
    const panel = await open()
    expect(within(panel).getByText('Routed to HR guidance')).toBeVisible()
    expect(
      within(panel).getByText('Questions like this also go to a person on the HR team.'),
    ).toBeVisible()
    expect(within(panel).queryByText('Safety check: no concerns')).not.toBeInTheDocument()
  })

  it('claims nothing when the turn has no recorded safety check', async () => {
    renderTrace({ guard: null })
    const panel = await open()
    expect(within(panel).queryByText(/Safety check|Routed/)).not.toBeInTheDocument()
  })
})

describe('WorkTrace: tools called', () => {
  it('has a line per call, worded from the tool and its summary', async () => {
    renderTrace({
      toolCalls: [
        toolCall({ name: 'get_my_profile', inputSummary: '' }),
        toolCall({ inputSummary: "query='sick leave', location=CA" }),
        toolCall({ inputSummary: "query='California sick leave'" }),
      ],
    })
    const panel = await open()
    const list = within(panel).getByRole('list', { name: 'Tools called' })
    const lines = within(list)
      .getAllByRole('listitem')
      .map((item) => item.textContent)
    expect(lines).toEqual([
      'Read your profile',
      'Searched the handbook: sick leave',
      'Searched the handbook: California sick leave',
    ])
  })

  it('says so when a tool call failed, keeping the line for what was tried', async () => {
    renderTrace({
      toolCalls: [
        toolCall({ ok: true, inputSummary: "query='sick leave'" }),
        toolCall({ ok: false, inputSummary: "query='sick leave'" }),
        toolCall({ ok: false, name: 'get_my_profile', inputSummary: '' }),
      ],
    })
    const panel = await open()
    const list = within(panel).getByRole('list', { name: 'Tools called' })
    expect(
      within(list)
        .getAllByRole('listitem')
        .map((item) => item.textContent),
    ).toEqual([
      'Searched the handbook: sick leave',
      'Searched the handbook: sick leave (failed)',
      'Read your profile (failed)',
    ])
  })

  it('words the entry for steps the limit skipped, and does not call it failed', async () => {
    renderTrace({
      toolCalls: [
        toolCall({ ok: true }),
        toolCall({ name: 'skipped', inputSummary: '3 calls not run (limit)', ok: false }),
      ],
    })
    const panel = await open()
    const list = within(panel).getByRole('list', { name: 'Tools called' })
    const lines = within(list)
      .getAllByRole('listitem')
      .map((item) => item.textContent)
    expect(lines[1]).toBe('Skipped 3 more steps (the limit for one question)')
    expect(panel).not.toHaveTextContent('calls not run')
    expect(lines[1]).not.toContain('(failed)')
  })

  it('never shows a private detail from a profile call', async () => {
    renderTrace({
      toolCalls: [toolCall({ name: 'get_my_profile', inputSummary: 'Oakland store, California' })],
    })
    const panel = await open()
    expect(panel).not.toHaveTextContent('Oakland')
  })

  it('says None when no tool was called', async () => {
    renderTrace({ toolCalls: [] })
    const panel = await open()
    const heading = within(panel).getByRole('heading', { name: 'Tools called' })
    expect(heading.parentElement).toHaveTextContent('None')
    expect(within(panel).queryByRole('list', { name: 'Tools called' })).not.toBeInTheDocument()
  })
})

describe('WorkTrace: sections retrieved', () => {
  it('shows each section with its title and group, and whether it was cited', async () => {
    renderTrace()
    const panel = await open()
    const rows = within(
      within(panel).getByRole('list', { name: 'Sections retrieved' }),
    ).getAllByRole('listitem')
    expect(rows.map((row) => row.textContent)).toEqual([
      'CA-4.3Sick leave · California addendumCited as 1',
      '§4.3Sick leave · Company handbookCited as 2',
      'CO-4.3Sick leave · Colorado addendumNot cited',
      '§4.1Paid time off · Company handbookNot cited',
    ])
  })

  it('stacks a row below sm: the number and status on one line, the title full width under them', async () => {
    renderTrace()
    const panel = await open()
    const row = within(
      within(panel).getByRole('list', { name: 'Sections retrieved' }),
    ).getAllByRole('listitem')[0]!
    const [number, title, status] = [...row.children] as HTMLElement[]
    expect(row).toHaveClass(
      'grid-cols-[minmax(0,1fr)_auto]',
      'sm:grid-cols-[64px_minmax(0,1fr)_auto]',
    )
    expect(title).toHaveClass('col-span-2', 'row-start-2', 'sm:col-span-1', 'sm:row-start-1')
    expect(number).toHaveClass('row-start-1')
    expect(status).toHaveClass('row-start-1', 'col-start-2', 'sm:col-start-3')
  })

  it('writes "Cited as N" in bold and "Not cited" plain', async () => {
    renderTrace()
    const panel = await open()
    expect(within(panel).getByText('Cited as 1')).toHaveClass('font-semibold')
    expect(within(panel).getAllByText('Not cited')[0]).not.toHaveClass('font-semibold')
  })

  it('shows the section number alone when the API sends a null title and group', async () => {
    renderTrace({
      sections: [{ sectionId: '4.1', passageIds: ['4.1~p1'], title: null, groupName: null }],
    })
    const panel = await open()
    const rows = within(
      within(panel).getByRole('list', { name: 'Sections retrieved' }),
    ).getAllByRole('listitem')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent(/^§4\.1Not cited$/)
  })

  it("takes a cited section's title and group from its citation when the section has none", async () => {
    renderTrace({
      sections: [{ sectionId: 'CA-4.3', passageIds: ['CA-4.3~p1'], title: null, groupName: null }],
    })
    const panel = await open()
    expect(panel).toHaveTextContent('CA-4.3Sick leave · California addendumCited as 1')
  })

  it('says None when no section was retrieved', async () => {
    renderTrace({ sections: [] })
    const panel = await open()
    const heading = within(panel).getByRole('heading', { name: 'Sections retrieved' })
    expect(heading.parentElement).toHaveTextContent('None')
  })
})

describe('WorkTrace: the numbering work', () => {
  it('takes citations as numbered, and does not number them again', () => {
    const spy = vi.spyOn(sources, 'numberBySection')
    renderTrace({ citations: apiCitations() })
    expect(spy).not.toHaveBeenCalled()
  })
})

describe('WorkTrace: citations as the API sends them', () => {
  it('numbers cited sections the way the markers and chips do', async () => {
    renderTrace({ citations: numberBySection(apiCitations()) })
    const panel = await open()
    expect(within(panel).getByText('Cited as 1').closest('li')).toHaveTextContent('CA-4.3')
    expect(within(panel).getByText('Cited as 2').closest('li')).toHaveTextContent('§4.3')
    expect(within(panel).queryByText('Cited as 3')).not.toBeInTheDocument()
  })

  it('says a section cited only through its second passage was cited', async () => {
    renderTrace({
      citations: [citation({ marker: 1, passageId: 'CA-4.3~p2' })],
      sections: [
        {
          sectionId: 'CA-4.3',
          passageIds: ['CA-4.3~p1', 'CA-4.3~p2'],
          title: null,
          groupName: null,
        },
      ],
    })
    const panel = await open()
    expect(within(panel).getByText('Cited as 1')).toBeInTheDocument()
    expect(within(panel).queryByText('Not cited')).not.toBeInTheDocument()
  })
})

describe('WorkTrace with a section listed twice', () => {
  it('draws no React key warning, though the API promises each section once', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    renderTrace({
      sections: [
        {
          sectionId: '4.3',
          passageIds: ['p1'],
          title: 'Sick leave',
          groupName: 'Company handbook',
        },
        {
          sectionId: '4.3',
          passageIds: ['p2'],
          title: 'Sick leave',
          groupName: 'Company handbook',
        },
      ],
    })
    const reported = errors.mock.calls.map((call) => String(call[0]) + String(call[1] ?? ''))
    expect(reported.filter((text) => /same key/.test(text))).toEqual([])
    errors.mockRestore()
  })
})

describe('WorkTrace: the time-off tools', () => {
  it('words the reads and the propose tools plainly and shows no request id', async () => {
    const id = '3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b'
    const { container } = renderTrace({
      toolCalls: [
        toolCall({ name: 'check_time_off', inputSummary: 'start=2026-10-30, end=2026-10-30' }),
        toolCall({ name: 'propose_time_off_decision', inputSummary: `approve request ${id}` }),
        toolCall({ name: 'propose_cancel_time_off', inputSummary: `cancel request ${id}` }),
      ],
    })
    const panel = await open()
    expect(within(panel).getByText('Checked your time off')).toBeInTheDocument()
    expect(within(panel).getAllByText('Prepared a confirm card')).toHaveLength(2)
    expect(container.textContent).not.toContain(id)
    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/)
  })
})
