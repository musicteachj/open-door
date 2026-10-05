import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

// tailwind-merge guesses what a class means from its name, and it only knows Tailwind's own
// scale. The design's names (src/styles/theme.css) have to be taught to it. Without this,
// `text-small` reads as a color and drops `text-ink-muted`, and `shadow-focus-halo` reads as a
// shadow color and survives next to `shadow-xs`. Keep these lists in step with theme.css.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: ['display', 'h1', 'h2', 'body-lg', 'body', 'ui', 'small', 'caption', 'numeric'],
      shadow: ['xs', 'md', 'focus-halo'],
      radius: ['xs', 'sm', 'md', 'lg', 'xl', 'full'],
      'font-weight': ['regular', 'medium', 'semibold'],
      spacing: ['sidebar', 'rail', 'content', 'sheet', 'control', 'control-sm', 'row'],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
