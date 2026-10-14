import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { TripForm } from './TripForm'
import { initialValues } from './tripValidation'

function setup(props: Partial<Parameters<typeof TripForm>[0]> = {}) {
  const onSubmit = vi.fn()
  render(
    <TripForm
      onSubmit={onSubmit}
      isSubmitting={false}
      initial={{ ...initialValues(), timezone: 'America/Chicago' }}
      {...props}
    />,
  )
  return onSubmit
}

describe('TripForm', () => {
  it('shows inline errors and does not submit an incomplete trip', async () => {
    const onSubmit = setup()
    await userEvent.click(screen.getByRole('button', { name: 'Compare routes' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Origin')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Enter an origin.')).toBeInTheDocument()
    expect(screen.getByText('Enter the cargo weight in pounds.')).toBeInTheDocument()
  })

  it('submits a valid trip with the chosen spacing', async () => {
    const onSubmit = setup()
    await userEvent.type(screen.getByLabelText('Origin'), 'Chicago, IL')
    await userEvent.type(screen.getByLabelText('Destination'), 'Denver, CO')
    await userEvent.type(screen.getByLabelText('Cargo weight (lb)'), '38000')
    await userEvent.click(screen.getByLabelText('10 mi'))
    await userEvent.click(screen.getByRole('button', { name: 'Compare routes' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        origin: 'Chicago, IL',
        destination: 'Denver, CO',
        timezone: 'America/Chicago',
        load_weight_lb: 38000,
        checkpoint_spacing_miles: 10,
      }),
    )
  })

  it('clears an error once the field is fixed', async () => {
    setup()
    await userEvent.click(screen.getByRole('button', { name: 'Compare routes' }))
    await userEvent.type(screen.getByLabelText('Origin'), 'Chicago')
    expect(screen.queryByText('Enter an origin.')).not.toBeInTheDocument()
  })

  it('shows server-side field errors', () => {
    setup({ serverErrors: { departureLocal: 'this local time does not exist' } })
    expect(screen.getByText('this local time does not exist')).toBeInTheDocument()
  })

  it('disables submit while evaluating', () => {
    setup({ isSubmitting: true })
    expect(screen.getByRole('button', { name: 'Evaluating routes…' })).toBeDisabled()
  })

  it('explains how cargo weight is used', () => {
    setup()
    expect(screen.getByText(/Weather load rules use cargo weight/)).toBeInTheDocument()
  })
})

describe('TripForm server errors', () => {
  it('hides a server error once its field is edited', async () => {
    setup({ serverErrors: { destination: 'origin and destination resolve to the same place' } })
    const destination = screen.getByLabelText('Destination')
    expect(destination).toHaveAttribute('aria-invalid', 'true')
    await userEvent.type(destination, 'Denver, CO')
    expect(screen.queryByText(/resolve to the same place/)).not.toBeInTheDocument()
    expect(destination).not.toHaveAttribute('aria-invalid')
  })
})
