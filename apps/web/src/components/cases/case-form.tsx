import { Lock } from 'lucide-react'
import { useEffect, useId, useLayoutEffect, useRef, useState, type ChangeEvent } from 'react'
import type { Category } from '@/api/generated'
import { Segments } from '@/components/assistant/crisis-segments'
import { linkifyCrisis } from '@/components/assistant/crisis-text'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { ChoiceGroup } from '@/components/timeoff/choice-group'
import { fieldLabelClass, FieldError } from '@/components/timeoff/field-parts'
import { FormMessage } from '@/components/timeoff/form-message'
import { announce } from '@/lib/announce'
import { cn } from '@/lib/utils'
import { afterEdit } from './edit'
import { CATEGORY_OPTIONS, caseCopy, countLine } from './labels'
import { CaseSurface } from './surface'
import { trimLikePython } from '@/components/assistant/text-count'
import { CASE_LIMIT_CHARACTERS, characterCountOf, validateCase, type CaseProblem } from './validate'

/** A reply under this many characters that raised the panel gets the "Add what happened" hint. */
const SHORT_REPLY_CHARACTERS = 40

type CaseSubmission = { submissionId: string; category: Category; text: string }

type CaseFormProps = {
  /** `panel` is the band at the foot of the HR panel (an h3); `page` is the card on My cases (an h2). */
  variant: 'panel' | 'page'
  /** The form's five lines, from the API (`GET /cases/texts`). Never a copy in this app. */
  bullets: string[]
  /** The turn's own question, verbatim. Empty on My cases. */
  prefill?: string
  /** A send is in flight: the fields and "Not now" lock, and Send to HR reads "Sending…". */
  sending?: boolean
  /** The last send failed: the refusal shows above the buttons and the primary reads "Try again". */
  sendFailed?: boolean
  /**
   * What the server refused the words for, after a send the form's own checks let through (the
   * server repeats every check). It shows as the form's own error on the words, and the words
   * take focus. The caller clears it (null) when the next send starts.
   */
  refusal?: 'empty' | 'personal-data' | null
  /** The person pressed Send to HR and everything passed. Each press of a form sends the same `submissionId`. */
  onSend: (input: CaseSubmission) => void
  /** "Not now". The caller closes the form and returns focus to the button that opened it. */
  onCancel: () => void
  /** The heading takes focus when the form opens. Off only for the gallery's static frames. */
  focusHeadingOnMount?: boolean
  /** A category already chosen, for the gallery's static frames. */
  initialCategory?: Category
  /** Shows the errors the first press of Send would, without a press. For the gallery's frames. */
  validateOnMount?: boolean
  className?: string
}

const WORDS_PROBLEMS: CaseProblem[] = ['empty', 'personal-data', 'limit']

/**
 * The confidential-case form (CaseForm.jsx). Not a modal: it opens in place, as a band at the foot
 * of the HR panel or a card on My cases. The AI never opens or submits it: only the person's own
 * press of Send to HR does. The category and the words are the form's own state, kept through a
 * failed send. One `submissionId` is made when the form opens and reused by every press, so a
 * double click or "Try again" can open only one case.
 */
function CaseForm({
  variant,
  bullets,
  prefill = '',
  sending = false,
  sendFailed = false,
  refusal = null,
  onSend,
  onCancel,
  focusHeadingOnMount = true,
  initialCategory,
  validateOnMount = false,
  className,
}: CaseFormProps) {
  const id = useId()
  const [submissionId] = useState(() => crypto.randomUUID())
  const [category, setCategory] = useState<Category | null>(initialCategory ?? null)
  const [text, setText] = useState(prefill)
  const [problems, setProblems] = useState<CaseProblem[]>(() =>
    validateOnMount ? validateCase({ category: initialCategory ?? null, text: prefill }) : [],
  )
  const headingRef = useRef<HTMLHeadingElement>(null)
  const groupRef = useRef<HTMLDivElement>(null)
  const wordsRef = useRef<HTMLTextAreaElement>(null)
  const failureRef = useRef<HTMLDivElement>(null)
  const previousFailed = useRef(sendFailed)
  // Where the caret goes after an insertion was cut, so the person types on after what stayed.
  const caretAfterCut = useRef<number | null>(null)

  useLayoutEffect(() => {
    if (caretAfterCut.current !== null) {
      wordsRef.current?.setSelectionRange(caretAfterCut.current, caretAfterCut.current)
      caretAfterCut.current = null
    }
  }, [text])

  useEffect(() => {
    if (focusHeadingOnMount) headingRef.current?.focus()
    // Once, when the form opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    // Only a failure that arrives while the form is open takes focus.
    if (sendFailed && !previousFailed.current) failureRef.current?.focus()
    previousFailed.current = sendFailed
  }, [sendFailed])

  useEffect(() => {
    if (refusal === null) return
    setProblems([refusal])
    wordsRef.current?.focus()
  }, [refusal])

  const Heading = variant === 'panel' ? 'h3' : 'h2'
  const SubHeading = variant === 'panel' ? 'h4' : 'h3'
  const count = characterCountOf(text)
  const atLimit = count >= CASE_LIMIT_CHARACTERS
  const wordsError = problems.includes('empty')
    ? caseCopy.noWords
    : problems.includes('personal-data')
      ? caseCopy.personalData
      : null
  const categoryError = problems.includes('category')
  const limitError = problems.includes('limit')
  const wordsInvalid = wordsError !== null || limitError
  const hintId = `${id}-hint`
  const countId = `${id}-count`
  const wordsErrorId = `${id}-words-error`
  const categoryErrorId = `${id}-category-error`
  // Empty as the server sees it (Python's strip), and counted in code points like the limit.
  const shortReply =
    trimLikePython(prefill) !== '' && characterCountOf(prefill) < SHORT_REPLY_CHARACTERS

  function submit() {
    if (sending) return
    const found = validateCase({ category, text })
    setProblems(found)
    if (found.length > 0) {
      // A role added to the counter's existing text is often not read, so it is said apart.
      if (found.includes('limit')) announce(countLine(count), 'assertive')
      if (found[0] === 'category') {
        const radios = groupRef.current?.querySelectorAll<HTMLElement>('[role="radio"]')
        const checked = groupRef.current?.querySelector<HTMLElement>('[aria-checked="true"]')
        ;(checked ?? radios?.[0])?.focus()
      } else {
        wordsRef.current?.focus()
      }
      return
    }
    if (category !== null) onSend({ submissionId, category, text })
  }

  function onWordsChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const inputType = (event.nativeEvent as InputEvent).inputType ?? ''
    const edit = afterEdit(text, event.target.value, inputType)
    if (edit === null) return
    // With nothing changed there is no render to move the caret in, so a stale one is not kept.
    caretAfterCut.current = edit.value === text ? null : edit.caret
    setText(edit.value)
    setProblems((found) => found.filter((problem) => !WORDS_PROBLEMS.includes(problem)))
  }

  return (
    <CaseSurface variant={variant} data-slot="case-form" className={className}>
      <div className="flex flex-col gap-5.5 text-ink">
        <Heading
          ref={headingRef}
          tabIndex={-1}
          className="m-0 flex items-center gap-2.5 text-[17px]/6 font-semibold outline-none"
        >
          <Lock aria-hidden="true" className="size-4.5 flex-none text-primary" />
          {caseCopy.heading}
        </Heading>

        <div ref={groupRef} className="flex flex-col gap-2">
          <ChoiceGroup
            label={caseCopy.categoryLabel}
            options={CATEGORY_OPTIONS}
            value={category ?? ''}
            onValueChange={(next) => {
              setCategory(next as Category)
              setProblems((found) => found.filter((problem) => problem !== 'category'))
            }}
            disabled={sending}
            invalid={categoryError}
            describedBy={categoryError ? categoryErrorId : undefined}
            optionsClassName="grid-cols-2 max-sm:grid-cols-1"
          />
          {categoryError && <FieldError id={categoryErrorId}>{caseCopy.noCategory}</FieldError>}
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor={`${id}-words`} className="text-body/[22px] font-semibold">
            {caseCopy.wordsLabel}
          </label>
          <p id={hintId} className="m-0 mb-1 text-ui text-pretty text-ink-muted">
            {shortReply ? caseCopy.shortHint : caseCopy.hint}
          </p>
          <Textarea
            ref={wordsRef}
            id={`${id}-words`}
            rows={6}
            value={text}
            disabled={sending}
            aria-invalid={wordsInvalid || undefined}
            // Ids, so a plain join: `cn` would run tailwind-merge over them.
            aria-describedby={[hintId, countId, wordsError && wordsErrorId]
              .filter(Boolean)
              .join(' ')}
            onChange={onWordsChange}
            className="py-2.5 text-body"
          />
          <div className="flex flex-col items-end gap-1 sm:flex-row sm:items-start sm:justify-end sm:gap-4">
            {wordsError !== null && (
              <FieldError id={wordsErrorId} className="w-full items-start sm:flex-1">
                {wordsError}
              </FieldError>
            )}
            <span
              id={countId}
              className={cn(
                'flex-none text-small tabular-nums',
                limitError
                  ? 'font-semibold text-danger'
                  : atLimit
                    ? 'font-semibold text-ink'
                    : 'text-ink-muted',
              )}
            >
              {countLine(count)}
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-2 border-t border-confidential-border pt-4.5">
          <SubHeading className={cn(fieldLabelClass, 'm-0 text-body/[22px]')}>
            {caseCopy.beforeYouSend}
          </SubHeading>
          <ul className="m-0 flex list-disc flex-col gap-2 pl-5 text-ui/[22px]">
            {bullets.map((bullet, index) => (
              <li key={index} className="font-regular text-pretty">
                <Segments segments={linkifyCrisis(bullet)} />
              </li>
            ))}
          </ul>
        </div>

        {sendFailed && (
          <div ref={failureRef} tabIndex={-1} className="outline-none">
            <FormMessage tone="refusal">{caseCopy.sendFailed}</FormMessage>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 max-sm:flex-col max-sm:items-stretch">
          <Button
            loading={sending}
            aria-disabled={sending || undefined}
            onClick={submit}
            data-case-send=""
          >
            {sending ? caseCopy.sending : sendFailed ? caseCopy.tryAgain : caseCopy.send}
          </Button>
          <Button variant="secondary" disabled={sending} onClick={onCancel}>
            {caseCopy.notNow}
          </Button>
        </div>
      </div>
    </CaseSurface>
  )
}

export { CaseForm, SHORT_REPLY_CHARACTERS }
export type { CaseFormProps, CaseSubmission }
