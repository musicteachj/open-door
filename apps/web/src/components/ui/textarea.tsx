import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'
import { fieldClasses } from './field-classes'

function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(fieldClasses, 'min-h-20 resize-y px-3 py-2', className)}
      {...props}
    />
  )
}

export { Textarea }
