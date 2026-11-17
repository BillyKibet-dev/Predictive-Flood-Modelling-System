"""Offline import of supplied reference coordinates into parent monitoring zones.

Preserves original evidence, keeps four previously reviewed street/school
locations, joins points to the repository's administrative polygons, and never
changes any model zone, feature contract, database or inference path.
"""
import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

from src.api.services.operational_source_storage import LocalEvidenceStore, canonical_json
from src.scripts.prepare_hotspot_catalog import ROOT, terrain_profile, drainage_profile, vegetation_profile, unknown
from src.scripts.inspect_hotspot_evidence import evidence

COORDINATE_ZIP_SHA256 = 'd87bbc2c82e8fc35c563ea57c01012bcbaf8919d1466f056d20a23f487f23de8'
BASE_SHA256 = '048da4152ae5dbc97fa05af1cd51148e273485782abbda8e9d94c627d4a36895'
OUTPUT = ROOT/'src/api/data/monitoring_areas.json'
STATUSES = {'LANDMARK_REFERENCE','NEIGHBORHOOD_REFERENCE','RELATED_LANDMARK_REFERENCE','RELATED_WATERBODY_REFERENCE','UNRESOLVED'}
LOCATION_UPDATES=ROOT/'src/api/data/monitoring_area_location_updates.json'


def dms_to_decimal(degrees,minutes,seconds,hemisphere):
    import math
    if hemisphere not in ('N','S','E','W') or any(type(v) not in (int,float) or not math.isfinite(v) for v in (degrees,minutes,seconds)):
        raise ValueError('Invalid DMS coordinate')
    limit=90 if hemisphere in ('N','S') else 180
    if not (0<=degrees<=limit and 0<=minutes<60 and 0<=seconds<60) or (degrees==limit and (minutes or seconds)):
        raise ValueError('DMS component outside geographic range')
    value=degrees+minutes/60+seconds/3600
    return round(-value if hemisphere in ('S','W') else value,9)


def apply_location_update(site,update,items,source_sha256):
    position=[dms_to_decimal(*update['longitude_dms']),dms_to_decimal(*update['latitude_dms'])]
    if update['longitude_dms'][3] not in ('E','W') or update['latitude_dms'][3] not in ('N','S'):
        raise ValueError('DMS axis mismatch')
    if update['field_verified'] is not False or update['source_kind'] not in ('user_personal_observation','user_supplied_location'):
        raise ValueError('Unsupported user-location evidence claim')
    site['location_history']=[{k:deepcopy(site[k]) for k in ('geometry','location','reference_kind','terrain','vegetation','drainage')}]
    site['geometry']={'type':'Point','coordinates':position}
    site['display_name']=update['display_name'];site['reference_kind']='USER_REPORTED_LOCATION'
    site['location']={'status':'USER_REPORTED_LOCATION','coordinates':position,'field_verified':False,
        'description':update['observation'],'method':'User-supplied degrees/minutes/seconds converted to WGS84 decimal degrees',
        'source_label':'user-location-update','source_kind':update['source_kind'],
        'original_coordinate_text':update['original_coordinate_text'],'recorded_at_utc':update['recorded_at_utc'],
        'location_update_sha256':source_sha256,
        'limitations':'User-supplied monitoring location; no independently verified event date, extent, depth or surveyed accuracy.'}
    site['historical_evidence_spatial_note']='Historical source reports describe the original named site. They have not been independently verified at the updated monitoring coordinate.'
    site['terrain']=terrain_profile(position,items)
    label='sentinel-location-update-'+site['id']
    site['vegetation']=vegetation_profile(site['id'],position,items,sample_label=label)
    # Choose an actual cached extract covering this coordinate; never inherit a
    # different site's nearest-waterway distance or claim unmapped drains absent.
    import xml.etree.ElementTree as ET
    site['drainage']=unknown('Updated point is outside the reviewed drainage extracts')
    for label in ('tmall-osm-map','uhuru-updated-osm-map','cbd-osm-map'):
        if label not in items or items[label][1]['http_status']!=200:continue
        bounds=ET.fromstring(items[label][0]).find('bounds').attrib
        if float(bounds['minlon'])<=position[0]<=float(bounds['maxlon']) and float(bounds['minlat'])<=position[1]<=float(bounds['maxlat']):
            site['drainage']=drainage_profile(position,{'source_label':label},items);break


def read_lookup(path):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=COORDINATE_ZIP_SHA256:
        raise ValueError('Coordinate package differs from the reviewed v0.2 package')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        csv_raw=archive.read('Hotspot_Coordinates_Research_Lookup.csv')
        rows=list(csv.DictReader(io.StringIO(csv_raw.decode('utf-8-sig'))))
        if len(rows)!=40 or len({r['hotspot_id'] for r in rows})!=40:
            raise ValueError('Expected the same forty distinct source records')
        for row in rows:
            if row['location_match_status'] not in STATUSES or row['flood_location_verified']!='NO':
                raise ValueError('Unexpected source location classification')
            lat,lon=row['reference_latitude_wgs84'],row['reference_longitude_wgs84']
            if bool(lat)!=bool(lon) or bool(lat)==(row['location_match_status']=='UNRESOLVED'):
                raise ValueError('Source coordinates and unresolved status disagree')
            if lat and not (-1.5<float(lat)<-1.0 and 36.6<float(lon)<37.2):
                raise ValueError('Reference is outside the reviewed Nairobi bounds')
        return raw,csv_raw,rows


def build(path,base_path=ROOT/'data/hotspots/original/hotspot_inventory_v1.json'):
    raw,csv_raw,rows=read_lookup(path)
    base_raw=Path(base_path).read_bytes()
    if hashlib.sha256(base_raw).hexdigest()!=BASE_SHA256:raise ValueError('Historical inventory changed')
    document=deepcopy(json.loads(base_raw));items=evidence()
    store=LocalEvidenceStore(ROOT/'data/hotspots/evidence')
    package_ref=store.put('raw',raw);csv_ref=store.put('raw',csv_raw)
    index=store.root/'index/coordinate-lookup-v02.json'
    if index.exists():receipt=store.read_json(json.loads(index.read_bytes()),'captures')
    else:
        receipt={'kind':'user_supplied_coordinate_lookup','imported_at_utc':datetime.now(timezone.utc).isoformat(),
            'original_filename':Path(path).name,'package':package_ref,'csv':csv_ref,
            'independently_verified':False,'description':'Reference places from user attachment, not GPS flood measurements'}
        index.write_bytes(canonical_json(store.put_json('captures',receipt)))
    if receipt['package']!=package_ref or receipt['csv']!=csv_ref:raise ValueError('Coordinate import evidence changed')
    original=ROOT/'data/hotspots/original'/Path(path).name
    if original.exists() and original.read_bytes()!=raw:raise ValueError('Original coordinate archive changed')
    if not original.exists():original.write_bytes(raw)
    sys.path.insert(0,str(ROOT/'data/hotspots/gis_dependencies'))
    from shapely.geometry import Point,shape
    boundary_raw=(ROOT/'data/boundaries/nairobi_subcounties.geojson').read_bytes()
    boundaries=json.loads(boundary_raw)['features']
    lookup={r['hotspot_id']:r for r in rows}
    if set(lookup)!={s['id'] for s in document['sites']}:raise ValueError('Source site IDs differ')
    updates_raw=LOCATION_UPDATES.read_bytes();updates=json.loads(updates_raw)
    removals=updates.get('removals',{})
    if (updates['schema_version']!='monitoring-area-location-updates-v1' or not set(updates['updates'])<=set(lookup)
            or not set(removals)<=set(lookup) or set(removals)&set(updates['updates'])):
        raise ValueError('Invalid monitored-area location updates')
    for site in document['sites']:
        row=lookup[site['id']];old_group=site['group']
        site['inventory_group']=old_group
        site['coordinate_lookup']=row
        site['display_name']=site['name']
        # Four verified OSM geometries have greater specificity than the supplied
        # rounded landmarks. In particular retain the roundabout, not the mall.
        if site['geometry'] is not None:
            site['location']['selection_note']='Retained previously reviewed native OSM reference; supplied v0.2 reference retained alongside it.'
            site['reference_kind']='LANDMARK_REFERENCE'
        elif row['location_match_status']!='UNRESOLVED':
            position=[float(row['reference_longitude_wgs84']),float(row['reference_latitude_wgs84'])]
            site['geometry']={'type':'Point','coordinates':position}
            site['reference_kind']=row['location_match_status']
            site['display_name']=row['matched_map_feature'].replace(' (OSM point)','').replace(' named OSM point','')
            site['location']={'status':row['location_match_status'],'coordinates':position,'field_verified':False,
                'description':row['review_note'],'source_url':row['coordinate_source_url'],
                'source_label':'coordinate-lookup-v02','source_package':receipt,
                'method':'User-supplied v0.2 reference coordinate; matched feature and precision limits preserved',
                'limitations':'Place/landmark reference; not an incident-specific flood coordinate or surveyed exposure point.'}
            site['terrain']=terrain_profile(position,items)
            site['vegetation']=unknown('No verified Sentinel sample at this coordinate; previous samples were not copied')
            site['drainage']=drainage_profile(position,site['location'],items)
        else:
            site['reference_kind']='UNLOCATED'
            site['location']['reason']=row['review_note']
        if site['id'] in updates['updates']:
            apply_location_update(site,updates['updates'][site['id']],items,hashlib.sha256(updates_raw).hexdigest())
        position=site['geometry']['coordinates'] if site['geometry'] else None
        matches=[f for f in boundaries if shape(f['geometry']).covers(Point(position))] if position else []
        if position and len(matches)!=1:raise ValueError('Parent administrative zone is ambiguous: '+site['id'])
        site['administrative_context']=[{'id':f['id'],'name':f['properties']['name'],
            'source_url':f['properties']['source_url'],'source_year':f['properties']['source_year'],
            'source_sha256':hashlib.sha256(boundary_raw).hexdigest(),
            'method':'Reference point covered by repository administrative polygon; does not locate the flood-affected site'} for f in matches]
        if matches:
            site['parent_zone_id']=matches[0]['id'];site['parent_zone_name']=matches[0]['properties']['name']
            site['parent_assignment']='REFERENCE_POINT_SPATIAL_JOIN'
        else:
            name=old_group.replace(' (proposed)','')
            site['parent_zone_id']='review-'+name.lower();site['parent_zone_name']=name
            site['parent_assignment']='INVENTORY_GROUP_PENDING_LOCATION'
        site['group']=site['parent_zone_name']
        site['association_status']=site['parent_assignment']
    # Records the user could not locate during manual review are removed from the
    # served inventory; the original v0.2 package and base catalogue keep them.
    for site in document['sites']:
        if site['id'] in removals and site['geometry'] is not None:
            raise ValueError('Only unlocated records may be removed: '+site['id'])
    document['sites']=[s for s in document['sites'] if s['id'] not in removals]
    document['removed_records']=[{'id':k,**v} for k,v in sorted(removals.items())]
    document['schema_version']='monitoring-area-inventory-v1'
    document['information_type']='monitoring_area_inventory'
    document['coordinate_package']=receipt
    document['location_updates_sha256']=hashlib.sha256(updates_raw).hexdigest()
    document['inventory_limitations']=[
        'The v0.2 attachment supplies 28 place/landmark coordinates and 12 unresolved records; none are incident-specific field-verified flood points.',
        'Two reviewed OSM references are retained, including one unresolved in the attachment. T-Mall, Uhuru Highway and seven previously unresolved records use separately recorded user-supplied points; four records the user could not locate were removed. Total: 36 mapped area records and no unresolved records.',
        'Neighbourhood, school and reservoir references identify the displayed feature. They do not precisely locate the associated riverbank, households or substation.',
        'Mapped records are assigned by reference-point containment in existing administrative polygons. Unlocated records retain explicitly tentative inventory groups.',
        'Coincident source coordinates remain shared; no jitter or invented additional locations is applied.',
        'Parent monitoring zones classify geography only. The frozen model zones, contracts and saved predictions are unchanged.'
    ]
    groups={}
    for site in document['sites']:
        key=site['parent_zone_id']
        group=groups.setdefault(key,{'id':key,'name':site['parent_zone_name'],'zone_id':key,
            'assignment':site['parent_assignment'],'site_count':0,'located_count':0})
        group['site_count']+=1;group['located_count']+=int(site['geometry'] is not None)
    document['groups']=sorted(groups.values(),key=lambda g:(g['id'].startswith('review-'),g['name']))
    return document


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('coordinate_zip',type=Path)
    parser.add_argument('--nearby-water-package',type=Path,required=True)
    parser.add_argument('--unosat-archive',type=Path,required=True)
    args=parser.parse_args();document=build(args.coordinate_zip)
    from src.scripts.prepare_nearby_water_context import attach_context
    document=attach_context(document,args.nearby_water_package,args.unosat_archive)
    OUTPUT.write_bytes(canonical_json(document))
    print(json.dumps({'sites':len(document['sites']),'mapped_records':sum(s['geometry'] is not None for s in document['sites']),
        'distinct_points':len({tuple(s['geometry']['coordinates']) for s in document['sites'] if s['geometry']}),
        'parent_zones':document['groups'],'sha256':hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}))
