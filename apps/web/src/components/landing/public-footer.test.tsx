import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PublicFooter } from './public-footer'

describe('the public footer', () => {
  it('says how long sandboxes, backups, and logs are kept, and who processes the data', () => {
    render(<PublicFooter />)
    // The words James approved on 2026-11-19 (Phase 9a, Task 4).
    expect(
      screen.getByText(
        'Each sandbox is removed after 24 hours. Server backups keep copies for up to 7 days, and server logs, which include IP addresses, are kept for 14 days. Anthropic (AI answers), Voyage (handbook search), Cloudflare (the bot check), and AWS (hosting) process this data.',
      ),
    ).toBeInTheDocument()
  })
})
