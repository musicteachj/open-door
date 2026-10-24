import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { HoursStepper } from './hours-stepper'

function Controlled({ start = '3', disabled = false }: { start?: string; disabled?: boolean }) {
  const [value, setValue] = useState(start)
  return <HoursStepper value={value} onValueChange={setValue} disabled={disabled} />
}

const input = () => screen.getByRole('textbox', { name: 'Hours' })

describe('HoursStepper', () => {
  it('has the label, the value, and the hint as its description', () => {
    render(<Controlled />)
    expect(input()).toHaveValue('3')
    expect(input()).toHaveAccessibleDescription('1 to 8 hours')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('steps with the minus and plus buttons', async () => {
    const user = userEvent.setup()
    render(<Controlled />)
    await user.click(screen.getByRole('button', { name: 'More hours' }))
    expect(input()).toHaveValue('4')
    await user.click(screen.getByRole('button', { name: 'Fewer hours' }))
    await user.click(screen.getByRole('button', { name: 'Fewer hours' }))
    expect(input()).toHaveValue('2')
  })

  it('disables Fewer hours at 1', () => {
    render(<Controlled start="1" />)
    expect(screen.getByRole('button', { name: 'Fewer hours' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'More hours' })).toBeEnabled()
  })

  it('disables More hours at 8', () => {
    render(<Controlled start="8" />)
    expect(screen.getByRole('button', { name: 'More hours' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Fewer hours' })).toBeEnabled()
  })

  it('takes what is typed, and says so when it is not 1 to 8', async () => {
    const user = userEvent.setup()
    render(<Controlled start="" />)
    await user.type(input(), '645')
    expect(input()).toHaveValue('645')
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('keeps a pasted 3.5 as it is and shows the error, instead of cutting it to "3."', async () => {
    const user = userEvent.setup()
    render(<Controlled start="" />)
    await user.click(input())
    await user.paste('3.5')
    expect(input()).toHaveValue('3.5')
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a whole number from 1 to 8.')
  })

  it.each(['0', '9', '12', '', '2.5', 'ab', '-1', '3.5', '4 5'])(
    'shows the error for "%s"',
    (value) => {
      render(<Controlled start={value} />)
      const alert = screen.getByRole('alert')
      expect(alert).toHaveTextContent('Enter a whole number from 1 to 8.')
      expect(input()).toHaveAttribute('aria-invalid', 'true')
      expect(input()).toHaveAccessibleDescription(
        expect.stringContaining('Enter a whole number from 1 to 8.'),
      )
    },
  )

  it.each(['1', '4', '8', '08', ' 4', '4 '])('accepts "%s" without an error', (value) => {
    render(<Controlled start={value} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(input()).not.toHaveAttribute('aria-invalid')
  })

  it('recovers from an out-of-range value with the buttons', async () => {
    const user = userEvent.setup()
    render(<Controlled start="12" />)
    await user.click(screen.getByRole('button', { name: 'Fewer hours' }))
    expect(input()).toHaveValue('8')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('starts from 1 when the field is empty', async () => {
    const user = userEvent.setup()
    render(<Controlled start="" />)
    await user.click(screen.getByRole('button', { name: 'More hours' }))
    expect(input()).toHaveValue('1')
  })

  it('locks the input and both buttons when disabled', () => {
    render(<Controlled disabled />)
    expect(input()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Fewer hours' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'More hours' })).toBeDisabled()
  })
})
