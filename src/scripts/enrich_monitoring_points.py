"""Bounded satellite context enrichment; cached requests, offline reproducible build.

No training, prediction, source-contract changes or database imports.
"""
import argparse
import json
import math
from pathlib import Path
import sys

from src.api.services.monitoring_area_service import load_catalog, CATALOG_SHA256
from src.api.services.operational_source_storage import canonical_json
from src.scripts.collect_hotspot_sources import capture
from src.scripts.inspect_hotspot_evidence import evidence
from src.scripts.prepare_hotspot_catalog import terrain_profile, vegetation_profile, source_ref, unknown

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'src/api/data/monitoring_point_enrichment.json'
VEGETATION_CLASSES={10,20,30,40,90,95,100}
VALID_CLASSES=VEGETATION_CLASSES | {50,60,70,80}


def context_polygon(position):
    lon,lat=position
    dx=250/(111320*math.cos(math.radians(lat)));dy=250/110574
    return dict(type='Feature',properties={},geometry=dict(type='Polygon',coordinates=[[
        [lon-dx,lat-dy],[lon+dx,lat-dy],[lon+dx,lat+dy],[lon-dx,lat+dy],[lon-dx,lat-dy]]]))


def landcover_profile(position, items):
    label='worldcover-context-'+','.join(map(str,position))
    if label not in items or items[label][1]['http_status']!=200:
        return unknown('No successful WorldCover context subset')
    raw,receipt=items[label]
    if receipt['identity']['body']!=context_polygon(position):
        raise ValueError('WorldCover subset belongs to different coordinates')
    result=json.loads(raw)
    stats=result['properties']['statistics']['map_b1']
    if stats.get('valid_percent')!=100 or stats.get('masked_pixels')!=0:
        return unknown('Incomplete WorldCover context; no missing-to-zero fill')
    counts,categories=stats['histogram']
    if len(counts)!=len(categories) or len(set(categories))!=len(categories):
        raise ValueError('Invalid categorical histogram')
    histogram={int(c):n for c,n in zip(categories,counts,strict=True)}
    if any(c not in VALID_CLASSES or c!=original for c,original in zip(histogram,categories)):
        raise ValueError('Unrecognised WorldCover class')
    if any(type(n) not in (int,float) or not math.isfinite(n) or n<0 for n in counts):
        raise ValueError('Invalid WorldCover histogram count')
    total=math.fsum(counts)
    if not total>0 or not math.isclose(total,stats['count'],abs_tol=1e-6):
        raise ValueError('WorldCover histogram is incomplete')
    return dict(status='DERIVED_CONTEXT',built_up_fraction=histogram.get(50,0)/total,
        vegetation_fraction=math.fsum(histogram.get(c,0) for c in VEGETATION_CLASSES)/total,
        histogram={str(c):n for c,n in histogram.items()},valid_pixel_count=total,
        reference_year=2021,source=source_ref(receipt),
        catalog_source=source_ref(items['worldcover-2021-nairobi-search'][1]),
        method='Native categorical WorldCover pixels in a 500 m by 500 m context box; fractions of valid pixel counts.',
        vegetation_classes=sorted(VEGETATION_CLASSES),built_up_class=50,
        context_polygon=context_polygon(position),resolution='WorldCover 2021 v200 10 m; nearest categorical sampling, max_size 1024',
        source_url='https://esa-worldcover.org/en/data-access',
        limitations='Built-up class is a land-cover proxy, not measured imperviousness. Context box is not a flood catchment. 2021 cover is static and may have changed.')


def fetch(include_dem=False):
    doc=load_catalog();points={tuple(s['geometry']['coordinates']):s for s in doc['sites'] if s['geometry']}
    raw,r=capture('worldcover-2021-nairobi-search','https://planetarycomputer.microsoft.com/api/stac/v1/search',params={
        'collections':'esa-worldcover','bbox':'36.70,-1.45,37.15,-1.15',
        'datetime':'2021-01-01T00:00:00Z/2021-12-31T23:59:59Z','limit':5},max_bytes=100000)
    if r['http_status']!=200:raise ValueError('WorldCover discovery failed; stop')
    wc=json.loads(raw)['features']
    scene=json.loads(evidence()['sentinel-search'][0])['features'][0]
    for position,site in points.items():
        if site['vegetation'].get('value') is None:
            label='sentinel-extra-'+','.join(map(str,position))
            _,r=capture(label,'https://planetarycomputer.microsoft.com/api/data/v1/item/point/'+','.join(map(str,position)),
                params={'collection':'sentinel-2-l2a','item':scene['id'],'assets':['B04','B08','SCL']},max_bytes=20000)
            print(json.dumps({'source':'ndvi','area':site['id'],'http_status':r['http_status']}),flush=True)
            if r['http_status'] in (401,403,429):raise ValueError('Provider access/rate failure; stop')
        matches=[f for f in wc if f['bbox'][0]<=position[0]<=f['bbox'][2] and f['bbox'][1]<=position[1]<=f['bbox'][3]]
        if len(matches)!=1:continue
        _,r=capture('worldcover-context-'+','.join(map(str,position)),
            'https://planetarycomputer.microsoft.com/api/data/v1/item/statistics',
            params={'collection':'esa-worldcover','item':matches[0]['id'],'assets':'map',
                    'categorical':'true','max_size':1024,'resampling':'nearest'},
            body=context_polygon(position),max_bytes=100000)
        print(json.dumps({'source':'landcover','area':site['id'],'http_status':r['http_status']}),flush=True)
        if r['http_status'] in (401,403,429):raise ValueError('Provider access/rate failure; stop')
    if include_dem and any(s['terrain']['status']=='UNAVAILABLE' and s['geometry'] for s in doc['sites']):
        stem='Copernicus_DSM_COG_10_S02_00_E037_00_DEM'
        url='https://copernicus-dem-30m.s3.amazonaws.com/'+stem+'/'
        capture('copernicus-dem-e037-tile',url+stem+'.tif',max_bytes=45_000_000)
        capture('copernicus-dem-e037-metadata',url+'Copernicus_DSM_10_S02_00_E037_00.xml',max_bytes=100000)


def build():
    sys.path.insert(0,str(ROOT/'data/hotspots/gis_dependencies'))
    items=evidence();doc=load_catalog();rows=[]
    for s in doc['sites']:
        if not s['geometry']:continue
        position=s['geometry']['coordinates']
        vegetation=s['vegetation']
        if vegetation.get('value') is None:
            vegetation=vegetation_profile(s['id'],position,items,sample_label='sentinel-extra-'+','.join(map(str,position)))
        rows.append(dict(area_id=s['id'],coordinates=position,vegetation=vegetation,
                         landcover=landcover_profile(position,items)))
        if s['terrain']['status']=='UNAVAILABLE' and 'copernicus-dem-e037-tile' in items:
            extra=items.copy();extra['copernicus-dem-tile']=items['copernicus-dem-e037-tile']
            extra['copernicus-dem-metadata']=items['copernicus-dem-e037-metadata']
            if extra['copernicus-dem-tile'][1]['http_status']==extra['copernicus-dem-metadata'][1]['http_status']==200:
                rows[-1]['terrain']=terrain_profile(position,extra)
    output=dict(contract_version='monitored-point-enrichment-v1',catalog_sha256=CATALOG_SHA256,rows=rows,
        attribution='© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium, CC BY 4.0; Contains modified Copernicus Sentinel data (2026).')
    OUTPUT.write_bytes(canonical_json(output))
    import hashlib
    print(json.dumps(dict(output=str(OUTPUT.relative_to(ROOT)),sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        ndvi=sum(r['vegetation'].get('value') is not None for r in rows),
        landcover=sum(r['landcover']['status']=='DERIVED_CONTEXT' for r in rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fetch',action='store_true')
    p.add_argument('--terrain-tile',action='store_true',help='Explicit extra bounded DEM attempt; not automatically retried')
    args=p.parse_args()
    if args.fetch:fetch(include_dem=args.terrain_tile)
    build()
