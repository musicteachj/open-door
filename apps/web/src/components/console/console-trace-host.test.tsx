import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { DAY_TURNS, sectionTitle, T_1033_CARD, T_FLAGGED } from '@/app/gallery/fixtures/console'
import { stubMediaQuery } from '@/test/media-query'
import { ConsoleTraceHost } from './console-trace-host'

const host = () => (
  <ConsoleTraceHost turns={DAY_TURNS} timeZone="America/Denver" sectionTitle={sectionTitle} />
)
const rowButton = (time: string) => screen.getByRole('button', { name: new RegExp(`^${time}`) })

afterEach(() => {
  document.body.removeAttribute('style')
})

describe('ConsoleTraceHost', () => {
  it('shows no trace until a row is opened', () => {
    render(host())
    expect(screen.queryByRole('complementary')).toBeNull()
    expect(rowButton('10:31 AM')).toHaveAttribute('aria-expanded', 'false')
  })

  it('docks the trace beside the table, focuses its heading, and marks the row', async () => {
    const { container } = render(host())
    await userEvent.click(rowButton('10:33 AM'))
    const heading = screen.getByRole('heading', {
      level: 2,
      name: '10:33 AM · Employee · Oakland, CA',
    })
    expect(heading).toHaveFocus()
    expect(rowButton('10:33 AM')).toHaveAttribute('aria-expanded', 'true')
    expect(rowButton('10:33 AM').getAttribute('aria-controls')).toBe(
      screen.getByRole('complementary').id,
    )
    expect(container.querySelector('[data-slot="turn-table"]')).toHaveAttribute('data-panel')
  })

  it('as a page, docks the trace outside the padded column, at the panel width', async () => {
    const { container } = render(
      <ConsoleTraceHost
        turns={DAY_TURNS}
        timeZone="America/Denver"
        sectionTitle={sectionTitle}
        header={<h1>Console</h1>}
        columnClassName="px-12"
      />,
    )
    await userEvent.click(rowButton('10:33 AM'))
    const dock = container.querySelector('[data-slot="trace-dock"]')!
    expect(dock).toHaveClass('w-panel', 'sticky')
    expect(dock.parentElement).toBe(container.querySelector('[data-slot="console-trace-host"]'))
    expect(container.querySelector('.px-12')).not.toContainElement(dock as HTMLElement)
  })

  it('opens from the keyboard with Enter', async () => {
    render(host())
    rowButton('10:31 AM').focus()
    await userEvent.keyboard('{Enter}')
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('10:31 AM')
    expect(screen.getByRole('heading', { level: 2 })).toHaveFocus()
  })

  it('swaps the content for another row and focuses the heading again', async () => {
    render(host())
    await userEvent.click(rowButton('10:33 AM'))
    await userEvent.click(rowButton('10:31 AM'))
    expect(screen.getAllByRole('complementary')).toHaveLength(1)
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('10:31 AM')
    expect(screen.getByRole('heading', { level: 2 })).toHaveFocus()
    expect(rowButton('10:33 AM')).toHaveAttribute('aria-expanded', 'false')
  })

  it('closes on Escape and returns focus to the row’s button', async () => {
    render(host())
    await userEvent.click(rowButton('10:33 AM'))
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('complementary')).toBeNull()
    expect(rowButton('10:33 AM')).toHaveFocus()
  })

  it('closes with the X and returns focus to the row’s button', async () => {
    render(host())
    await userEvent.click(rowButton('10:31 AM'))
    await userEvent.click(screen.getByRole('button', { name: 'Close trace' }))
    expect(screen.queryByRole('complementary')).toBeNull()
    expect(rowButton('10:31 AM')).toHaveFocus()
  })

  it('forgets an open row that leaves the list, so it never reopens when the id returns', async () => {
    const { rerender } = render(host())
    await userEvent.click(rowButton('10:33 AM'))
    expect(screen.getByRole('complementary')).toBeInTheDocument()
    const without = DAY_TURNS.filter((t) => t.id !== T_1033_CARD.id)
    rerender(
      <ConsoleTraceHost turns={without} timeZone="America/Denver" sectionTitle={sectionTitle} />,
    )
    expect(screen.queryByRole('complementary')).toBeNull()
    rerender(host())
    expect(screen.queryByRole('complementary')).toBeNull()
    expect(rowButton('10:33 AM')).toHaveAttribute('aria-expanded', 'false')
  })

  it('hides the panel while the rows load, and shows it again after', async () => {
    const { rerender } = render(host())
    await userEvent.click(rowButton('10:33 AM'))
    rerender(
      <ConsoleTraceHost
        turns={DAY_TURNS}
        timeZone="America/Denver"
        sectionTitle={sectionTitle}
        loading
      />,
    )
    expect(screen.queryByRole('complementary')).toBeNull()
    rerender(host())
    expect(screen.getByRole('complementary')).toBeInTheDocument()
  })

  it('opens nothing for the flagged row', async () => {
    render(host())
    await userEvent.click(screen.getByText(/^Flagged by the safety check/))
    expect(screen.queryByRole('complementary')).toBeNull()
  })

  it('shows what it is given before and after the table, and no trace controls without rows', () => {
    render(
      <ConsoleTraceHost
        turns={[]}
        timeZone="America/Denver"
        sectionTitle={sectionTitle}
        before={<p>Tiles here</p>}
        after={<p>Scoreboard here</p>}
      />,
    )
    expect(screen.getByText('Tiles here')).toBeInTheDocument()
    expect(screen.getByText('Scoreboard here')).toBeInTheDocument()
  })

  describe('at 640 px and below', () => {
    it('opens the trace as a full-screen dialog named by its title, and returns focus on Escape', async () => {
      stubMediaQuery(true)
      render(host())
      await userEvent.click(rowButton('10:33 AM'))
      const dialog = screen.getByRole('dialog', { name: '10:33 AM · Employee · Oakland, CA' })
      expect(dialog).toHaveClass('top-0', 'rounded-none')
      expect(screen.queryByRole('complementary')).toBeNull()
      expect(screen.getByRole('heading', { level: 2 })).toHaveFocus()
      await userEvent.keyboard('{Escape}')
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(rowButton('10:33 AM')).toHaveFocus()
    })

    it('closes with the X and returns focus to the button', async () => {
      stubMediaQuery(true)
      render(host())
      await userEvent.click(rowButton('10:31 AM'))
      await userEvent.click(screen.getByRole('button', { name: 'Close trace' }))
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(rowButton('10:31 AM')).toHaveFocus()
    })
  })

  it('keeps the trace open when the rows reload and return', async () => {
    const { rerender } = render(host())
    await userEvent.click(rowButton('10:33 AM'))
    const loadingHost = (turns: typeof DAY_TURNS, loading: boolean) => (
      <ConsoleTraceHost
        turns={turns}
        timeZone="America/Denver"
        sectionTitle={sectionTitle}
        loading={loading}
      />
    )
    rerender(loadingHost([], true))
    rerender(loadingHost(DAY_TURNS, false))
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('10:33 AM')
    expect(rowButton('10:33 AM')).toHaveAttribute('aria-expanded', 'true')
  })

  it('closes for good when the row is gone and the rows are not loading', async () => {
    const { rerender } = render(host())
    await userEvent.click(rowButton('10:33 AM'))
    const without = DAY_TURNS.filter((t) => t.id !== T_1033_CARD.id)
    rerender(
      <ConsoleTraceHost turns={without} timeZone="America/Denver" sectionTitle={sectionTitle} />,
    )
    rerender(host())
    expect(screen.queryByRole('complementary')).toBeNull()
  })

  it('moves focus to the first remaining row when the open row is reloaded away', async () => {
    const { rerender } = render(host())
    await userEvent.click(rowButton('10:33 AM'))
    expect(screen.getByRole('heading', { level: 2 })).toHaveFocus()
    const without = DAY_TURNS.filter((t) => t.id !== T_1033_CARD.id)
    rerender(
      <ConsoleTraceHost turns={without} timeZone="America/Denver" sectionTitle={sectionTitle} />,
    )
    expect(screen.queryByRole('complementary')).toBeNull()
    const first = document.querySelector<HTMLElement>('[data-turn-id]')!
    expect(first).toHaveFocus()
  })

  it('moves focus to the day heading when no row is left to take it', async () => {
    const { rerender } = render(host())
    await userEvent.click(rowButton('10:33 AM'))
    rerender(
      <ConsoleTraceHost
        turns={[T_FLAGGED]}
        timeZone="America/Denver"
        sectionTitle={sectionTitle}
      />,
    )
    expect(screen.getByRole('heading', { level: 3 })).toHaveFocus()
  })

  it('leaves focus alone when the open row is reloaded away from outside the panel', async () => {
    const { rerender } = render(host())
    await userEvent.click(rowButton('10:33 AM'))
    const outside = document.createElement('button')
    document.body.append(outside)
    outside.focus()
    const without = DAY_TURNS.filter((t) => t.id !== T_1033_CARD.id)
    rerender(
      <ConsoleTraceHost turns={without} timeZone="America/Denver" sectionTitle={sectionTitle} />,
    )
    expect(outside).toHaveFocus()
    outside.remove()
  })
})
