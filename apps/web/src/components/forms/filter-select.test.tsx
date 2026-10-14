import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FilterSelect } from './filter-select'

const LOCATIONS = [
  { id: 'loc-aus', name: 'Austin warehouse', state: 'TX', count: 35 },
  { id: 'loc-den', name: 'Denver HQ', state: 'CO', count: 40 },
  { id: 'loc-oak', name: 'Oakland store', state: 'CA', count: 0 },
]

function setup(props: Partial<Parameters<typeof FilterSelect>[0]> = {}) {
  const onChange = vi.fn<(id: string | null) => void>()
  const user = userEvent.setup()
  render(
    <FilterSelect
      label="Location"
      value={null}
      options={LOCATIONS}
      onChange={onChange}
      {...props}
    />,
  )
  return { onChange, user }
}

describe('FilterSelect', () => {
  it('is named by its label, and shows "All" while nothing is chosen', () => {
    setup()
    const trigger = screen.getByRole('combobox', { name: 'Location' })
    expect(trigger).toHaveTextContent('Location')
    expect(trigger).toHaveTextContent('All')
    expect(trigger).not.toHaveAttribute('data-active')
  })

  it('lists "All" first, then every option with its count, zeros included', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    const options = await screen.findAllByRole('option')
    expect(options.map((o) => within(o).queryByText(/^\d+$/)?.textContent ?? null)).toEqual([
      null,
      '35',
      '40',
      '0',
    ])
    expect(options.every((o) => !o.hasAttribute('data-disabled'))).toBe(true)
  })

  it('names each option with its name and count apart, and keeps "All" plain', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    expect(await screen.findByRole('option', { name: 'Denver HQ, 40' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Oakland store, 0' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'All' })).toBeInTheDocument()
  })

  it('finds an option by typing its name, not its count', async () => {
    const { onChange, user } = setup()
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    await screen.findByRole('listbox')
    await user.keyboard('d')
    await user.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith('loc-den')
  })

  it('reports the chosen id', async () => {
    const { onChange, user } = setup()
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    await user.click(await screen.findByRole('option', { name: /Denver HQ/ }))
    expect(onChange).toHaveBeenCalledWith('loc-den')
  })

  it('reports null for "All"', async () => {
    const { onChange, user } = setup({ value: 'loc-den' })
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    await user.click(await screen.findByRole('option', { name: 'All' }))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('shows the chosen name without its count, and is active', () => {
    setup({ value: 'loc-den' })
    const trigger = screen.getByRole('combobox', { name: 'Location' })
    expect(within(trigger).getByText('Denver HQ')).toBeInTheDocument()
    expect(trigger).toHaveTextContent('Location')
    expect(trigger).not.toHaveTextContent('40')
    expect(trigger).toHaveAttribute('data-active', 'true')
    expect(trigger).toHaveClass('data-[active=true]:bg-primary-tint')
  })

  it('is not active, and shows "All", when the value matches no option', () => {
    setup({ value: 'gone' })
    const trigger = screen.getByRole('combobox', { name: 'Location' })
    expect(trigger).toHaveTextContent('All')
    expect(trigger).not.toHaveAttribute('data-active')
  })

  it('lets "All" be chosen when the value matches no option, so a stale filter can be cleared', async () => {
    const { onChange, user } = setup({ value: 'gone' })
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    await user.click(await screen.findByRole('option', { name: 'All' }))
    expect(onChange).toHaveBeenCalledWith(null)
  })

  it('shows the ring alone on focus, with no halo', () => {
    setup()
    expect(screen.getByRole('combobox')).toHaveClass('focus:shadow-none')
  })

  it('takes another label and its own word for "All"', () => {
    setup({ label: 'Department', allLabel: 'Everyone', options: [] })
    const trigger = screen.getByRole('combobox', { name: 'Department' })
    expect(trigger).toHaveTextContent('Everyone')
  })

  it('is a strong-bordered, 40 px control, with the design’s focus ring', () => {
    setup()
    expect(screen.getByRole('combobox')).toHaveClass(
      'h-control',
      'border-border-strong',
      'focus-visible:outline-focus-ring',
    )
  })

  it('shows a count beside "All" when given one, and names the option with it', async () => {
    const { user } = setup({ allCount: 119 })
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    expect(await screen.findByRole('option', { name: 'All, 119' })).toBeInTheDocument()
  })

  it('reports "All" as null even when it shows a count', async () => {
    const { user, onChange } = setup({ value: 'loc-den', allCount: 119 })
    await user.click(screen.getByRole('combobox', { name: 'Location' }))
    await user.click(await screen.findByRole('option', { name: 'All, 119' }))
    expect(onChange).toHaveBeenCalledWith(null)
  })
})
