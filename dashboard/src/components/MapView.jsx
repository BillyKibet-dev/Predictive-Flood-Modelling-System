import { Fragment } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import { RISK_OPACITY, RISK_RADIUS, riskColor } from '../constants/colors'
import { LAST_UPDATED } from '../data/mockData'
import RiskBadge from './RiskBadge'

// Leaflet map — every zone rendered as a coloured circle marker; Extreme zones
// get a second, larger pulsing marker behind them (a "sonar ping") to draw attention.
export default function MapView({ zones, height = '100%' }) {
  const navigate = useNavigate()

  function viewDetails(zoneId) {
    navigate(`/citizen#zone-${zoneId}`)
  }

  function getDirections(lat, lon) {
    window.open(`https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`, '_blank', 'noopener')
  }

  return (
    <MapContainer center={[-1.286, 36.817]} zoom={12} style={{ height, width: '100%' }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {zones.map((zone) => {
        const color = riskColor(zone.risk)
        return (
          <Fragment key={zone.id}>
            {zone.risk === 'Extreme' && (
              <CircleMarker
                center={[zone.lat, zone.lon]}
                radius={RISK_RADIUS[zone.risk] + 10}
                pathOptions={{ color, fillColor: color, fillOpacity: 0.25, weight: 0, className: 'pulse-marker' }}
                interactive={false}
              />
            )}
            <CircleMarker
              center={[zone.lat, zone.lon]}
              radius={RISK_RADIUS[zone.risk]}
              pathOptions={{ color, fillColor: color, fillOpacity: RISK_OPACITY[zone.risk], weight: 1.5 }}
            >
              <Popup>
                <div className="p-4 space-y-2">
                  <div>
                    <h3 className="text-base font-semibold text-ink leading-tight">{zone.name}</h3>
                    <p className="text-xs text-muted">{zone.subCounty}</p>
                  </div>
                  <RiskBadge risk={zone.risk} size="sm" />
                  <p className="text-sm text-ink">24h Rainfall: {zone.rainfall24h}mm</p>
                  <p className="text-sm text-ink">Confidence: {Math.round(zone.confidence * 100)}%</p>
                  <p className="text-xs text-muted">Updated: {LAST_UPDATED}</p>
                  <div className="border-t border-border pt-2 flex gap-2">
                    <button
                      onClick={() => viewDetails(zone.id)}
                      className="flex-1 text-xs font-medium border border-border rounded-btn px-2 py-1.5 hover:bg-bg transition-colors"
                    >
                      View Details
                    </button>
                    <button
                      onClick={() => getDirections(zone.lat, zone.lon)}
                      className="flex-1 text-xs font-medium rounded-btn px-2 py-1.5 text-brand hover:bg-bg transition-colors"
                    >
                      Get Directions
                    </button>
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          </Fragment>
        )
      })}
    </MapContainer>
  )
}
