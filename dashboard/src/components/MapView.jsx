import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import { RISK_ORDER, RISK_RADIUS, riskColor } from '../constants/colors'
import RiskBadge from './RiskBadge'

// Leaflet map showing the flood risk of each monitored zone as a coloured circle marker
export default function MapView({ zones, height = 420 }) {
  return (
    <div className="relative" style={{ height }}>
      <MapContainer
        center={[-1.286, 36.817]}
        zoom={12}
        style={{ height: '100%', width: '100%', borderRadius: '0.5rem' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {zones.map((zone) => (
          <CircleMarker
            key={zone.id}
            center={[zone.lat, zone.lon]}
            radius={RISK_RADIUS[zone.risk]}
            pathOptions={{
              color: riskColor(zone.risk),
              fillColor: riskColor(zone.risk),
              fillOpacity: 0.6,
              className: zone.risk === 'Extreme' ? 'pulse-marker' : '',
            }}
          >
            <Popup>
              <div className="space-y-1">
                <p className="font-bold">{zone.name}</p>
                <RiskBadge risk={zone.risk} size="sm" />
                <p className="text-sm">Water level: {zone.waterLevel.toFixed(1)}m</p>
                <p className="text-sm">6h Rainfall: {zone.rainfall6h}mm</p>
                <p className="text-sm">Confidence: {Math.round(zone.confidence * 100)}%</p>
                <p className="text-xs text-gray-500">Last updated: {zone.lastUpdated}</p>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>

      {/* Map legend */}
      <div className="absolute bottom-2 left-2 z-[1000] bg-white/95 rounded-lg shadow px-3 py-2 text-xs space-y-1">
        {RISK_ORDER.map((risk) => (
          <div key={risk} className="flex items-center gap-2">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ backgroundColor: riskColor(risk) }}
            />
            <span className="text-gray-700">{risk}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
