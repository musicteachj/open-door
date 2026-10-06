// The look every text field shares, from the design's search field (forms.css): a 1 px
// input-border that darkens on hover, and on focus an aubergine border plus the 3 px halo in
// place of the outline. The design defines no error state, so aria-invalid reuses the danger
// color on the border, and the halo stays the brand's.
export const fieldClasses = [
  'w-full rounded-md border border-input-border bg-surface-raised text-ui text-ink font-regular',
  'placeholder:text-ink-placeholder outline-none',
  'transition-[border-color,box-shadow]',
  'hover:border-input-border-hover',
  'focus:border-primary focus:shadow-focus-halo',
  'aria-invalid:border-danger',
  'disabled:cursor-not-allowed disabled:border-disabled-bg disabled:bg-disabled-bg disabled:text-disabled-fg',
]
