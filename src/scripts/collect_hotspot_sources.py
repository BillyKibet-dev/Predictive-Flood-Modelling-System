"""Bounded, cached public GIS evidence acquisition. No model or database imports."""
from datetime import datetime, timezone
import hashlib,json,time
from pathlib import Path

import requests
from src.api.services.operational_source_storage import LocalEvidenceStore,canonical_json

ROOT=Path(__file__).resolve().parents[2]
STORE=ROOT/'data/hotspots/evidence'
HEADERS={'User-Agent':'NairobiFloodWatch-HotspotResearch/0.1 (+https://github.com/BillyKibet-dev/Predictive-Flood-Modelling-System)'}


def capture(label,url,*,params=None,body=None,max_bytes=2_000_000):
    store=LocalEvidenceStore(STORE)
    identity={'label':label,'url':url,'params':params,'body':body}
    key=hashlib.sha256(canonical_json(identity)).hexdigest()
    index=store.root/'index'/(key+'.json')
    if index.exists():
        receipt=store.read_json(json.loads(index.read_bytes()),'captures')
        if receipt.get('complete') is False:
            raise ValueError('Cached request was incomplete; inspect evidence before any explicit retry')
        return store.read(receipt['raw'],'raw'),receipt
    started=datetime.now(timezone.utc).isoformat()
    method=requests.post if body is not None else requests.get
    try:
        response=method(url,params=params,**({'json':body} if body is not None else {}),headers=HEADERS,
            timeout=45,allow_redirects=True,stream=True)
        raw=b''; complete=True
        try:
            for chunk in response.iter_content(65536):
                if len(raw)+len(chunk)>max_bytes:
                    complete=False;break
                raw+=chunk
        finally:response.close()
        receipt={'identity':identity,'requested_at_utc':started,'received_at_utc':datetime.now(timezone.utc).isoformat(),
            'http_status':response.status_code,'response_url':response.url,'raw':store.put('raw',raw),
            'content_type':response.headers.get('Content-Type'),'etag':response.headers.get('ETag'),
            'last_modified':response.headers.get('Last-Modified'),'complete':complete,
            'capture_status':'COMPLETE' if complete else 'BYTE_LIMIT_REACHED'}
    except requests.RequestException as exc:
        store.put_json('captures',{'identity':identity,'requested_at_utc':started,'http_status':None,'failure_type':type(exc).__name__})
        raise ValueError('GIS source transport failed; no automatic retry') from exc
    ref=store.put_json('captures',receipt);index.parent.mkdir(parents=True,exist_ok=True)
    with index.open('xb') as f:f.write(canonical_json(ref))
    if not complete:raise ValueError('Source exceeds explicit byte bound; partial evidence retained, no automatic retry')
    return raw,receipt


def pilot():
    queries={
        'tmall':'T Mall Nairobi Kenya',
        'globe':'Globe Roundabout Nairobi Kenya',
        'mathare-school':'Mathare North Primary School Nairobi Kenya',
        'gumba':'Gumba Bridge Nairobi Kenya',
    }
    for label,q in queries.items():
        raw,r=capture(label,'https://nominatim.openstreetmap.org/search',params={
            'q':q,'format':'jsonv2','limit':5,'countrycodes':'ke','bounded':1,
            'viewbox':'36.65,-1.15,37.05,-1.45','addressdetails':1})
        print(json.dumps({'label':label,'status':r['http_status'],'body':json.loads(raw) if r['http_status']==200 else raw.decode(errors='replace')[:200]}),flush=True)
        if r['http_status'] in (401,403,429):break
        time.sleep(1.2)


def research():
    query='''[out:json][timeout:30];(way["highway"]["name"~"Kenyatta|Moi Avenue|Uhuru|Langata|Mbagathi",i](-1.33,36.79,-1.27,36.83);way["highway"]["junction"="roundabout"](around:350,-1.3122,36.8169);way["bridge"](around:250,-1.2787,36.8212););out meta geom;'''
    raw,r=capture('named-roads-and-bridges','https://overpass-api.de/api/interpreter',params={'data':query})
    print('OSM',r['http_status'],len(raw),flush=True)
    if r['http_status']==200:
        for e in json.loads(raw).get('elements',[]):print(json.dumps({'id':e['id'],'tags':e.get('tags'),'nodes':e.get('nodes',[])[:2]}),flush=True)
    raw,r=capture('planetary-api','https://planetarycomputer.microsoft.com/api/data/v1/openapi.json')
    print('POINT_PATHS',[k for k in json.loads(raw).get('paths',{}) if 'point' in k],flush=True)
    raw,r=capture('dem-tile-list','https://copernicus-dem-30m.s3.amazonaws.com/',params={'list-type':'2','prefix':'Copernicus_DSM_COG_10_S02_00_E036_00_DEM/'})
    print('DEM',r['http_status'],raw.decode()[:2000],flush=True)


def roads():
    query='''[out:json][timeout:20];way["highway"]["name"~"Kenyatta|Moi Avenue|Uhuru",i](-1.292,36.808,-1.278,36.826);out meta geom;'''
    raw,r=capture('cbd-junction-roads','https://overpass-api.de/api/interpreter',params={'data':query})
    print('ROADS',r['http_status'],len(raw),flush=True)
    if r['http_status']==200:
        for e in json.loads(raw).get('elements',[]):print(json.dumps({'id':e['id'],'tags':e.get('tags'),'nodes':len(e.get('nodes',[]))}),flush=True)
    raw,r=capture('sentinel-search','https://planetarycomputer.microsoft.com/api/stac/v1/search',params={
        'collections':'sentinel-2-l2a','bbox':'36.80,-1.33,36.88,-1.24',
        'datetime':'2026-08-01T00:00:00Z/2026-10-31T23:59:59Z','limit':8,'sortby':'+properties.eo:cloud_cover'})
    print('STAC',r['http_status'],flush=True)
    if r['http_status']==200:
        for e in json.loads(raw).get('features',[]):print(json.dumps({'id':e['id'],'cloud':e['properties'].get('eo:cloud_cover'),'date':e['properties'].get('datetime'),'bbox':e.get('bbox'),'red':e['assets'].get('B04',{}).get('raster:bands')}),flush=True)
    raw,r=capture('dem-tile-list','https://copernicus-dem-30m.s3.amazonaws.com/',params={'list-type':'2','prefix':'Copernicus_DSM_COG_10_S02_00_E036_00_DEM/'})
    import xml.etree.ElementTree as ET
    for c in ET.fromstring(raw).findall('{*}Contents'):
        key=c.find('{*}Key').text
        if key.endswith('_DEM.tif'):print('DEM_TILE',key,c.find('{*}Size').text,flush=True)


def landmarks():
    import xml.etree.ElementTree as ET
    for label,bbox in [('cbd-osm-map','36.810,-1.290,36.826,-1.282'),('tmall-osm-map','36.813,-1.316,36.821,-1.308')]:
        raw,r=capture(label,'https://api.openstreetmap.org/api/0.6/map',params={'bbox':bbox},max_bytes=8_000_000)
        print(label,r['http_status'],len(raw),flush=True)
        if r['http_status']==200:
            doc=ET.fromstring(raw)
            for w in doc.findall('way'):
                tags={t.attrib['k']:t.attrib['v'] for t in w.findall('tag')}
                if tags.get('highway') and (any(n in tags.get('name','').lower() for n in ('kenyatta','moi avenue','uhuru','langata','mbagathi')) or tags.get('junction')=='roundabout'):
                    print(json.dumps({'id':w.attrib['id'],'tags':tags}),flush=True)
    raw,_=capture('sentinel-search','https://planetarycomputer.microsoft.com/api/stac/v1/search',params={
        'collections':'sentinel-2-l2a','bbox':'36.80,-1.33,36.88,-1.24','datetime':'2026-08-01T00:00:00Z/2026-10-31T23:59:59Z','limit':8,'sortby':'+properties.eo:cloud_cover'})
    item=json.loads(raw)['features'][0]
    print('ASSETS',json.dumps(item['assets']['B04']),flush=True)
    print('BASELINE',{k:v for k,v in item['properties'].items() if any(s in k for s in ('baseline','quant','offset'))},flush=True)
    raw,r=capture('sentinel-tmall-sample','https://planetarycomputer.microsoft.com/api/data/v1/item/point/36.8169419,-1.3122475',
        params={'collection':'sentinel-2-l2a','item':item['id'],'assets':['B04','B08','SCL']})
    print('SAMPLE',r['http_status'],raw.decode()[:2500],flush=True)


def terrain():
    from src.scripts.inspect_hotspot_evidence import evidence
    item=json.loads(evidence()['sentinel-search'][0])['features'][0]
    raw,r=capture('sentinel-product-metadata',item['assets']['product-metadata']['href'])
    print('SENTINEL_METADATA',r['http_status'],raw[:150],flush=True)
    key='Copernicus_DSM_COG_10_S02_00_E036_00_DEM/Copernicus_DSM_COG_10_S02_00_E036_00_DEM.tif'
    raw,r=capture('copernicus-dem-tile','https://copernicus-dem-30m.s3.amazonaws.com/'+key,max_bytes=45_000_000)
    print('DEM_CAPTURE',r['http_status'],len(raw),r['raw']['sha256'],flush=True)
    raw,r=capture('copernicus-dem-metadata','https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_S02_00_E036_00_DEM/Copernicus_DSM_10_S02_00_E036_00.xml')
    print('DEM_METADATA',r['http_status'],len(raw),flush=True)


def sentinel_metadata():
    """Public provider SAS is kept in memory; no signed URLs enter evidence/logs."""
    from src.scripts.inspect_hotspot_evidence import evidence
    item=json.loads(evidence()['sentinel-search'][0])['features'][0]
    url=item['assets']['product-metadata']['href']
    store=LocalEvidenceStore(STORE)
    identity={'label':'sentinel-product-metadata-authorized','url':url,'params':None,'body':None}
    key=hashlib.sha256(canonical_json(identity)).hexdigest(); index=store.root/'index'/(key+'.json')
    if index.exists():
        r=store.read_json(json.loads(index.read_bytes()),'captures')
        print('METADATA_CACHED',r['http_status']);return
    started=datetime.now(timezone.utc).isoformat()
    try:
        signing=requests.get('https://planetarycomputer.microsoft.com/api/sas/v1/sign',params={'href':url},timeout=30)
        if signing.status_code!=200:raise ValueError('Public asset authorization unavailable')
        # Never persist authorization response or signed request/response URLs.
        response=requests.get(signing.json()['href'],timeout=45)
    except requests.RequestException:
        raise ValueError('Metadata transport failed; temporary authorization details withheld') from None
    raw=response.content
    if len(raw)>2_000_000:raise ValueError('Metadata exceeds byte bound')
    r={'identity':identity,'requested_at_utc':started,'received_at_utc':datetime.now(timezone.utc).isoformat(),
       'http_status':response.status_code,'response_url':url,'raw':store.put('raw',raw),
       'authorization':'provider public-asset SAS; discarded, never persisted'}
    ref=store.put_json('captures',r)
    with index.open('xb') as f:f.write(canonical_json(ref))
    print('METADATA',response.status_code,len(raw),flush=True)


def hotspot_samples():
    from src.scripts.inspect_hotspot_evidence import evidence
    from src.scripts.prepare_hotspot_catalog import landmark_locations
    items=evidence();item=json.loads(items['sentinel-search'][0])['features'][0]
    for identifier,location in landmark_locations(items).items():
        lon,lat=location['coordinates']
        raw,r=capture('sentinel-point-'+identifier,
            f'https://planetarycomputer.microsoft.com/api/data/v1/item/point/{lon},{lat}',
            params={'collection':'sentinel-2-l2a','item':item['id'],'assets':['B04','B08','SCL']})
        print(identifier,r['http_status'],raw.decode()[:300],flush=True)


def refined_points():
    from src.scripts.inspect_hotspot_evidence import evidence
    from src.scripts.prepare_monitoring_areas import LOCATION_UPDATES,dms_to_decimal
    item=json.loads(evidence()['sentinel-search'][0])['features'][0]
    updates=json.loads(LOCATION_UPDATES.read_bytes())['updates']
    for identifier,update in updates.items():
        lon=dms_to_decimal(*update['longitude_dms']);lat=dms_to_decimal(*update['latitude_dms'])
        raw,r=capture('sentinel-location-update-'+identifier,
            f'https://planetarycomputer.microsoft.com/api/data/v1/item/point/{lon},{lat}',
            params={'collection':'sentinel-2-l2a','item':item['id'],'assets':['B04','B08','SCL']},max_bytes=100_000)
        print(identifier,r['http_status'],raw.decode()[:300],flush=True)
    raw,r=capture('uhuru-updated-osm-map','https://api.openstreetmap.org/api/0.6/map',
        params={'bbox':'36.815,-1.300,36.827,-1.288'},max_bytes=8_000_000)
    print('UHURU_OSM',r['http_status'],len(raw),flush=True)


if __name__=='__main__':
    import sys
    if '--refined-points' in sys.argv:refined_points()
    elif '--samples' in sys.argv:hotspot_samples()
    elif '--sentinel-metadata' in sys.argv:sentinel_metadata()
    elif '--terrain' in sys.argv:terrain()
    elif '--landmarks' in sys.argv:landmarks()
    elif '--roads' in sys.argv:roads()
    elif '--research' in sys.argv:research()
    else:pilot()
