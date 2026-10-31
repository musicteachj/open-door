import { useState, type ReactNode } from 'react'
import { EscalationPanel } from '@/components/assistant/escalation-panel'
import { CaseForm, type CaseFormProps } from '@/components/cases/case-form'
import { CaseSent } from '@/components/cases/case-sent'
import { OpenCaseButton } from '@/components/cases/open-case-button'
import { MY_CASES_LINK, WRITE_TO_HR_LINK, YOUR_CASES_LINK } from '@/components/cases/labels'
import { useCaseDisclosure } from '@/components/cases/use-case-disclosure'
import { Group, Section } from '../gallery-parts'
import {
  CASE_BULLETS,
  PREFILL,
  SENT_LINE,
  SHORT_PREFILL,
  SSN_WORDS,
  WAITING_LIMIT,
  wordsOfLength,
} from '../fixtures/cases'
import { CRISIS_TEXT, DANA, SENSITIVE_TEXT, UNAVAILABLE_TEXT } from './conversation-fixtures'

// The case button, the confidential-case form, and the sent and limit lines (screen 11), each in
// the place the design draws it: at the foot of the 680 px HR panel, or in a card on My cases. The
// frames call nothing. The first is live: open it, press Not now, press Send to HR with nothing
// chosen to see the errors, then choose and send. The others are fixed frames, with the form's
// own focus left alone so the page does not jump.

const noop = () => {}

function Panel({ children }: { children: ReactNode }) {
  return <div className="w-[680px] max-w-full">{children}</div>
}

function Page({ children }: { children: ReactNode }) {
  return <div className="flex w-[760px] max-w-full flex-col gap-6">{children}</div>
}

/** A form frame: fixed, with its own focus left alone. */
function frame(extra: Partial<CaseFormProps> = {}) {
  return (
    <CaseForm
      variant="panel"
      bullets={CASE_BULLETS}
      prefill={PREFILL}
      onSend={noop}
      onCancel={noop}
      focusHeadingOnMount={false}
      {...extra}
    />
  )
}

function SensitivePanel({ caseArea, ...rest }: { caseArea?: ReactNode; offerCase?: boolean }) {
  return (
    <EscalationPanel
      kind="sensitive"
      message={SENSITIVE_TEXT}
      contacts={[DANA]}
      offerCase
      caseArea={caseArea}
      {...rest}
    />
  )
}

/** The live panel: the button opens the form, Not now closes it, and a send shows the sent line. */
function LivePanel() {
  const disclosure = useCaseDisclosure()
  const [sent, setSent] = useState(false)
  return (
    <EscalationPanel
      kind="sensitive"
      message={SENSITIVE_TEXT}
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
            onSend={() => {
              setSent(true)
              disclosure.dismiss()
            }}
          />
        ) : null
      }
    />
  )
}

function PageButton() {
  const disclosure = useCaseDisclosure()
  const { buttonRef, open } = disclosure
  return disclosure.isOpen ? (
    <CaseForm variant="page" bullets={CASE_BULLETS} onSend={noop} onCancel={disclosure.close} />
  ) : (
    <OpenCaseButton ref={buttonRef} onClick={open} />
  )
}

export function CasesSections() {
  return (
    <>
      <Group title="Case button, form, and sent line: in the HR panel">
        <Section id="case-sensitive-offer" title="Sensitive panel with the case button (live)">
          <Panel>
            <LivePanel />
          </Panel>
        </Section>
        <Section id="case-form-open" title="Form open, nothing chosen, prefilled">
          <Panel>
            <SensitivePanel caseArea={frame()} />
          </Panel>
        </Section>
        <Section id="case-form-category" title="Form with a category chosen">
          <Panel>
            <SensitivePanel caseArea={frame({ initialCategory: 'harassment_discrimination' })} />
          </Panel>
        </Section>
        <Section id="case-form-short-reply" title="Form prefilled with a short reply">
          <Panel>
            <SensitivePanel
              caseArea={frame({
                prefill: SHORT_PREFILL,
                initialCategory: 'harassment_discrimination',
              })}
            />
          </Panel>
        </Section>
        <Section id="case-form-errors" title="Form with a category error and a personal-data error">
          <Panel>
            <SensitivePanel caseArea={frame({ prefill: SSN_WORDS, validateOnMount: true })} />
          </Panel>
        </Section>
        <Section id="case-form-limit" title="Form at 4,000 characters">
          <Panel>
            <SensitivePanel
              caseArea={frame({ prefill: wordsOfLength(4000), initialCategory: 'pay' })}
            />
          </Panel>
        </Section>
        <Section id="case-form-sending" title="Form sending">
          <Panel>
            <SensitivePanel
              caseArea={frame({ sending: true, initialCategory: 'harassment_discrimination' })}
            />
          </Panel>
        </Section>
        <Section id="case-form-send-failed" title="Form after a send failed">
          <Panel>
            <SensitivePanel
              caseArea={frame({ sendFailed: true, initialCategory: 'harassment_discrimination' })}
            />
          </Panel>
        </Section>
        <Section id="case-sent-panel" title="Sent, in the panel">
          <Panel>
            <SensitivePanel
              caseArea={
                <CaseSent
                  variant="panel"
                  state="sent"
                  sentLine={SENT_LINE}
                  link={MY_CASES_LINK}
                  focusOnMount={false}
                />
              }
            />
          </Panel>
        </Section>
        <Section id="case-limit-panel" title="Five cases waiting, in the panel">
          <Panel>
            <SensitivePanel
              caseArea={
                <CaseSent
                  variant="panel"
                  state="limit"
                  limitLine={WAITING_LIMIT}
                  link={YOUR_CASES_LINK}
                />
              }
            />
          </Panel>
        </Section>
        <Section id="case-crisis-offer" title="Crisis panel with the secondary case button">
          <Panel>
            <EscalationPanel kind="crisis" message={CRISIS_TEXT} contacts={[DANA]} offerCase />
          </Panel>
        </Section>
        <Section id="case-unavailable-write-to-hr" title="Can't answer right now, with Write to HR">
          <Panel>
            <EscalationPanel
              kind="unavailable"
              message={UNAVAILABLE_TEXT}
              contacts={[DANA]}
              onTryAgain={noop}
              writeToHr={WRITE_TO_HR_LINK}
            />
          </Panel>
        </Section>
      </Group>
      <Group title="Case form and sent line: on My cases">
        <Section id="case-page-form" title="Form on the page, empty (live)">
          <Page>
            <PageButton />
          </Page>
        </Section>
        <Section id="case-page-form-empty" title="Form on the page, open and empty">
          <Page>{frame({ variant: 'page', prefill: '' })}</Page>
        </Section>
        <Section id="case-page-sent" title="Sent, on the page">
          <Page>
            <CaseSent
              variant="page"
              state="sent"
              sentLine={SENT_LINE}
              link={null}
              focusOnMount={false}
            />
          </Page>
        </Section>
        <Section id="case-page-sent-crisis" title="Sent, on the page, followed by the crisis panel">
          <Page>
            <CaseSent
              variant="page"
              state="sent"
              sentLine={SENT_LINE}
              link={null}
              focusOnMount={false}
            />
            <EscalationPanel kind="crisis" message={CRISIS_TEXT} contacts={[DANA]} />
          </Page>
        </Section>
        <Section id="case-page-limit" title="Five cases waiting, on the page, with the HR contacts">
          <Page>
            <CaseSent
              variant="page"
              state="limit"
              limitLine={WAITING_LIMIT}
              link={null}
              contacts={[DANA]}
            />
          </Page>
        </Section>
      </Group>
    </>
  )
}
