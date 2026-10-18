import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { AnswerFooter, Feedback, type FeedbackSubmission } from './feedback'
import { WorkTrace } from './work-trace'

type Status = 'idle' | 'sending' | 'sent' | 'error'

// A caller like Stage 6's: the status comes from a mutation, so the harness moves it on submit.
function Harness({
  onSubmit = () => {},
  result = 'sent',
  initialStatus = 'idle',
  errorMessage = 'The feedback could not be saved.',
}: {
  onSubmit?: (feedback: FeedbackSubmission) => void
  result?: 'sent' | 'error'
  initialStatus?: Status
  errorMessage?: string
}) {
  const [status, setStatus] = useState<Status>(initialStatus)
  const handle = (feedback: FeedbackSubmission) => {
    onSubmit(feedback)
    setStatus(result)
  }
  return status === 'error' ? (
    <Feedback status="error" errorMessage={errorMessage} onSubmit={handle} />
  ) : (
    <Feedback status={status} onSubmit={handle} />
  )
}

const no = () => screen.getByRole('button', { name: 'No' })
const yes = () => screen.getByRole('button', { name: 'Yes' })
const reasonBox = () => screen.getByRole('textbox', { name: /What was wrong/ })

describe('Feedback: asking', () => {
  it('asks "Was this right?" with Yes and No in a labeled group', () => {
    render(<Harness />)
    const group = screen.getByRole('group', { name: 'Was this right?' })
    expect(group).toContainElement(yes())
    expect(group).toContainElement(no())
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('sends Yes at once, and moves focus to the thank-you', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness onSubmit={onSubmit} />)
    await userEvent.click(yes())
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ helpful: true })
    const thanks = screen.getByRole('status')
    expect(thanks).toHaveTextContent('Thanks for the feedback.')
    expect(thanks).toHaveFocus()
    expect(screen.queryByRole('button', { name: 'Yes' })).not.toBeInTheDocument()
  })
})

describe('Feedback: No and the reason', () => {
  it('shows No as pressed, opens the form, and focuses the box', async () => {
    render(<Harness />)
    expect(no()).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(no())
    expect(no()).toHaveAttribute('aria-pressed', 'true')
    expect(reasonBox()).toHaveFocus()
    expect(reasonBox()).toHaveAttribute('placeholder', 'For example, it cited the wrong state')
    expect(screen.getByText('Optional')).toBeInTheDocument()
    expect(screen.getByText('0 of 500 characters')).toBeInTheDocument()
    expect(reasonBox()).toHaveAccessibleDescription('0 of 500 characters')
  })

  it('puts the counter on its own row below sm, above the buttons, which sit at the end', async () => {
    render(<Harness />)
    await userEvent.click(no())
    const counter = screen.getByText('0 of 500 characters')
    expect(counter.parentElement).toHaveClass('flex-wrap')
    expect(counter).toHaveClass('max-sm:basis-full', 'sm:flex-1')
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveClass('max-sm:ml-auto')
  })

  it('counts what is typed', async () => {
    render(<Harness />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), 'Wrong state')
    expect(screen.getByText('11 of 500 characters')).toBeInTheDocument()
  })

  it('returns focus to No when Cancel closes the form', async () => {
    render(<Harness />)
    await userEvent.click(no())
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(no()).toHaveFocus()
    expect(no()).toHaveAttribute('aria-pressed', 'false')
  })

  it('keeps nothing from a canceled reason', async () => {
    render(<Harness />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), 'draft')
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await userEvent.click(no())
    expect(reasonBox()).toHaveValue('')
  })

  it('sends the reason, then moves focus to the thank-you', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness onSubmit={onSubmit} />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), 'It cited the wrong state.')
    await userEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({
      helpful: false,
      reason: 'It cited the wrong state.',
    })
    const thanks = screen.getByRole('status')
    expect(thanks).toHaveTextContent('Thanks for the feedback.')
    expect(thanks).toHaveFocus()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('sends No with no reason when the box is empty or only spaces', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness onSubmit={onSubmit} />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), '   ')
    await userEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ helpful: false })
  })

  it('sends the reason trimmed, as the API stores it', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness onSubmit={onSubmit} />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), '  too short  ')
    await userEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ helpful: false, reason: 'too short' })
  })

  it('takes 500 characters and refuses a 501st, counting the way the API does', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness onSubmit={onSubmit} />)
    await userEvent.click(no())
    await userEvent.click(reasonBox())
    await userEvent.paste('a'.repeat(500))
    expect(screen.getByText('500 of 500 characters')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send feedback' })).toBeEnabled()
    await userEvent.paste('a')
    expect(screen.getByText('501 of 500 characters')).toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'Send feedback' })
    // Like the composer's Ask: aria-disabled, so it stays focusable, and pressing it goes to the box.
    expect(send).toHaveAttribute('aria-disabled', 'true')
    expect(send).toBeEnabled()
    await userEvent.click(send)
    expect(onSubmit).not.toHaveBeenCalled()
    expect(reasonBox()).toHaveFocus()
  })

  it('is not aria-disabled when the reason fits', async () => {
    render(<Harness />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), 'short')
    expect(screen.getByRole('button', { name: 'Send feedback' })).not.toHaveAttribute(
      'aria-disabled',
    )
  })

  it('counts an emoji as one character, and leaves out the spaces around the text', async () => {
    render(<Harness />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), '  ok 👍 ')
    expect(screen.getByText('4 of 500 characters')).toBeInTheDocument()
  })

  it('trims like the API does: U+001F around a reason does not count, and does not send', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness onSubmit={onSubmit} />)
    await userEvent.click(no())
    await userEvent.click(reasonBox())
    await userEvent.paste(`\u001f${'a'.repeat(500)}\u001f`)
    expect(screen.getByText('500 of 500 characters')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ helpful: false, reason: 'a'.repeat(500) })
  })

  it('sends No with no reason when the box holds only U+001F', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness onSubmit={onSubmit} />)
    await userEvent.click(no())
    await userEvent.click(reasonBox())
    await userEvent.paste('\u001f')
    await userEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ helpful: false })
  })

  it('does not set maxLength, which would cut a paste without saying so', async () => {
    render(<Harness />)
    await userEvent.click(no())
    expect(reasonBox()).not.toHaveAttribute('maxlength')
  })
})

describe('Feedback: sending and failing', () => {
  it('says it is sending, and ignores a second press', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness initialStatus="sending" onSubmit={onSubmit} />)
    await userEvent.click(yes())
    await userEvent.click(no())
    expect(onSubmit).not.toHaveBeenCalled()
    expect(yes()).toHaveAttribute('aria-busy', 'true')
  })

  it('keeps what was typed and shows the error as an alert when sending the reason fails', async () => {
    render(<Harness result="error" errorMessage="Feedback is already recorded for this answer." />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), 'It cited the wrong state.')
    await userEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Feedback is already recorded for this answer.',
    )
    expect(reasonBox()).toHaveValue('It cited the wrong state.')
    expect(screen.queryByText('Thanks for the feedback.')).not.toBeInTheDocument()
  })

  it('shows an error from Yes outside the reason form, even with the form open', async () => {
    render(<Harness result="error" errorMessage="Could not save." />)
    await userEvent.click(no())
    await userEvent.click(yes())
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Could not save.')
    const form = reasonBox().closest('form')!
    expect(form).not.toContainElement(alert)
    expect(reasonBox()).toBeInTheDocument()
  })

  it('shows an error from sending the reason inside the form, and a later Yes error outside it', async () => {
    render(<Harness result="error" errorMessage="Could not save." />)
    await userEvent.click(no())
    await userEvent.type(reasonBox(), 'wrong state')
    await userEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    const form = reasonBox().closest('form')!
    expect(form).toContainElement(screen.getByRole('alert'))
    await userEvent.click(yes())
    expect(form).not.toContainElement(screen.getByRole('alert'))
    expect(screen.getAllByRole('alert')).toHaveLength(1)
  })

  it('moves the error into the form when the reason is sent after a Yes failed', async () => {
    render(<Harness result="error" errorMessage="Could not save." />)
    await userEvent.click(no())
    await userEvent.click(yes())
    await userEvent.type(reasonBox(), 'wrong state')
    await userEvent.click(screen.getByRole('button', { name: 'Send feedback' }))
    expect(reasonBox().closest('form')).toContainElement(screen.getByRole('alert'))
    expect(screen.getAllByRole('alert')).toHaveLength(1)
  })

  it('shows an error inside a form that starts open, as the gallery draws it', () => {
    render(
      <Feedback status="error" errorMessage="Could not save." onSubmit={() => {}} defaultOpen />,
    )
    expect(reasonBox().closest('form')).toContainElement(screen.getByRole('alert'))
  })

  it('shows the error when Yes fails, and leaves Yes and No to try again', async () => {
    const onSubmit = vi.fn<(feedback: FeedbackSubmission) => void>()
    render(<Harness result="error" onSubmit={onSubmit} errorMessage="Could not save." />)
    await userEvent.click(yes())
    expect(screen.getByRole('alert')).toHaveTextContent('Could not save.')
    expect(yes()).toHaveFocus()
    await userEvent.click(yes())
    expect(onSubmit).toHaveBeenCalledTimes(2)
  })
})

describe('Feedback: already given', () => {
  it('shows the thank-you for a turn that has feedback, without taking focus', () => {
    render(
      <>
        <button type="button">before</button>
        <Feedback status="sent" onSubmit={() => {}} />
      </>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Thanks for the feedback.')
    expect(screen.getByRole('status')).not.toHaveFocus()
    expect(document.body).toHaveFocus()
    expect(screen.queryByRole('button', { name: 'Yes' })).not.toBeInTheDocument()
  })

  it('can start with the reason form open, for a screen that shows that state', () => {
    render(<Feedback status="idle" onSubmit={() => {}} defaultOpen defaultReason="Draft" />)
    expect(reasonBox()).toHaveValue('Draft')
    expect(no()).toHaveAttribute('aria-pressed', 'true')
    expect(reasonBox()).not.toHaveFocus()
  })
})

describe('Feedback: focus that no longer applies', () => {
  // A parent whose state the tests drive, standing in for the feedback request.
  function Controlled({ onSubmit = () => {} }: { onSubmit?: () => void }) {
    const [status, setStatus] = useState<Status>('idle')
    const [renders, setRenders] = useState(0)
    const set = (next: Status) => (
      <button type="button" onClick={() => setStatus(next)}>{`set ${next}`}</button>
    )
    return (
      <>
        {status === 'error' ? (
          <Feedback status="error" errorMessage="Failed." onSubmit={onSubmit} />
        ) : (
          <Feedback status={status} onSubmit={onSubmit} />
        )}
        {set('idle')}
        {set('sending')}
        {set('sent')}
        {set('error')}
        <button
          type="button"
          onClick={() => setRenders((n) => n + 1)}
        >{`render ${renders}`}</button>
      </>
    )
  }
  const setter = (name: string) => screen.getByRole('button', { name })

  it('puts focus in the box when No is pressed again with the form already open', async () => {
    render(<Harness />)
    await userEvent.click(no())
    await userEvent.click(no())
    expect(reasonBox()).toHaveFocus()
  })

  it('does not take focus back to the box when the parent re-renders later', async () => {
    render(<Controlled />)
    await userEvent.click(no())
    await userEvent.click(no())
    await userEvent.click(setter('set sending'))
    expect(setter('set sending')).toHaveFocus()
  })

  it('does not move focus to the thank-you when the send went back to idle and "sent" comes later', async () => {
    render(<Controlled />)
    await userEvent.click(yes())
    await userEvent.click(setter('set sending'))
    await userEvent.click(setter('set idle'))
    await userEvent.click(setter('set sent'))
    expect(setter('set sent')).toHaveFocus()
  })

  it('does not move focus to the thank-you after a failed send either', async () => {
    render(<Controlled />)
    await userEvent.click(yes())
    await userEvent.click(setter('set sending'))
    await userEvent.click(setter('set error'))
    await userEvent.click(setter('set sent'))
    expect(setter('set sent')).toHaveFocus()
  })

  it('keeps the pending thank-you focus across a render while an earlier error is still showing', async () => {
    render(<Controlled />)
    await userEvent.click(setter('set error'))
    await userEvent.click(yes())
    await userEvent.click(screen.getByRole('button', { name: /^render/ }))
    await userEvent.click(setter('set sending'))
    await userEvent.click(setter('set sent'))
    expect(screen.getByRole('status')).toHaveFocus()
  })

  it('still moves focus to the thank-you when Yes goes through sending to sent', async () => {
    render(<Controlled />)
    await userEvent.click(yes())
    await userEvent.click(setter('set sending'))
    // Focus is on the helper button the test pressed, and the thank-you takes it.
    await userEvent.click(setter('set sent'))
    expect(screen.getByRole('status')).toHaveFocus()
  })

  it('disables Cancel while the reason is being sent', () => {
    render(<Feedback status="sending" onSubmit={() => {}} defaultOpen defaultReason="Draft" />)
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    expect(reasonBox()).toHaveValue('Draft')
  })

  it('keeps Cancel on when nothing is being sent', () => {
    render(<Feedback status="idle" onSubmit={() => {}} defaultOpen />)
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
  })
})

describe('AnswerFooter', () => {
  it('holds the feedback row and the "Show your work" button and panel together', () => {
    render(
      <AnswerFooter
        feedback={<Feedback status="idle" onSubmit={() => {}} />}
        work={
          <WorkTrace guard={{ category: 'ordinary' }} toolCalls={[]} sections={[]} citations={[]} />
        }
      />,
    )
    expect(screen.getByRole('group', { name: 'Was this right?' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show your work' })).toBeInTheDocument()
  })

  it('keeps Tab in reading order: Yes, No, the reason form, then Show your work', async () => {
    render(
      <AnswerFooter
        feedback={<Feedback status="idle" onSubmit={() => {}} />}
        work={
          <WorkTrace guard={{ category: 'ordinary' }} toolCalls={[]} sections={[]} citations={[]} />
        }
      />,
    )
    await userEvent.click(no())
    expect(reasonBox()).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Send feedback' })).toHaveFocus()
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Show your work' })).toHaveFocus()
  })

  it('works with only "Show your work", as under an escalation panel', () => {
    render(
      <AnswerFooter
        work={
          <WorkTrace
            guard={{ category: 'sensitive' }}
            toolCalls={[]}
            sections={[]}
            citations={[]}
          />
        }
      />,
    )
    expect(screen.getByRole('button', { name: 'Show your work' })).toBeInTheDocument()
    expect(screen.queryByText('Was this right?')).not.toBeInTheDocument()
  })

  it('puts the two on one row from the small breakpoint up, and on two rows below it', () => {
    render(
      <AnswerFooter
        feedback={<Feedback status="idle" onSubmit={() => {}} />}
        work={
          <WorkTrace guard={{ category: 'ordinary' }} toolCalls={[]} sections={[]} citations={[]} />
        }
      />,
    )
    const footer = document.querySelector('[data-slot="answer-footer"]')!
    expect(footer).toHaveClass('grid', 'grid-cols-1', 'sm:grid-cols-[minmax(0,1fr)_auto]')
    expect(screen.getByRole('button', { name: 'Show your work' })).toHaveClass(
      'sm:col-start-2',
      'sm:row-start-1',
    )
  })
})
