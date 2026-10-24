import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { NoteField } from './note-field'

function Field({ initial = '', disabled = false }: { initial?: string; disabled?: boolean }) {
  const [value, setValue] = useState(initial)
  return <NoteField firstName="Zara" value={value} onChange={setValue} disabled={disabled} />
}

/** An edit the browser reports as a paste, so the field cuts it instead of refusing it. */
function pasteInto(box: HTMLElement, value: string) {
  fireEvent.input(box, { target: { value }, inputType: 'insertFromPaste' })
}

/** An edit the browser reports as typing. */
function typeInto(box: HTMLElement, value: string) {
  fireEvent.input(box, { target: { value }, inputType: 'insertText' })
}

describe('NoteField', () => {
  it('is a four-row textarea named for the person, with the helper and the count', () => {
    render(<Field />)
    const box = screen.getByRole('textbox', { name: 'Note to Zara (optional)' })
    expect(box).toHaveAttribute('rows', '4')
    // No maxlength attribute: it counts UTF-16 units, so the field cuts at 300 characters itself.
    expect(box).not.toHaveAttribute('maxlength')
    expect(screen.getByText('Zara will see this note. Up to 300 characters.')).toBeInTheDocument()
    expect(screen.getByText('0 of 300')).toHaveClass('tabular-nums')
    expect(box).toHaveAccessibleDescription(
      'Zara will see this note. Up to 300 characters. 0 of 300',
    )
  })

  it('counts what is typed', async () => {
    const user = userEvent.setup()
    render(<Field />)
    await user.type(screen.getByRole('textbox'), 'Not that week.')
    expect(screen.getByText('14 of 300')).toBeInTheDocument()
  })

  it('counts a long note as the design does, 77 of 300', () => {
    render(
      <Field initial="Inventory runs November 9 and 10 this year. Could you move this a week later?" />,
    )
    expect(screen.getByText(/ of 300$/)).toBeInTheDocument()
  })

  it('stays silent until the last 20 characters, then says how many are left', () => {
    const { rerender } = render(
      <NoteField firstName="Zara" value={'a'.repeat(279)} onChange={() => {}} />,
    )
    const live = () => document.querySelector('[aria-live="polite"]')!
    expect(live()).toHaveTextContent('')
    expect(live()).toHaveClass('sr-only')
    rerender(<NoteField firstName="Zara" value={'a'.repeat(280)} onChange={() => {}} />)
    expect(live()).toHaveTextContent('20 characters left')
    rerender(<NoteField firstName="Zara" value={'a'.repeat(300)} onChange={() => {}} />)
    expect(live()).toHaveTextContent('0 characters left')
    expect(screen.getByText('300 of 300')).toBeInTheDocument()
  })

  it('is disabled when asked', () => {
    render(<Field disabled />)
    expect(screen.getByRole('textbox')).toBeDisabled()
  })

  it('hands its textarea to a ref, so a dialog can focus it', () => {
    let node: HTMLTextAreaElement | null = null
    render(
      <NoteField
        firstName="Zara"
        value=""
        onChange={() => {}}
        ref={(element) => {
          node = element
        }}
      />,
    )
    expect(node).toBe(screen.getByRole('textbox'))
  })

  it('counts an emoji as one character and never splits it at the limit', async () => {
    const onChange = vi.fn<(value: string) => void>()
    const { rerender } = render(
      <NoteField firstName="Zara" value={'a'.repeat(299)} onChange={onChange} />,
    )
    expect(screen.getByRole('textbox')).not.toHaveAttribute('maxlength')
    const box = screen.getByRole('textbox')
    // One more character fits, and it is a whole emoji (two UTF-16 units).
    fireEvent.change(box, { target: { value: 'a'.repeat(299) + '😀' } })
    expect(onChange).toHaveBeenLastCalledWith('a'.repeat(299) + '😀')
    // Past the limit it is cut back to 300 characters, without leaving half an emoji.
    pasteInto(box, 'a'.repeat(299) + '😀😀')
    expect(onChange).toHaveBeenLastCalledWith('a'.repeat(299) + '😀')
    rerender(<NoteField firstName="Zara" value={'a'.repeat(299) + '😀'} onChange={onChange} />)
    expect(screen.getByText('300 of 300')).toBeInTheDocument()
  })

  it('counts the trimmed text, as the server does, so spaces around a note use none of the limit', () => {
    const onChange = vi.fn<(value: string) => void>()
    render(<NoteField firstName="Zara" value="" onChange={onChange} />)
    const box = screen.getByRole('textbox')
    const note = 'a'.repeat(299)
    fireEvent.change(box, { target: { value: `\n\n${note}b  ` } })
    expect(onChange).toHaveBeenLastCalledWith(`\n\n${note}b  `)
    pasteInto(box, `\n\n${note}bc  `)
    expect(onChange).toHaveBeenLastCalledWith(`\n\n${note}b`)
  })

  it('lets typing continue at the end while the trimmed text is under the limit', () => {
    const onChange = vi.fn<(value: string) => void>()
    render(<NoteField firstName="Zara" value="" onChange={onChange} />)
    const typed = `  ${'a'.repeat(297)}  x`
    fireEvent.change(screen.getByRole('textbox'), { target: { value: typed } })
    expect(onChange).toHaveBeenLastCalledWith(typed)
  })

  it('refuses a typed character in the middle once the note is at the limit', () => {
    const onChange = vi.fn<(value: string) => void>()
    render(<NoteField firstName="Zara" value={'a'.repeat(300)} onChange={onChange} />)
    const typed = 'a'.repeat(150) + 'X' + 'a'.repeat(150)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: typed } })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('cuts a paste that arrives over the limit at the end', () => {
    const onChange = vi.fn<(value: string) => void>()
    render(<NoteField firstName="Zara" value={'a'.repeat(295)} onChange={onChange} />)
    pasteInto(screen.getByRole('textbox'), 'a'.repeat(295) + 'bcdefghij')
    expect(onChange).toHaveBeenLastCalledWith('a'.repeat(295) + 'bcdef')
  })

  it('cuts a paste that replaces a selection, even when it adds only one character', () => {
    const onChange = vi.fn<(value: string) => void>()
    render(<NoteField firstName="Zara" value={'a'.repeat(300)} onChange={onChange} />)
    // 50 selected characters replaced by 51 pasted ones: a net gain of one.
    pasteInto(screen.getByRole('textbox'), 'a'.repeat(250) + 'b'.repeat(51))
    expect(onChange).toHaveBeenLastCalledWith('a'.repeat(250) + 'b'.repeat(50))
  })

  it('refuses a typed character at the limit, by the input type and not the length', () => {
    const onChange = vi.fn<(value: string) => void>()
    render(<NoteField firstName="Zara" value={'a'.repeat(300)} onChange={onChange} />)
    typeInto(screen.getByRole('textbox'), 'a'.repeat(250) + 'b'.repeat(51))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('accepts an edit that removes characters from a value that is already over the limit', () => {
    const onChange = vi.fn<(value: string) => void>()
    render(<NoteField firstName="Zara" value={'a'.repeat(350)} onChange={onChange} />)
    fireEvent.input(screen.getByRole('textbox'), {
      target: { value: 'a'.repeat(349) },
      inputType: 'deleteContentBackward',
    })
    expect(onChange).toHaveBeenCalledWith('a'.repeat(349))
  })

  it('caps the raw text at the 20,000 characters the API accepts', () => {
    const onChange = vi.fn<(value: string) => void>()
    const { rerender } = render(<NoteField firstName="Zara" value="" onChange={onChange} />)
    pasteInto(screen.getByRole('textbox'), ' '.repeat(25_000) + 'a')
    expect([...(onChange.mock.lastCall![0] as string)]).toHaveLength(20_000)
    onChange.mockClear()
    rerender(<NoteField firstName="Zara" value={' '.repeat(20_000)} onChange={onChange} />)
    typeInto(screen.getByRole('textbox'), ' '.repeat(20_001))
    expect(onChange).not.toHaveBeenCalled()
  })
})
