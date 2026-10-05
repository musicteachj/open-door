import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'
import { fieldClasses } from './field-classes'

function Input({ className, type = 'text', ...props }: ComponentProps<'input'>) {
  return (
    <input
      data-slot="input"
      type={type}
      className={cn(fieldClasses, 'h-control px-3', className)}
      {...props}
    />
  )
}

export { Input }
