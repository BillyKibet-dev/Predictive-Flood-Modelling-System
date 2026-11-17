"""Integrity-pinned satellite context, separate from frozen model terrain."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/'data/monitoring_point_enrichment.json'
SHA256='f7859dcdedf4301b5e8696dcd65dc338d52d127481975bff30ba4a9d262228b2'


def enrich_catalog(document):
    from src.api.services.monitoring_area_service import CATALOG_SHA256
    raw=PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA256:raise ValueError('Satellite enrichment integrity failure')
    enrichment=json.loads(raw)
    if enrichment['catalog_sha256']!=CATALOG_SHA256 or enrichment['contract_version']!='monitored-point-enrichment-v1':
        raise ValueError('Satellite enrichment catalogue mismatch')
    rows={r['area_id']:r for r in enrichment['rows']}
    if len(rows)!=len(enrichment['rows']) or set(rows)!={s['id'] for s in document['sites'] if s['geometry']}:
        raise ValueError('Satellite enrichment coverage mismatch')
    result=deepcopy(document)
    for site in result['sites']:
        if site['id'] not in rows:continue
        row=rows[site['id']]
        if row['coordinates']!=site['geometry']['coordinates']:raise ValueError('Satellite context belongs to another point')
        veg,land=row['vegetation'],row['landcover']
        if veg.get('value') is not None:
            if (veg['status']!='DERIVED_CONTEXT' or veg['scl'] not in (4,5,6)
                    or type(veg['value']) not in (int,float) or not math.isfinite(veg['value']) or not -1<=veg['value']<=1):
                raise ValueError('Invalid enriched vegetation quality')
        if land['status']=='DERIVED_CONTEXT':
            values=[land['built_up_fraction'],land['vegetation_fraction']]
            if (any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in values)
                    or sum(values)>1+1e-8 or land['reference_year']!=2021 or land['valid_pixel_count']<=0):
                raise ValueError('Invalid land-cover context')
        site['vegetation']=deepcopy(veg);site['landcover']=deepcopy(land)
    result['enrichment_sha256']=SHA256
    result['attribution']=[*result['attribution'],enrichment['attribution']]
    return result
