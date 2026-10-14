import { useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from './api/client'
import { describeError } from './api/errorMessages'
import { useEvaluateRoutes, useHeatmap } from './api/hooks'
import { CheckpointList } from './components/CheckpointList'
import { HeatmapPanel } from './components/HeatmapPanel'
import { RecommendationBanner } from './components/RecommendationBanner'
import { RouteComparison } from './components/RouteComparison'
import { SeverityLegend } from './components/SeverityLegend'
import { TripForm } from './components/TripForm'
import { TripSummary } from './components/TripSummary'
import { serverFieldErrors } from './components/tripValidation'
import { WarningList } from './components/WarningList'
import { CheckpointLayer } from './map/CheckpointLayer'
import { HeatmapLayer } from './map/HeatmapLayer'
import { MapView } from './map/MapView'
import { RouteLayers } from './map/RouteLayers'
import type { EvaluateRequest, EvaluateResponse } from './types/api'

function defaultSelection(evaluation: EvaluateResponse): string | null {
  return evaluation.recommendation.route_id ?? evaluation.routes[0]?.id ?? null
}

export default function App() {
  const evaluate = useEvaluateRoutes()
  // The last successful result is kept in state: TanStack Query v5 clears mutation data while a new
  // request is pending, which would unmount the map layers and blank the panel on every re-submit.
  const [evaluation, setEvaluation] = useState<EvaluateResponse | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [hoveredRouteId, setHoveredRouteId] = useState<string | null>(null)
  const [focus, setFocus] = useState<{ index: number } | null>(null)
  const [heatmapOffset, setHeatmapOffset] = useState(0)
  const [heatmapVisible, setHeatmapVisible] = useState(true)
  // One request per evaluation returns all 49 frames; the slider never fetches.
  const heatmap = useHeatmap(evaluation ?? undefined)

  const selectedRoute = evaluation?.routes.find((r) => r.id === selectedRouteId) ?? null
  // Colours follow the provider's route ids, so a route keeps its colour regardless of rank.
  const colorIndex = useMemo(
    () =>
      Object.fromEntries(
        (evaluation?.routes.map((r) => r.id) ?? []).sort().map((id, index) => [id, index]),
      ),
    [evaluation],
  )

  const error = evaluate.error
  // Memoized so TripForm sees a new object only when a new error arrives.
  const fieldErrors = useMemo(
    () => (error instanceof ApiError && error.fields ? serverFieldErrors(error.fields) : undefined),
    [error],
  )
  const hasFieldErrors = fieldErrors !== undefined && Object.keys(fieldErrors).length > 0
  // Only input errors are shown purely inline; anything else keeps its banner (and retry option)
  // even if the envelope also names fields.
  const inlineOnly =
    hasFieldErrors &&
    error instanceof ApiError &&
    (error.code === 'invalid_request' || error.code === 'place_not_found')
  const errorInfo = error && !inlineOnly ? describeError(error) : null
  const [lastRequest, setLastRequest] = useState<EvaluateRequest | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  // On narrow screens results render below the form; bring a new result into view.
  useEffect(() => {
    const results = resultsRef.current
    if (!results || typeof results.scrollIntoView !== 'function') return
    if (results.getBoundingClientRect().top > window.innerHeight * 0.8) {
      results.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [evaluation])
  const isRefreshing = evaluate.isPending && evaluation !== null

  function submit(request: EvaluateRequest) {
    setLastRequest(request)
    setFocus(null)
    evaluate.mutate(request, {
      onSuccess: (result) => {
        setEvaluation(result)
        setHeatmapOffset(0)
        setSelectedRouteId(defaultSelection(result))
        setHoveredRouteId(null)
      },
    })
  }

  function select(routeId: string) {
    setSelectedRouteId(routeId)
    setFocus(null)
  }

  return (
    <div className="app">
      <aside className="app__panel" aria-label="Trip planner">
        <header className="app__header">
          <h1>Weather-Aware Truck Routing</h1>
          <p className="app__subtitle">
            Compare truck routes by forecast weather at each checkpoint&apos;s arrival time.
          </p>
        </header>

        <TripForm
          onSubmit={submit}
          isSubmitting={evaluate.isPending}
          serverErrors={fieldErrors}
          onEdit={() => {
            // Try again re-sends the failed trip; once the form changes, that would be stale.
            setLastRequest(null)
          }}
        />

        {errorInfo && (
          <div className="banner banner--danger" role="alert">
            <strong>{errorInfo.title}</strong>
            <p>{errorInfo.message}</p>
            {evaluation && <p>The previous results are still shown below.</p>}
            {errorInfo.retryable && lastRequest && (
              <button
                type="button"
                className="button button--secondary"
                disabled={evaluate.isPending}
                onClick={() => {
                  submit(lastRequest)
                }}
              >
                Try again
              </button>
            )}
          </div>
        )}

        {evaluation && (
          <div
            ref={resultsRef}
            className={`results${isRefreshing ? ' results--stale' : ''}`}
            aria-live="polite"
            aria-busy={isRefreshing}
          >
            <RecommendationBanner evaluation={evaluation} />
            <RouteComparison
              evaluation={evaluation}
              selectedRouteId={selectedRouteId}
              onSelect={select}
              onHover={setHoveredRouteId}
              colorIndex={colorIndex}
            />
            {selectedRoute && (
              <CheckpointList
                route={selectedRoute}
                timeZone={evaluation.request.timezone}
                onFocusCheckpoint={(index) => {
                  setFocus({ index })
                }}
              />
            )}
            <WarningList warnings={evaluation.warnings} />
            <TripSummary evaluation={evaluation} />
          </div>
        )}

        {!evaluation && !evaluate.isPending && !error && (
          <p className="empty-state">
            Enter a trip to compare up to three truck routes. Each route is checked against the
            forecast at the time the truck is expected to reach every checkpoint.
          </p>
        )}
      </aside>

      <main className="app__map">
        <MapView>
          {evaluation && (
            <>
              {/* Rendered first so its fill layer sits beneath the route lines. */}
              <HeatmapLayer
                heatmap={heatmap.data}
                offsetHours={heatmapOffset}
                visible={heatmapVisible}
              />
              <RouteLayers
                routes={evaluation.routes}
                colorIndex={colorIndex}
                selectedRouteId={selectedRouteId}
                hoveredRouteId={hoveredRouteId}
                fitKey={evaluation.generated_at}
                onSelect={select}
                onHover={setHoveredRouteId}
              />
              <CheckpointLayer
                route={selectedRoute}
                timeZone={evaluation.request.timezone}
                focus={focus}
              />
            </>
          )}
        </MapView>
        {evaluation && <SeverityLegend />}
        {evaluation && (
          <HeatmapPanel
            heatmap={heatmap.data}
            isLoading={heatmap.isFetching && !heatmap.data}
            error={heatmap.isFetching ? null : heatmap.error}
            onRetry={() => {
              void heatmap.refetch()
            }}
            offsetHours={heatmapOffset}
            onOffsetChange={setHeatmapOffset}
            visible={heatmapVisible}
            onVisibleChange={setHeatmapVisible}
            timeZone={evaluation.request.timezone}
          />
        )}
        {evaluate.isPending && (
          <div className="map-overlay" role="status">
            Evaluating routes and forecasts…
          </div>
        )}
      </main>
    </div>
  )
}
