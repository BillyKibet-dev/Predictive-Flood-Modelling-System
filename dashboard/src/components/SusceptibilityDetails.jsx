// Why a place scores as it does: each factor, its points, and the measured value behind it.
const VALUE = {
  height_above_river: r => `${r.height_above_river_m} m above ${r.river_name}`,
  relief: r => `${r.relief_m > 0 ? '+' : ''}${r.relief_m} m vs ground within 250 m`,
  river_distance: r => `${r.river_distance_m} m to ${r.river_name}`,
  satellite_water: r => !r.satellite_covered ? 'Not covered by the 2024 scene' : r.satellite_water_m == null ? 'No water seen within 250 m' : `Water ${r.satellite_water_m} m away`,
  built_up: r => r.built_up_fraction == null ? 'Unknown' : `${Math.round(r.built_up_fraction * 100)}% built up`,
  observed: r => r.observed_flooding ? 'Recorded' : 'None recorded',
}

export default function SusceptibilityDetails({ row }) {
  if (!row) return null
  return <section aria-label="Local flood susceptibility" className="space-y-2">
    <h3 className="text-sm font-semibold">Local susceptibility: {row.level} <span className="font-normal text-muted tabular">({row.score} of {row.max_score} points)</span></h3>
    <ul className="text-xs divide-y divide-border border border-border rounded-btn">
      {row.factors.map(f => <li key={f.key} className="flex gap-3 px-2.5 py-1.5">
        <span className="flex-1"><span className="block">{f.label}</span><span className="text-muted">{VALUE[f.key](row)}</span></span>
        <span className={`tabular shrink-0 ${f.points ? 'font-semibold' : 'text-muted'}`}>{f.points}/{f.max_points}</span>
      </li>)}
    </ul>
    <p className="text-xs text-muted">Compares the monitored places with each other using 30 m terrain, mapped rivers, the 1 May 2024 satellite water map and land cover. Not a validated flood probability; it cannot see drains or blockages.</p>
  </section>
}
