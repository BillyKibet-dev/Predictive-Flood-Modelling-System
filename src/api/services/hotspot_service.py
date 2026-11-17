"""Read-only, integrity-checked hotspot inventory; independent of model inference."""
import hashlib
import json
import math
from pathlib import Path
import re

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data/hotspots.json'
CATALOG_SHA256 = '048da4152ae5dbc97fa05af1cd51148e273485782abbda8e9d94c627d4a36895'
ZONE_IDS = frozenset(('cbd','dagoretti','embakasi','kasarani','kibera','mathare','ruaraka','westlands'))


class HotspotsUnavailable(ValueError):
    pass


def validate_catalog(document):
    if document.get('schema_version') != 'hotspot-inventory-v1' or document.get('information_type') != 'candidate_hotspot_inventory':
        raise HotspotsUnavailable('Unsupported inventory')
    sites = document.get('sites')
    if not isinstance(sites,list) or not sites:
        raise HotspotsUnavailable('Empty inventory')
    identifiers = set()
    source_ids = {s['source_id'] for s in document['sources']}
    for site in sites:
        identifier = site.get('id')
        if not isinstance(identifier,str) or not re.fullmatch(r'NFW-S\d{3}',identifier) or identifier in identifiers:
            raise HotspotsUnavailable('Invalid or repeated site identity')
        identifiers.add(identifier)
        if site.get('zone_id') is not None and site['zone_id'] not in ZONE_IDS:
            raise HotspotsUnavailable('Unknown monitoring zone')
        if not site.get('name') or not set(site['source_ids']) <= source_ids:
            raise HotspotsUnavailable('Site provenance is missing')
        if site['evidence_category'] not in ('OBSERVED_FLOOD_OR_IMPACT','OFFICIAL_WARNING_NAMED_SITE'):
            raise HotspotsUnavailable('Unsupported evidence category')
        if any(site.get(k) is not None for k in ('risk_score','live_flood_status','flood_extent','flood_depth')):
            raise HotspotsUnavailable('Inventory must not contain model outputs')
        geometry = site.get('geometry')
        location = site['location']
        if location.get('field_verified') is not False:
            raise HotspotsUnavailable('This inventory has no field-verified locations')
        if geometry is None:
            if location.get('status') != 'UNLOCATED':raise HotspotsUnavailable('Unlocated status mismatch')
            if any(site[k].get('status') != 'UNAVAILABLE' for k in ('terrain','vegetation','drainage')):
                raise HotspotsUnavailable('Unlocated sites cannot inherit geographic features')
        else:
            coordinates = geometry.get('coordinates')
            if geometry.get('type') != 'Point' or not isinstance(coordinates,list) or len(coordinates) != 2:
                raise HotspotsUnavailable('Only reference points are supported')
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in coordinates):
                raise HotspotsUnavailable('Invalid reference coordinate')
            if not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90:
                raise HotspotsUnavailable('Expected WGS84 coordinates')
            if location.get('status') != 'LANDMARK_REFERENCE' or location.get('coordinates') != coordinates:
                raise HotspotsUnavailable('Reference location mismatch')
        vegetation = site['vegetation']
        value = vegetation.get('value')
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or not -1 <= value <= 1
                                  or vegetation.get('scl') not in (4,5,6) or vegetation['status'] != 'DERIVED_CONTEXT'):
            raise HotspotsUnavailable('Invalid or unscreened NDVI')
    for group in document['groups']:
        members = [s for s in sites if s['group'] == group['name']]
        if len(members) != group['site_count'] or sum(s['geometry'] is not None for s in members) != group['located_count']:
            raise HotspotsUnavailable('Inventory group count mismatch')
    return document


def load_catalog():
    raw = CATALOG_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise HotspotsUnavailable('Inventory integrity check failed')
    return validate_catalog(json.loads(raw))


def list_hotspots(zone_id=None, located=None):
    document = load_catalog()
    document['sites'] = [s for s in document['sites']
        if (zone_id is None or (s['zone_id'] is None if zone_id == 'unassigned' else s['zone_id'] == zone_id))
        and (located is None or (s['geometry'] is not None) == located)]
    document['returned_count'] = len(document['sites'])
    return document


def get_hotspot(identifier):
    document = load_catalog()
    site = next((s for s in document['sites'] if s['id'] == identifier),None)
    if site is None:return None
    return {**site,'sources':[s for s in document['sources'] if s['source_id'] in site['source_ids']],
            'attribution':document['attribution'],'information_type':document['information_type']}
