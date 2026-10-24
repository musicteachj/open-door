import { useId, type Ref } from 'react'
import { characterCount, trimLikePython } from '@/components/assistant/text-count'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { NOTE_LIMIT_CHARACTERS, NOTE_WARN_AT_REMAINING, approvalsCopy } from './labels'

type NoteFieldProps = {
  /** The person the note is for: the label reads "Note to Zara (optional)". */
  firstName: string
  value: string
  onChange: (value: string) => void
  disabled?: boolean
  /** The textarea, so a dialog can put focus in it. */
  ref?: Ref<HTMLTextAreaElement>
  className?: string
}

/** The most characters the API accepts in a request body, whatever they are. */
const BODY_LIMIT_CHARACTERS = 20_000

/**
 * The text cut so its trimmed part holds at most 300 characters, as the counter and the server
 * count it (spaces around a note use none of the limit). Each emoji and letter is one character,
 * so a character that takes two UTF-16 units is never split. A `maxlength` attribute counts the
 * units and the raw text, so it cannot agree.
 */
function cutToLimit(text: string): string {
  const trimmed = trimLikePython(text)
  const characters = [...trimmed]
  if (characters.length <= NOTE_LIMIT_CHARACTERS) return text
  const lead = text.slice(0, text.indexOf(trimmed))
  return lead + characters.slice(0, NOTE_LIMIT_CHARACTERS).join('')
}

/**
 * What the field holds after an edit, or null to refuse it. Within the limit the edit stands. Over
 * it, an edit that adds nothing stands; otherwise the kind of edit decides, as the browser reports it: a paste or a drop is cut at the end
 * (even one that replaces a selection and adds a single character), and anything else, a
 * keystroke, is refused, so typing in the middle of a full note never pushes characters off the
 * end.
 */
function afterEdit(previous: string, nextText: string, inputType: string): string | null {
  const bulk = inputType === 'insertFromPaste' || inputType === 'insertFromDrop'
  // The API takes at most 20,000 characters of body, spaces included, so that caps the raw text.
  const rawCount = [...nextText].length
  let next = nextText
  if (rawCount > BODY_LIMIT_CHARACTERS && rawCount > [...previous].length) {
    if (!bulk) return null
    next = [...nextText].slice(0, BODY_LIMIT_CHARACTERS).join('')
  }
  const count = characterCount(next)
  if (count <= NOTE_LIMIT_CHARACTERS) return next
  // An edit that does not add characters (a deletion, a replacement that shrinks) always stands.
  if (count <= characterCount(previous)) return next
  return bulk ? cutToLimit(next) : null
}

/**
 * The optional note on a denial (NoteField.jsx): four rows, a hard limit of 300 characters (cut in code points, not UTF-16 units), and a
 * counter ("77 of 300"). In the last 20 characters a polite live region, for screen readers only,
 * says how many are left.
 */
function NoteField({
  firstName,
  value,
  onChange,
  disabled = false,
  ref,
  className,
}: NoteFieldProps) {
  const id = useId()
  const helperId = `${id}-help`
  const countId = `${id}-count`
  const count = characterCount(value)
  const left = NOTE_LIMIT_CHARACTERS - count
  return (
    <div data-slot="note-field" className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={id} className="text-ui font-semibold text-ink">
        {approvalsCopy.noteLabel(firstName)}
      </label>
      <Textarea
        ref={ref}
        id={id}
        rows={4}
        value={value}
        disabled={disabled}
        aria-describedby={`${helperId} ${countId}`}
        onChange={(event) => {
          const inputType = (event.nativeEvent as InputEvent).inputType ?? ''
          const next = afterEdit(value, event.target.value, inputType)
          if (next !== null) onChange(next)
        }}
        className="min-h-0 py-2.5 text-body"
      />
      <div className="flex justify-between gap-4 text-small text-ink-muted">
        <span id={helperId}>{approvalsCopy.noteHelper(firstName)}</span>
        <span id={countId} className="flex-none tabular-nums">
          {approvalsCopy.noteCount(count)}
        </span>
      </div>
      <span aria-live="polite" className="sr-only">
        {left <= NOTE_WARN_AT_REMAINING ? approvalsCopy.charactersLeft(left) : ''}
      </span>
    </div>
  )
}

export { NoteField }
export type { NoteFieldProps }
