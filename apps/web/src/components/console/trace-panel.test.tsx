import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import {
  sectionTitle,
  T_0914_REFUSED,
  T_0948_FAILED,
  T_1002_FALLBACK,
  T_1031_ANSWERED,
  T_1033_CARD,
  T_1038_INJECTION,
} from '@/app/gallery/fixtures/console'
import { TracePanel } from './trace-panel'

const base = { timeZone: 'America/Denver', sectionTitle, onClose: () => {} }
const section = (name: string) =>
  within(screen.getByRole('heading', { level: 3, name }).closest('section') as HTMLElement)

describe('TracePanel', () => {
  it('is an aside named by its heading, titled with the time, role, and place', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    const aside = screen.getByRole('complementary', { name: '10:31 AM · Employee · Oakland, CA' })
    expect(within(aside).getByRole('heading', { level: 2 })).toHaveAttribute('tabindex', '-1')
    expect(within(aside).getByText('Turn trace')).toBeInTheDocument()
  })

  it('says a section is not in the handbook when it has no title', () => {
    render(<TracePanel turn={{ ...T_1031_ANSWERED, sectionsRetrieved: ['ZZ-9.9'] }} {...base} />)
    const note = section('Sections retrieved').getByText('Not in the current handbook')
    expect(note).toHaveClass('text-ink-muted')
  })

  it('shows the nine sections in order', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      'Outcome',
      'Safety check',
      'Tools called',
      'Sections retrieved',
      'Card offered',
      'Model',
      'Tokens',
      'Cost',
      'Timings',
    ])
  })

  it('closes with the X and with Escape', async () => {
    const onClose = vi.fn<() => void>()
    render(<TracePanel turn={T_1031_ANSWERED} {...base} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Close trace' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('moves focus to the heading when it opens and when another turn replaces it', () => {
    const { rerender } = render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    const heading = screen.getByRole('heading', { level: 2 })
    expect(heading).toHaveFocus()
    screen.getByRole('button', { name: 'Close trace' }).focus()
    rerender(<TracePanel turn={T_1033_CARD} {...base} />)
    expect(screen.getByRole('heading', { level: 2 })).toHaveFocus()
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('10:33 AM')
  })

  it('leaves focus alone when told not to take it', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} focusOnOpen={false} />)
    expect(document.body).toHaveFocus()
  })

  it('shows the outcome, and a refusal’s category only', () => {
    render(<TracePanel turn={T_0914_REFUSED} {...base} />)
    const outcome = section('Outcome')
    expect(outcome.getByText('Refused by the model')).toBeInTheDocument()
    expect(outcome.getByText('Category: general harms')).toBeInTheDocument()
  })

  it('shows the safety check with its time and the injection tag', () => {
    render(<TracePanel turn={T_1038_INJECTION} {...base} />)
    const safety = section('Safety check')
    expect(safety.getByText('Ordinary')).toBeInTheDocument()
    expect(safety.getByText('· 980 ms')).toBeInTheDocument()
    expect(safety.getByText(/Possible prompt/)).toBeInTheDocument()
  })

  it('lists tools in order with a neutral label, the tool’s name, its time, and OK', () => {
    render(<TracePanel turn={T_1033_CARD} {...base} />)
    const items = section('Tools called').getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Checked time offcheck_time_off85 msOK')
    expect(items[1]).toHaveTextContent('Prepared a confirm cardpropose_time_off_request120 msOK')
    expect(within(items[0]!).getByText('check_time_off').tagName).toBe('CODE')
  })

  it('shows a failed tool as Failed, in the danger color', () => {
    render(<TracePanel turn={T_0948_FAILED} {...base} />)
    const item = section('Tools called').getByRole('listitem')
    expect(item).toHaveTextContent('Checked time offcheck_time_off3.0 sFailed')
    expect(within(item).getByText('Failed').querySelector('svg')).toHaveClass('text-danger')
  })

  it('says "None" for no tools, no sections, and no card', () => {
    render(<TracePanel turn={T_1038_INJECTION} {...base} />)
    for (const name of ['Tools called', 'Sections retrieved', 'Card offered'])
      expect(section(name).getByText('None')).toBeInTheDocument()
  })

  it('reads a missing effort as None to assistive tech, with no dash in a code', () => {
    render(
      <TracePanel turn={{ ...T_1031_ANSWERED, effort: null, promptVersion: null }} {...base} />,
    )
    const model = section('Model')
    const effort = model.getByText('Effort').nextElementSibling as HTMLElement
    expect(effort).toHaveTextContent('–None')
    expect(within(effort).getByText('None')).toHaveClass('sr-only')
    const prompt = model.getByText('Prompt').nextElementSibling as HTMLElement
    expect(prompt.querySelector('code')).toBeNull()
  })

  it('shows sections retrieved with titles, Cited or Not cited', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    const rows = section('Sections retrieved').getAllByRole('listitem')
    expect(rows[0]).toHaveTextContent('CA-4.3Sick leave (California)Cited')
    expect(rows[1]).toHaveTextContent('4.3Sick leaveNot cited')
    expect(rows[2]).toHaveTextContent('4.1Paid time offNot cited')
    expect(within(rows[0]!).getByText('Cited')).toHaveClass('font-semibold', 'text-ink')
    expect(within(rows[1]!).getByText('Not cited')).toHaveClass('text-ink-muted')
  })

  it('keeps the number and the cited state of a section with no known title', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} sectionTitle={() => undefined} />)
    expect(section('Sections retrieved').getAllByRole('listitem')[0]).toHaveTextContent(
      'CA-4.3Not in the current handbookCited',
    )
  })

  it('names the card offered by its action', () => {
    render(<TracePanel turn={T_1033_CARD} {...base} />)
    expect(section('Card offered').getByText('Time-off request')).toBeInTheDocument()
  })

  it('shows the model and its versions', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    const model = section('Model')
    expect(model.getByText('claude-opus-5-5').tagName).toBe('CODE')
    expect(model.getByText('low')).toBeInTheDocument()
    expect(model.getAllByText('2026-11.2')).toHaveLength(2)
    expect(model.queryByText(/after a fallback/)).toBeNull()
  })

  it('names the model that served after a fallback', () => {
    render(<TracePanel turn={T_1002_FALLBACK} {...base} />)
    const model = section('Model')
    expect(model.getByText('claude-opus-5-5')).toBeInTheDocument()
    expect(model.getByText(/Served by/)).toHaveTextContent(
      'Served by claude-sonnet-5-5 after a fallback',
    )
  })

  it('counts cache writes once: input is the plain input plus the cache reads', () => {
    render(<TracePanel turn={{ ...T_1031_ANSWERED, cacheWriteTokens: 3000 }} {...base} />)
    const tokens = section('Tokens')
    expect(tokens.getByText('12,400 (10,200 from cache)')).toBeInTheDocument()
    expect(tokens.getByText('Cache writes').nextSibling).toHaveTextContent('3,000')
  })

  it('shows the input with what came from the cache, then output and cache writes', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    const tokens = section('Tokens')
    expect(tokens.getByText('12,400 (10,200 from cache)')).toBeInTheDocument()
    expect(tokens.getByText('470')).toBeInTheDocument()
    expect(tokens.getByText('Cache writes').nextSibling).toHaveTextContent('0')
  })

  it('shows the cost and that it includes the safety check', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    const cost = section('Cost')
    expect(cost.getByText('$0.021')).toBeInTheDocument()
    expect(cost.getByText('Includes the safety check')).toBeInTheDocument()
  })

  it('shows the three timings, and "No answer text" when there was no first token', () => {
    const { unmount } = render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    let timings = section('Timings')
    expect(timings.getByText('640 ms')).toBeInTheDocument()
    expect(timings.getByText('1.4 s')).toBeInTheDocument()
    expect(timings.getByText('4.1 s')).toBeInTheDocument()
    unmount()
    render(<TracePanel turn={T_0948_FAILED} {...base} />)
    timings = section('Timings')
    expect(timings.getByText('No answer text')).toBeInTheDocument()
  })

  it('is 420 px wide with a left border', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} />)
    expect(screen.getByRole('complementary')).toHaveClass('w-panel', 'border-l')
  })

  it('can sit in a dialog: its heading is the dialog’s title and it is not a landmark', () => {
    render(<TracePanel turn={T_1031_ANSWERED} {...base} landmark={false} />)
    expect(screen.queryByRole('complementary')).toBeNull()
  })
})
