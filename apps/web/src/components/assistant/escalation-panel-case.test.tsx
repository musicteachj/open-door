import { screen, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { CASE_BULLETS, PREFILL, SENT_LINE } from '@/app/gallery/fixtures/cases'
import { CaseForm } from '@/components/cases/case-form'
import { CaseSent } from '@/components/cases/case-sent'
import { MY_CASES_LINK } from '@/components/cases/labels'
import { useCaseDisclosure } from '@/components/cases/use-case-disclosure'
import { DANA } from '@/test/assistant-fixtures'
import { renderWithRouter } from '@/test/render-with-router'
import { EscalationPanel, type EscalationPanelProps } from './escalation-panel'

vi.mock('@/lib/announce', () => ({ announce: vi.fn<() => void>(), resetAnnouncer: () => {} }))

const CRISIS = '- If you are in danger, call 911.'

function panel(props: Partial<EscalationPanelProps> & { kind: EscalationPanelProps['kind'] }) {
  return renderWithRouter(
    <EscalationPanel
      message={props.kind === 'crisis' ? CRISIS : 'Text.'}
      contacts={[DANA]}
      {...props}
    />,
  )
}

const caseButton = () => screen.queryByRole('button', { name: 'Open a confidential case' })

describe('EscalationPanel: the case button', () => {
  it.each(['sensitive', 'crisis'] as const)(
    'has no button or case area for %s without offerCase',
    (kind) => {
      panel({ kind, caseArea: <div>AREA</div> })
      expect(caseButton()).not.toBeInTheDocument()
      expect(screen.queryByText('AREA')).not.toBeInTheDocument()
    },
  )

  it('has no button and no area for the unavailable panel, whatever else it is given', () => {
    panel({ kind: 'unavailable', offerCase: true, caseArea: <div>AREA</div> })
    expect(caseButton()).not.toBeInTheDocument()
    expect(screen.queryByText('AREA')).not.toBeInTheDocument()
  })

  it('puts a primary button with a lock after the §7.2 link on the sensitive panel', () => {
    panel({ kind: 'sensitive', offerCase: true })
    const button = caseButton()!
    expect(button.querySelector('svg.lucide-lock')).not.toBeNull()
    expect(button).toHaveClass('bg-primary')
    const link = screen.getByRole('link', { name: 'How confidential HR cases work, §7.2' })
    expect(link.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('puts a secondary button after the contacts on the crisis panel, after the crisis text', () => {
    panel({ kind: 'crisis', offerCase: true })
    const button = caseButton()!
    expect(button).toHaveClass('bg-surface-raised', 'border-border-strong')
    expect(button).not.toHaveClass('bg-primary')
    const contacts = screen.getByRole('heading', { name: 'HR contacts' })
    expect(contacts.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const crisis = screen.getByRole('link', { name: 'call 911' })
    expect(crisis.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('calls onOpenCase when pressed, and hands its ref to the caller', async () => {
    const onOpenCase = vi.fn<() => void>()
    const ref = { current: null as HTMLButtonElement | null }
    const { user } = panel({ kind: 'sensitive', offerCase: true, onOpenCase, openCaseRef: ref })
    await user.click(caseButton()!)
    expect(onOpenCase).toHaveBeenCalledTimes(1)
    expect(ref.current).toBe(caseButton())
  })

  it.each([false, null, undefined])('treats %s as no case area, and shows the button', (area) => {
    panel({ kind: 'sensitive', offerCase: true, caseArea: area })
    expect(caseButton()).toBeInTheDocument()
  })

  it('replaces the button with the case area, full panel width, outside the padded body', () => {
    panel({ kind: 'sensitive', offerCase: true, caseArea: <div data-testid="area">AREA</div> })
    expect(caseButton()).not.toBeInTheDocument()
    const region = screen.getByRole('region')
    const area = screen.getByTestId('area')
    // A direct child of the panel, after the band and the body.
    expect(area.parentElement).toBe(region)
    expect(region.lastElementChild).toBe(area)
  })
})

function Harness({ kind }: { kind: 'sensitive' | 'crisis' }) {
  const disclosure = useCaseDisclosure()
  const [sent, setSent] = useState(false)
  return (
    <EscalationPanel
      kind={kind}
      message={kind === 'crisis' ? CRISIS : 'Text.'}
      contacts={[DANA]}
      offerCase
      onOpenCase={disclosure.open}
      openCaseRef={disclosure.buttonRef}
      caseArea={
        sent ? (
          <CaseSent variant="panel" state="sent" sentLine={SENT_LINE} link={MY_CASES_LINK} />
        ) : disclosure.isOpen ? (
          <CaseForm
            variant="panel"
            bullets={CASE_BULLETS}
            prefill={PREFILL}
            onCancel={disclosure.close}
            onSend={() => setSent(true)}
          />
        ) : null
      }
    />
  )
}

describe.each(['sensitive', 'crisis'] as const)(
  'the case button and form on the %s panel',
  (kind) => {
    it('opens the form with focus on its heading', async () => {
      const { user } = renderWithRouter(<Harness kind={kind} />)
      await user.click(caseButton()!)
      expect(caseButton()).not.toBeInTheDocument()
      expect(
        screen.getByRole('heading', { level: 3, name: 'Open a confidential case' }),
      ).toHaveFocus()
    })

    it('returns focus to the button that opened the form on Not now', async () => {
      const { user } = renderWithRouter(<Harness kind={kind} />)
      await user.click(caseButton()!)
      await user.click(screen.getByRole('button', { name: 'Not now' }))
      expect(
        screen.queryByRole('heading', { name: 'Open a confidential case' }),
      ).not.toBeInTheDocument()
      expect(caseButton()).toHaveFocus()
    })

    it('moves focus to the sent line after sending, and the button stays gone', async () => {
      const { user } = renderWithRouter(<Harness kind={kind} />)
      await user.click(caseButton()!)
      await user.click(screen.getByRole('radio', { name: 'Pay concern' }))
      await user.click(screen.getByRole('button', { name: 'Send to HR' }))
      expect(screen.getByRole('status')).toHaveFocus()
      expect(caseButton()).not.toBeInTheDocument()
      expect(within(screen.getByRole('region')).getByRole('status')).toBeInTheDocument()
    })
  },
)
