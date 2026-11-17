"""Immutable geographic monitoring areas, grouped by parent administrative zone."""
import hashlib
import json
from pathlib import Path
import math
import re

CATALOG_PATH=Path(__file__).resolve().parents[1]/'data/monitoring_areas.json'
CATALOG_SHA256='f0dcd9bddfb8957d4271285259599aee6952b35fb48df9c05d2e94d63c9fc016'
LOCATED_STATUSES={'LANDMARK_REFERENCE','NEIGHBORHOOD_REFERENCE','RELATED_LANDMARK_REFERENCE','RELATED_WATERBODY_REFERENCE','USER_REPORTED_LOCATION'}
WATER_STATES={'REFERENCE_UNLOCATED','REFERENCE_OUTSIDE_2024_SCENE','REFERENCE_IN_2024_CLOUD',
    'REFERENCE_INSIDE_2024_MAPPED_WATER','MAPPED_WATER_WITHIN_250M_OF_REFERENCE',
    'MAPPED_WATER_WITHIN_500M_OF_REFERENCE','NO_WATER_WITHIN_500M_IN_2024_SCENE'}


def validate_nearby_water(context,geometry):
    if context.get('information_type')!='historical_nearby_water_reference' or context.get('status') not in WATER_STATES:
        raise ValueError('Unsupported nearby-water reference')
    if context.get('observation_date')!='2024-05-01' or context.get('source_event')!='FL20240426KEN' or context.get('search_radius_m')!=500:
        raise ValueError('Historical context identity mismatch')
    if context.get('reference_coordinates')!=(geometry['coordinates'] if geometry else None):
        raise ValueError('Historical context belongs to a different location')
    if context.get('operational_use_allowed') is not False or any(context.get(k) is not None for k in ('confirmed_flood_free','actual_incident_point','verified_flood_boundary')):
        raise ValueError('Nearby water cannot certify a flood site or safety')
    distance=context.get('distance_m')
    if distance is not None and (type(distance) not in (int,float) or not math.isfinite(distance) or not 0<=distance<=500):
        raise ValueError('Invalid historical reference distance')
    state=context['status']
    unknown=state in ('REFERENCE_UNLOCATED','REFERENCE_OUTSIDE_2024_SCENE','REFERENCE_IN_2024_CLOUD')
    if unknown and (distance is not None or context.get('mapped_water_area_m2') is not None):
        raise ValueError('Unknown observation cannot carry a water measurement')
    if (geometry is None)!=(state=='REFERENCE_UNLOCATED'):raise ValueError('Historical reference missingness mismatch')
    if state=='MAPPED_WATER_WITHIN_250M_OF_REFERENCE' and (distance is None or not 0<distance<=250):raise ValueError('Near-water class mismatch')
    if state=='MAPPED_WATER_WITHIN_500M_OF_REFERENCE' and (distance is None or not 250<distance<=500):raise ValueError('Near-water class mismatch')
    if state=='REFERENCE_INSIDE_2024_MAPPED_WATER' and distance!=0:raise ValueError('Water intersection must have zero distance')
    if state=='NO_WATER_WITHIN_500M_IN_2024_SCENE' and distance is not None:raise ValueError('Unsupported distance for no mapped water')
    area=context.get('mapped_water_area_m2')
    if area is not None and (type(area) not in (int,float) or not math.isfinite(area) or area<0):raise ValueError('Invalid historical water area')
    if distance is not None and (area is None or area<=0):raise ValueError('Water proximity requires actual mapped water')
    for key in ('usable_coverage_percent','analysis_coverage_percent','cloud_cover_percent'):
        value=context.get(key)
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=100):
            raise ValueError('Invalid historical coverage percentage')
    return context


class UnknownParentZone(ValueError):
    pass


def validate_catalog(document):
    if document.get('schema_version')!='monitoring-area-inventory-v1' or document.get('information_type')!='monitoring_area_inventory':
        raise ValueError('Unsupported monitoring inventory')
    sites=document['sites'];groups=document['groups'];seen=set()
    group_by_id={g['id']:g for g in groups}
    if len(group_by_id)!=len(groups) or not sites:raise ValueError('Missing or repeated zone')
    sources={s['source_id'] for s in document['sources']}
    for site in sites:
        if not re.fullmatch(r'NFW-S\d{3}',site['id']) or site['id'] in seen:raise ValueError('Repeated area ID')
        seen.add(site['id'])
        group=group_by_id[site['parent_zone_id']]
        if not site['display_name'] or site['parent_zone_name']!=group['name']:raise ValueError('Invalid parent zone')
        if not set(site['source_ids'])<=sources:raise ValueError('Missing evidence source')
        if any(site.get(k) is not None for k in ('risk_score','live_flood_status','flood_extent','flood_depth')):
            raise ValueError('Geographic areas cannot contain invented model outputs')
        geometry=site['geometry'];location=site['location']
        if location['field_verified'] is not False:raise ValueError('No field verification has been established')
        if location['status']=='USER_REPORTED_LOCATION' and location.get('source_kind') not in ('user_personal_observation','user_supplied_location'):
            raise ValueError('User-reported point is missing its observation provenance')
        if geometry is None:
            if location['status']!='UNLOCATED' or site['parent_assignment']!='INVENTORY_GROUP_PENDING_LOCATION':
                raise ValueError('Unlocated area assigned as a spatial match')
            if not group['id'].startswith('review-') or any(site[k]['status']!='UNAVAILABLE' for k in ('terrain','vegetation','drainage')):
                raise ValueError('Unlocated area has invented attributes')
        else:
            coords=geometry['coordinates']
            if geometry['type']!='Point' or len(coords)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in coords):
                raise ValueError('Invalid reference point')
            if not -180<=coords[0]<=180 or not -90<=coords[1]<=90 or coords!=location['coordinates']:
                raise ValueError('Reference coordinate mismatch')
            if location['status'] not in LOCATED_STATUSES or site['parent_assignment']!='REFERENCE_POINT_SPATIAL_JOIN':
                raise ValueError('Invalid reference classification')
            if len(site['administrative_context'])!=1 or site['administrative_context'][0]['id']!=site['parent_zone_id']:
                raise ValueError('Reference parent zone mismatch')
        v=site['vegetation'];value=v.get('value')
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not -1<=value<=1 or v.get('scl') not in (4,5,6)):
            raise ValueError('Invalid vegetation context')
        validate_nearby_water(site['nearby_water_reference'],geometry)
    for group in groups:
        members=[s for s in sites if s['parent_zone_id']==group['id']]
        if len(members)!=group['site_count'] or sum(s['geometry'] is not None for s in members)!=group['located_count']:
            raise ValueError('Parent zone count mismatch')
    return document


def load_catalog():
    raw=CATALOG_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CATALOG_SHA256:raise ValueError('Monitoring inventory integrity failure')
    return validate_catalog(json.loads(raw))


def list_areas(parent_zone_id=None,located=None):
    document=load_catalog()
    from src.api.services.monitoring_point_enrichment import enrich_catalog
    document=enrich_catalog(document)
    if parent_zone_id is not None and parent_zone_id not in {g['id'] for g in document['groups']}:
        raise UnknownParentZone('Unknown parent zone')
    document['sites']=[s for s in document['sites']
        if (parent_zone_id is None or s['parent_zone_id']==parent_zone_id)
        and (located is None or (s['geometry'] is not None)==located)]
    document['returned_count']=len(document['sites'])
    return document
