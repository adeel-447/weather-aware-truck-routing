import { MapView } from './map/MapView'

/** Layout shell. The trip form, route comparison and map layers are added in later steps. */
export default function App() {
  return (
    <div className="app">
      <aside className="app__panel" aria-label="Trip planner">
        <header>
          <h1>Weather-Aware Truck Routing</h1>
          <p className="app__subtitle">
            Compare truck routes by forecast weather at each checkpoint&apos;s arrival time.
          </p>
        </header>
      </aside>
      <main className="app__map">
        <MapView />
      </main>
    </div>
  )
}
