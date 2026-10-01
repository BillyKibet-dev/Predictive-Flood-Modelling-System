import { SignalHigh } from 'lucide-react'

const SENSOR_TYPES = {
  mathare: 'Ultrasonic Water Level Sensor',
  ngong: 'Radar Water Level Sensor',
  nairobi_river: 'Pressure Transducer Sensor',
}

const BATTERY = { mathare: 91, ngong: 87, nairobi_river: 78 }

// Admin section — physical IoT sensor health per monitored river zone
export default function SensorStatus({ zones }) {
  const now = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) + ' EAT'

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-gray-800">Sensor Status</h2>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {zones.map((zone) => {
          const battery = BATTERY[zone.id] ?? 85
          return (
            <div key={zone.id} className="bg-white rounded-lg shadow p-4 space-y-2">
              <p className="font-bold text-gray-800">{zone.name} Sensor</p>
              <p className="text-xs text-gray-500">
                {zone.lat.toFixed(3)}, {zone.lon.toFixed(3)}
              </p>
              <p className="text-xs text-gray-500">{SENSOR_TYPES[zone.id] || 'Water Level Sensor'}</p>
              <p className="text-green-600 font-semibold text-sm">● Online</p>
              <p className="text-xs text-gray-500">Last reading: {now}</p>
              <div>
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>Battery</span>
                  <span>{battery}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-green-500 h-2 rounded-full"
                    style={{ width: `${battery}%` }}
                  />
                </div>
              </div>
              <div className="flex items-center gap-1 text-gray-500 text-xs">
                <SignalHigh size={16} className="text-green-500" /> Signal: Strong
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
