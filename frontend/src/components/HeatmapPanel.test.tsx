import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import { heatmapFixture } from '../test/fixtures'
import { HeatmapPanel } from './HeatmapPanel'

function setup(props: Partial<Parameters<typeof HeatmapPanel>[0]> = {}) {
  const onOffsetChange = vi.fn()
  const onVisibleChange = vi.fn()
  const onRetry = vi.fn()
  render(
    <HeatmapPanel
      heatmap={heatmapFixture()}
      isLoading={false}
      error={null}
      onRetry={onRetry}
      offsetHours={0}
      onOffsetChange={onOffsetChange}
      visible
      onVisibleChange={onVisibleChange}
      timeZone="America/Chicago"
      {...props}
    />,
  )
  return { onOffsetChange, onVisibleChange, onRetry }
}

describe('HeatmapPanel', () => {
  it('shows the exact valid time in the trip time zone', () => {
    setup({ offsetHours: 3 })
    expect(screen.getByText('+3 h')).toBeInTheDocument()
    expect(screen.getByText('Tue, Oct 20, 11:00 AM CDT')).toBeInTheDocument()
  })

  it('reports slider moves in whole hours from 0 to 48', () => {
    const { onOffsetChange } = setup()
    const slider = screen.getByRole('slider')
    expect(slider).toHaveAttribute('min', '0')
    expect(slider).toHaveAttribute('max', '48')
    fireEvent.change(slider, { target: { value: '18' } })
    expect(onOffsetChange).toHaveBeenCalledWith(18)
  })

  it('explains that it is independent of checkpoint ETA scoring', () => {
    setup()
    expect(screen.getByText(/separate from checkpoint risk/)).toBeInTheDocument()
    expect(screen.getByText(/not used for route scoring/)).toBeInTheDocument()
    expect(screen.getByText('No data')).toBeInTheDocument()
  })

  it('flags frames beyond the forecast range', () => {
    setup({ offsetHours: 48 })
    expect(screen.getByRole('status')).toHaveTextContent('No forecast is available for this time')
  })

  it('shows loading and error states', () => {
    setup({ heatmap: undefined, isLoading: true })
    expect(screen.getByText('Loading the 48-hour forecast…')).toBeInTheDocument()
  })

  it('shows provider errors in heatmap context with a retry', async () => {
    const { onRetry } = setup({
      heatmap: undefined,
      error: new ApiError(503, {
        code: 'provider_rate_limited',
        message: 'Minutely API request limit exceeded.',
        provider: 'Open-Meteo',
      }),
    })
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Heatmap unavailable. Open-Meteo is busy.')
    expect(alert).toHaveTextContent('Route scoring is not affected.')
    await userEvent.click(within(alert).getByRole('button', { name: 'Retry heatmap' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('does not offer a retry for errors a retry cannot fix', () => {
    setup({
      heatmap: undefined,
      error: new ApiError(400, { code: 'invalid_request', message: 'Request validation failed.' }),
    })
    expect(screen.getByRole('alert')).toHaveTextContent('The forecast request was rejected')
    expect(screen.queryByRole('button', { name: 'Retry heatmap' })).not.toBeInTheDocument()
  })

  it('toggles visibility and disables the slider while hidden', () => {
    const { onVisibleChange } = setup({ visible: false })
    expect(screen.getByRole('slider')).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show' }))
    expect(onVisibleChange).toHaveBeenCalledWith(true)
  })
})
