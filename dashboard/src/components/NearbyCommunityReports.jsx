import { useEffect,useState } from 'react'
import { Link } from 'react-router-dom'

export default function NearbyCommunityReports({areaId,authorizedRequest}) {
  const [state,setState]=useState({loading:true,data:null,error:false})
  useEffect(()=>{
    const controller=new AbortController()
    setState({loading:true,data:null,error:false})
    authorizedRequest(`/monitoring-areas/${encodeURIComponent(areaId)}/reports`,{signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted){
        if(data.area_id!==areaId || !Array.isArray(data.items) || data.search_radius_m!==500 || data.lookback_days!==30) throw new Error('Unexpected report response')
        setState({loading:false,data,error:false})
      }})
      .catch(()=>{if(!controller.signal.aborted)setState({loading:false,data:null,error:true})})
    return()=>controller.abort()
  },[areaId,authorizedRequest])
  return <section className="text-sm mt-4 border-t border-border pt-3" aria-label="Nearby community reports">
    <h3 className="font-semibold">Nearby community reports · staff</h3>
    <p className="text-xs text-muted mt-1">Reported coordinates within 500 m, last 30 days. Proximity does not confirm flooding at this point.</p>
    {state.loading ? <p className="text-xs mt-2">Checking reports…</p> : state.error ? <p className="text-xs mt-2">Reports could not be verified. Check the report inbox.</p> : state.data.status==='LOCATION_UNRESOLVED' ? <p className="text-xs mt-2">A location is needed to match nearby reports.</p> : state.data.items.length ? <ul className="space-y-2 mt-2">{state.data.items.map(r=><li key={r.id} className="text-xs">
      <strong>{r.observed_condition}</strong> · {r.review_status} · approximately {r.distance_m} m away
      <p>{r.location_description}</p><p className="text-muted">{new Intl.DateTimeFormat('en-KE',{timeZone:'Africa/Nairobi',dateStyle:'medium',timeStyle:'short'}).format(new Date(r.timestamp))} EAT · Coordinate accuracy {r.reported_accuracy_m==null?'unknown':`reported as ${r.reported_accuracy_m} m`}</p>
    </li>)}</ul> : <p className="text-xs mt-2">No coordinate-matched reports found. Reports without coordinates remain in the inbox.</p>}
    <Link className="text-xs text-brand underline mt-2 inline-block" to="/officer/reports">Open report inbox</Link>
  </section>
}
