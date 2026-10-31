import { Lock } from 'lucide-react'
import type { ComponentProps } from 'react'
import { Button } from '@/components/ui/button'
import { caseCopy } from './labels'

type OpenCaseButtonProps = Omit<ComponentProps<typeof Button>, 'children'>

/**
 * "Open a confidential case" with a lock. Primary on the sensitive panel and on My cases;
 * secondary on the crisis panel, where the crisis text and the contacts come first. Pressing it
 * only opens the form: nothing is sent until the person presses Send to HR there.
 */
function OpenCaseButton(props: OpenCaseButtonProps) {
  return (
    <Button {...props}>
      <Lock aria-hidden="true" className="size-4" />
      {caseCopy.openButton}
    </Button>
  )
}

export { OpenCaseButton }
export type { OpenCaseButtonProps }
