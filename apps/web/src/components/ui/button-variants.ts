import { cva, type VariantProps } from 'class-variance-authority'

// From docs/design/system/components/core/core.css (.od-btn). The `ui` text size carries weight
// 500, so the semibold the design asks for is set here. Hover is gated on `enabled:` so a
// disabled button never lights up.
export const buttonVariants = cva(
  [
    'inline-flex items-center justify-center whitespace-nowrap border border-transparent font-semibold',
    'cursor-pointer transition-[color,background-color,border-color]',
    'disabled:cursor-not-allowed',
  ],
  {
    variants: {
      variant: {
        primary: [
          'bg-primary text-on-primary enabled:hover:bg-primary-hover',
          'disabled:bg-disabled-bg disabled:text-disabled-fg',
        ],
        secondary: [
          'bg-surface-raised text-ink border-border-strong',
          'enabled:hover:bg-surface-hover enabled:hover:border-border-strong-hover',
          'disabled:bg-surface-raised disabled:border-disabled-bg disabled:text-disabled-fg',
        ],
        ghost: [
          'bg-transparent text-primary',
          'enabled:hover:bg-primary-tint enabled:hover:text-primary-hover',
          'disabled:bg-transparent disabled:text-disabled-fg',
        ],
        destructive: [
          'bg-danger text-on-danger enabled:hover:bg-danger-hover',
          'disabled:bg-disabled-bg disabled:text-disabled-fg',
        ],
      },
      size: {
        md: 'h-control gap-2 rounded-md px-4 text-ui',
        sm: 'h-control-sm gap-1.5 rounded-sm px-3 text-small',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export type ButtonVariants = VariantProps<typeof buttonVariants>
