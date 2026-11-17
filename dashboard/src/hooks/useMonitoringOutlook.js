import { useEffect, useState } from 'react'
import { fetchMonitoringOutlook,expireOutlook } from '../services/monitoringOutlook'

export default function useMonitoringOutlook() {
  const [state,setState]=useState({data:null,loading:true,error:''}),[revision,setRevision]=useState(0)
  useEffect(()=>{
    const controller=new AbortController()
    setState({data:null,loading:true,error:''})
    fetchMonitoringOutlook({signal:controller.signal})
      .then(data=>{if(!controller.signal.aborted)setState({data,loading:false,error:''})})
      .catch(error=>{if(!controller.signal.aborted)setState({data:null,loading:false,error:error.message})})
    return ()=>controller.abort()
  },[revision])
  useEffect(()=>{
    const data=state.data
    if(!data?.available_count) return
    const deadline=Math.min(...data.areas.filter(a=>a.status==='AVAILABLE').map(a=>Date.parse(a.expires_at)))
    const timer=setTimeout(()=>setState(s=>({...s,data:expireOutlook(s.data)})),Math.max(0,deadline-Date.now()))
    return ()=>clearTimeout(timer)
  },[state.data])
  return {...state,refresh:()=>setRevision(n=>n+1)}
}
