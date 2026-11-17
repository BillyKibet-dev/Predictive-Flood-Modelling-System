import {useEffect,useRef,useState} from 'react'
import {useAuth} from '../context/AuthContext'
import useStaffList from '../hooks/useStaffList'
import {collectionStatus,requestWeatherCollection} from '../services/weatherCollection'
import {formatPredictionTime} from '../services/predictions'

export default function WeatherCollectionControl({onComplete}) {
  const {authorizedRequest}=useAuth()
  const state=useStaffList('/monitoring-areas/collection')
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [result,setResult]=useState(null)
  const [attemptId,setAttemptId]=useState(null), [now,setNow]=useState(Date.now)
  const pending=useRef(false), mounted=useRef(true)
  useEffect(()=>{
    mounted.current=true
    const timer=setInterval(()=>setNow(Date.now()),1000)
    return ()=>{mounted.current=false;clearInterval(timer)}
  },[])
  let status=null,validationError=''
  if(state.data)try{status=collectionStatus(state.data)}catch(failure){validationError=failure.message}
  const recovery=attemptId || (status?.latest?.status!=='COMPLETE' ? status?.latest?.request_id : null)
  const waiting=Boolean(status?.next_manual_at && Date.parse(status.next_manual_at)>now)
  async function collect(id) {
    if(pending.current)return
    pending.current=true;setBusy(true);setError('');setResult(null);setAttemptId(id)
    try {
      const response=await requestWeatherCollection(authorizedRequest,id)
      if(mounted.current){setResult(response);setAttemptId(null);onComplete?.()}
    } catch(failure) {
      if(mounted.current)setError(`${failure.name==='AbortError'?'The request timed out.':failure.message} Completion may be unconfirmed. Check status or resume the same attempt.`)
    } finally {
      pending.current=false
      if(mounted.current){setBusy(false);state.refresh()}
    }
  }
  const auto=status?.latest_automatic
  const btn='press inline-flex items-center h-9 px-3.5 rounded-btn text-sm font-medium disabled:opacity-50'
  return <section aria-label="Manual weather collection" className="space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="font-semibold">Weather collection</h2>
        <p className="text-sm text-muted mt-1">{status?.automatic?`Automatic, every ${status.configured_interval_hours===1?'hour':`${status.configured_interval_hours} hours`}. Next run about ${formatPredictionTime(status.next_collection_at)}.`:'Manual: nothing collects weather unless you ask.'}</p></div>
      {status?.automatic&&<span className="text-xs font-semibold px-2 py-1 rounded-full" style={{background:'color-mix(in srgb, var(--risk-low) 12%, transparent)',color:'var(--risk-low)'}}>Automatic on</span>}
    </div>
    {status&&<dl className="grid sm:grid-cols-2 gap-3 text-sm">
      {status.automatic&&<div className="rounded-btn bg-surface-2 p-3"><dt className="eyebrow">Last automatic run</dt><dd className="mt-1">{auto?<>{formatPredictionTime(auto.started_at)} · {auto.outcome==='FAILED'?<span className="text-risk-high">failed ({auto.error||'unknown error'}); the next run will retry</span>:auto.outcome==='SOURCE_UNAVAILABLE'?'provider returned no usable weather':`${auto.complete_target_count}/${auto.requested_count} places updated`}</>:'None finished yet'}</dd></div>}
      <div className="rounded-btn bg-surface-2 p-3"><dt className="eyebrow">Last attempt</dt><dd className="mt-1">{status.latest?<>{formatPredictionTime(status.latest.started_at)} · {status.latest.status==='COMPLETE'?`${status.latest.complete_target_count}/${status.latest.requested_count} target-day records complete`:'completion not yet confirmed'}</>:'None yet'}</dd></div>
    </dl>}
    {state.loading&&!status&&<p role="status" className="text-sm text-muted">Checking collection status…</p>}
    {(state.error||validationError)&&<p role="alert" className="text-sm">{state.error||validationError}</p>}
    {result&&<p role="status" className="text-sm">{result.reused?'Saved attempt verified. ':''}{result.attempt.outcome==='SOURCE_UNAVAILABLE'?'The provider response could not supply verified weather.':`${result.attempt.complete_target_count}/${result.attempt.requested_count} target-day records verified.`}</p>}
    {error&&<p role="alert" className="text-sm">{error}</p>}
    {busy&&<p role="status" className="text-sm">Collecting weather… keep this page open. A lost response does not mean it failed.</p>}
    <div className="flex flex-wrap gap-2">
      <button disabled={busy||!status||Boolean(state.error)||Boolean(validationError)||waiting||Boolean(recovery)} onClick={()=>collect(crypto.randomUUID())} className={btn+' bg-brand text-white hover:bg-brand-light'}>Collect latest weather</button>
      {recovery&&<button disabled={busy} onClick={()=>collect(recovery)} className={btn+' border border-border bg-surface hover:bg-surface-2'}>Resume same attempt</button>}
      <button disabled={busy||state.loading} onClick={state.refresh} className={btn+' border border-border bg-surface hover:bg-surface-2'}>Check collection status</button>
    </div>
    <p className="text-xs text-muted">{waiting?`Another manual collection is allowed after ${formatPredictionTime(status.next_manual_at)}. `:''}Collecting fetches weather only: it does not send alerts. Checking status only reads saved records.</p>
  </section>
}
