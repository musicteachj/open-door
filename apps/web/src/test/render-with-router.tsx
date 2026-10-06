import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'

/** Renders a component inside a memory router, for components that contain a `Link`. */
export function renderWithRouter(ui: ReactElement, { at = '/' }: { at?: string } = {}) {
  const user = userEvent.setup()
  return { user, ...render(<MemoryRouter initialEntries={[at]}>{ui}</MemoryRouter>) }
}
