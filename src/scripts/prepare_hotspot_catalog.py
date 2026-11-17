"""Reproducibly compile the reviewed inventory and cached public GIS evidence.

Offline only. Optional rasterio/shapely live in the isolated GIS dependency target;
neither is imported by the API. No model, scheduler or database writes.
"""
import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

from src.api.services.operational_source_storage import canonical_json
from src.scripts.inspect_hotspot_evidence import evidence

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'src/api/data/hotspots.json'
ZIP_SHA256 = 'd0ea8b1893b38a151ccfbefc03b9c8b142062830c8a360a42be2b61686076005'
GROUPS = ('CBD', 'Dagoretti', 'Embakasi', 'Kasarani', 'Kibera', 'Mathare', 'Ruaraka', 'Westlands', 'Langata (proposed)')


def source_ref(receipt):
    return {key: receipt[key] for key in ('identity', 'requested_at_utc', 'received_at_utc', 'http_status', 'raw')}


def osm_document(raw):
    doc = ET.fromstring(raw)
    nodes = {n.attrib['id']: [float(n.attrib['lon']), float(n.attrib['lat'])] for n in doc.findall('node')}
    ways = {w.attrib['id']: {'nodes': [n.attrib['ref'] for n in w.findall('nd')],
            'tags': {t.attrib['k']: t.attrib['v'] for t in w.findall('tag')}} for w in doc.findall('way')}
    return nodes, ways


def mean_position(nodes, identifiers):
    ids = sorted(set(identifiers))
    if not ids:
        raise ValueError('A reviewed landmark must contain native OSM nodes')
    return [round(sum(nodes[n][i] for n in ids) / len(ids), 7) for i in (0, 1)]


def junction(nodes, ways, second_name):
    first = {n for w in ways.values() if w['tags'].get('name') == 'Kenyatta Avenue'
             and w['tags'].get('highway') in ('secondary', 'trunk') for n in w['nodes']}
    second = {n for w in ways.values() if w['tags'].get('name') == second_name
              and w['tags'].get('highway') in ('secondary', 'trunk') for n in w['nodes']}
    shared = sorted(first & second)
    return mean_position(nodes, shared), shared


def school_match(results):
    # A drinking-water point and toilets share the school name: never pick rank 1.
    matches = [r for r in results if r.get('osm_type') == 'node' and r.get('osm_id') == 6445132387
               and r.get('type') == 'school' and r.get('name') == 'Mathare North Primary School']
    if len(matches) != 1:
        raise ValueError('Reviewed school identity is absent or ambiguous')
    return [float(matches[0]['lon']), float(matches[0]['lat'])]


def landmark_locations(items):
    nodes, ways = osm_document(items['cbd-osm-map'][0])
    locations = {}
    for identifier, second in [('NFW-S002', 'Moi Avenue'), ('NFW-S003', 'Uhuru Highway')]:
        position, shared = junction(nodes, ways, second)
        locations[identifier] = {'coordinates': position, 'source_label': 'cbd-osm-map',
            'osm_node_ids': shared, 'method': 'Mean of unique nodes shared by the two named carriageways',
            'description': 'Junction reference point; lane geometry is generalized to one pin.'}
    nodes, ways = osm_document(items['tmall-osm-map'][0])
    ids = ('659301392', '1115305149', '1117239310', '1117239311', '1120644824', '1151077120', '1153342971')
    if any(ways[i]['tags'].get('junction') != 'roundabout' for i in ids):
        raise ValueError('Reviewed T-Mall roundabout geometry changed')
    locations['NFW-S037'] = {'coordinates': mean_position(nodes, [n for i in ids for n in ways[i]['nodes']]),
        'source_label': 'tmall-osm-map', 'osm_way_ids': list(ids),
        'method': 'Mean of unique native nodes of the reviewed T-Mall roundabout carriageways',
        'description': 'Roundabout reference point, west of the T-Mall building; not a flooded-road survey.'}
    locations['NFW-S028'] = {'coordinates': school_match(json.loads(items['mathare-school'][0])),
        'source_label': 'mathare-school', 'osm_node_ids': ['6445132387'],
        'method': 'Reviewed school amenity node, excluding same-name water and toilet amenities',
        'description': 'School landmark for the reported environs; the affected households remain unlocated.'}
    for location in locations.values():
        location['status'] = 'LANDMARK_REFERENCE'
        location['field_verified'] = False
        location['source'] = source_ref(items[location['source_label']][1])
        location['limitations'] = 'OpenStreetMap reference, not a field-checked flood location, boundary or inundation extent.'
    return locations


def horn_slope(window, dx, dy):
    if len(window) != 3 or any(len(row) != 3 for row in window) or dx <= 0 or dy <= 0:
        raise ValueError('Horn slope needs a 3x3 valid window and positive metre spacing')
    if any(not math.isfinite(float(v)) for row in window for v in row):
        raise ValueError('Missing elevation cannot be replaced with zero')
    a,b,c,d,e,f,g,h,i = [float(v) for row in window for v in row]
    gx = ((c + 2*f + i) - (a + 2*d + g)) / (8*dx)
    gy = ((g + 2*h + i) - (a + 2*b + c)) / (8*dy)
    return math.degrees(math.atan(math.hypot(gx, gy)))


def ndvi_from_dn(red, nir, scl, red_offset, nir_offset, quantification):
    if scl not in (4, 5, 6):
        return None
    if any(v is None or not math.isfinite(float(v)) or v in (0, 65535) for v in (red, nir)) or quantification <= 0:
        return None
    r, n = (red + red_offset)/quantification, (nir + nir_offset)/quantification
    if r < 0 or n < 0 or r+n <= 0:
        return None
    return (n-r)/(n+r)


def unknown(reason):
    return {'status': 'UNAVAILABLE', 'value': None, 'reason': reason}


def terrain_profile(position, items):
    import rasterio
    from rasterio.windows import Window
    lon, lat = position
    receipt = items['copernicus-dem-tile'][1]
    path = ROOT/'data/hotspots/evidence'/receipt['raw']['path']
    with rasterio.open(path) as raster:
        if not raster.crs.is_geographic or 'SPHEROID["WGS 84",6378137,298.257223563]' not in raster.crs.to_wkt():
            raise ValueError('Expected geographic Copernicus tile')
        row, col = raster.index(lon, lat)
        values = raster.read(1, window=Window(col-1, row-1, 3, 3), masked=True)
        if values.shape != (3,3) or values.mask.any():
            return unknown('Incomplete native elevation neighbourhood')
        latitude = math.radians(raster.xy(row, col)[1])
        eccentricity = 6.69437999014e-3
        prime = 6378137 / math.sqrt(1-eccentricity*math.sin(latitude)**2)
        meridian = 6378137*(1-eccentricity)/(1-eccentricity*math.sin(latitude)**2)**1.5
        dx = abs(math.radians(raster.res[0])*prime*math.cos(latitude))
        dy = abs(math.radians(raster.res[1])*meridian)
        return {'status':'DERIVED_CONTEXT', 'elevation_m':round(float(values[1,1]),2),
            'slope_degrees':round(horn_slope(values.tolist(),dx,dy),3),
            'method':'Horn 3x3 gradient; WGS84 radii convert native angular spacing to metres at the central pixel',
            'native_3x3_m':values.tolist(), 'native_row':row,'native_col':col,
            'pixel_spacing_m':[dx,dy], 'pixel_center':list(raster.xy(row,col)),
            'source':source_ref(receipt),'metadata_source':source_ref(items['copernicus-dem-metadata'][1]),
            'native_crs_wkt':raster.crs.to_wkt(),
            'dataset':'Copernicus DEM GLO-30 public DSM tile; EGM2008 orthometric heights',
            'acquisition_period':'2011–2015 main TanDEM-X acquisition period; not a current terrain survey',
            'resolution':'1 arc-second, approximately 30 m; slope uses a 3x3 neighbourhood',
            'source_url':'https://registry.opendata.aws/copernicus-dem/',
            'limitations':'Surface model includes buildings and vegetation. Cannot resolve roadside drains, capacity, blockage or flood depth.'}


def vegetation_profile(identifier, position, items, sample_label=None):
    label = sample_label or 'sentinel-point-' + identifier
    if label not in items or items[label][1]['http_status'] != 200:
        return unknown('No verified Sentinel point response for this reference coordinate')
    item = json.loads(items['sentinel-search'][0])['features'][0]
    metadata = ET.fromstring(items['sentinel-product-metadata-authorized'][0])
    quantification = float(metadata.find('.//BOA_QUANTIFICATION_VALUE').text)
    offsets = {e.attrib['band_id']:float(e.text) for e in metadata.findall('.//BOA_ADD_OFFSET')}
    sample = json.loads(items[label][0])
    if sample.get('coordinates') != position:
        raise ValueError('Sentinel sample coordinates differ from reviewed landmark')
    bands = dict(zip(sample['band_names'], sample['values'], strict=True))
    red, nir, scl = (bands.get(k) for k in ('B04_b1','B08_b1','SCL_b1'))
    value = ndvi_from_dn(red,nir,scl,offsets['3'],offsets['7'],quantification)
    return {'status':'DERIVED_CONTEXT' if value is not None else 'WITHHELD_QUALITY',
        'value':round(value,5) if value is not None else None,'units':'NDVI, dimensionless',
        'raw_dn':{'B04':red,'B08':nir},'scl':scl,'accepted_scl_classes':[4,5,6],
        'offsets':{'B04':offsets['3'],'B08':offsets['7']},'quantification':quantification,
        'method':'BOA=(DN+band offset)/quantification; NDVI=(B08-B04)/(B08+B04); accept SCL vegetation/bare/water only',
        'scene_id':item['id'],'acquired_at_utc':item['properties']['datetime'],
        'scene_selection':'Lowest scene cloud cover among first eight results ordered by cloud cover, 1 August–31 October 2026',
        'resolution':'Single nearest 10 m red/NIR pixels and native 20 m SCL class at a landmark; not a site area mean',
        'source':source_ref(items[label][1]),'metadata_source':source_ref(items['sentinel-product-metadata-authorized'][1]),
        'catalog_source':source_ref(items['sentinel-search'][1]),
        'source_url':'https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a',
        'limitations':'Dated vegetation context, not live vegetation or vegetation at the historical flood event. No uncertainty or flood effect is calibrated.'}


def drainage_profile(position, location, items):
    from shapely.geometry import LineString, Point, box
    label = location['source_label']
    if label not in ('cbd-osm-map','tmall-osm-map','uhuru-updated-osm-map'):
        return unknown('No reviewed local waterway extract; field drainage survey remains required')
    raw, receipt = items[label]
    doc = ET.fromstring(raw); bounds = doc.find('bounds').attrib
    west,south,east,north = [float(bounds[k]) for k in ('minlon','minlat','maxlon','maxlat')]
    nodes,ways = osm_document(raw)
    lon,lat=position
    def metres(p):return ((p[0]-lon)*111320*math.cos(math.radians(lat)),(p[1]-lat)*110574)
    extent=box(*metres((west,south)),*metres((east,north)))
    matches=[]
    for identifier,way in ways.items():
        if way['tags'].get('waterway') not in ('river','stream','drain','ditch','canal'):continue
        line=LineString([metres(nodes[n]) for n in way['nodes']]).intersection(extent)
        if not line.is_empty:matches.append({'osm_way_id':identifier,'name':way['tags'].get('name','Unnamed mapped waterway'),
            'waterway':way['tags']['waterway'],'tunnel':way['tags'].get('tunnel'),
            'distance_m':round(Point(0,0).distance(line),1)})
    return {'status':'MAPPED_CONTEXT' if matches else 'NOT_MAPPED_IN_EXTRACT',
        'nearest_mapped_waterway':min(matches,key=lambda m:m['distance_m']) if matches else None,
        'mapped_culverts':[m for m in matches if m['tunnel']=='culvert'],
        'extract_bbox':[west,south,east,north], 'source':source_ref(receipt),
        'method':'Shortest planar distance to clipped mapped waterway lines in this bounded OSM extract; local WGS84 metre approximation',
        'capacity':None,'condition':None,'blockage':None,'surveyed':False,
        'limitations':'OSM mapping may be incomplete. Absence is not evidence of no drainage. Proximity does not establish overflow, flow connectivity, capacity or blockage.'}


def inventory(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ZIP_SHA256:
        raise ValueError('Inventory ZIP differs from the reviewed package')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read('MANIFEST.json'))
        checks = {}
        for name, ref in manifest['files'].items():
            member = archive.read(name)
            checks[name] = {'sha256':hashlib.sha256(member).hexdigest(), 'bytes':len(member),
                'matches_supplied_manifest':len(member)==ref['bytes'] and hashlib.sha256(member).hexdigest()==ref['sha256']}
            if name != 'MANIFEST.json' and not checks[name]['matches_supplied_manifest']:
                raise ValueError('Inventory member integrity failure: '+name)
        def rows(name):return list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig'))))
        sites = rows('01_Specific_Hotspots.csv')
        if len(sites)!=40 or any(r['latitude'] or r['longitude'] or r['risk_score'] for r in sites):
            raise ValueError('Unexpected inventory counts or prepopulated derived values')
        return raw,sites,rows('02_Government_Corridor_Names.csv'),rows('03_Evidence_Sources.csv'),checks


def build(path):
    raw,rows,corridors,sources,checks=inventory(path)
    items=evidence(); locations=landmark_locations(items)
    sys.path.insert(0,str(ROOT/'data/hotspots/gis_dependencies'))
    from shapely.geometry import Point, shape
    boundary_raw=(ROOT/'data/boundaries/nairobi_subcounties.geojson').read_bytes()
    boundaries=json.loads(boundary_raw)['features']
    sites=[]
    for row in rows:
        group=row['monitoring_group_provisional']
        if group == 'Langata proposed':group = 'Langata (proposed)'
        identifier=row['hotspot_id']; location=locations.get(identifier)
        if group not in GROUPS:raise ValueError('Unknown inventory group: '+repr(group))
        site={'id':identifier,'name':row['name'],'group':group,
            'zone_id':None if group=='Langata (proposed)' else group.lower(),
            'association_status':'PROVISIONAL_INVENTORY_GROUP','subarea_context':row['subarea_context'],
            'evidence_category':row['evidence_category'],'evidence_date':row['evidence_date'],
            'evidence_summary':row['evidence_summary'],'source_ids':row['source_ids'].split(';'),
            'verification_priority':row['priority_for_verification'],
            'reported_mechanism_hypothesis':row['flood_mechanism_hypothesis'],
            'geometry':{'type':'Point','coordinates':location['coordinates']} if location else None,
            'location':location or {'status':'UNLOCATED','field_verified':False,
                'reason':'Named reach, informal subarea or ambiguous landmark requires GIS or field review; no zone-centroid substitution.'},
            'administrative_context':[], 'terrain':unknown('Location not established'),
            'vegetation':unknown('Location not established'),'drainage':unknown('Location not established'),
            'risk_score':None,'live_flood_status':None,'flood_extent':None,'flood_depth':None}
        if location:
            point=Point(location['coordinates'])
            site['administrative_context']=[{'id':f['id'],'name':f['properties']['name'],
                'source_url':f['properties']['source_url'],'source_year':f['properties']['source_year'],
                'source_sha256':hashlib.sha256(boundary_raw).hexdigest(),
                'method':'Point covered by repository administrative polygon; independent of inventory group'}
                for f in boundaries if shape(f['geometry']).covers(point)]
            site['terrain']=terrain_profile(location['coordinates'],items)
            site['vegetation']=vegetation_profile(identifier,location['coordinates'],items)
            site['drainage']=drainage_profile(location['coordinates'],location,items)
        sites.append(site)
    original=ROOT/'data/hotspots/original'/Path(path).name
    original.parent.mkdir(parents=True,exist_ok=True)
    if original.exists() and original.read_bytes()!=raw:raise ValueError('Original archive changed')
    if not original.exists():original.write_bytes(raw)
    return {'schema_version':'hotspot-inventory-v1','information_type':'candidate_hotspot_inventory',
        'inventory_sha256':ZIP_SHA256,'source_member_checks':checks,
        'inventory_limitations':['All package coordinates were blank. Four landmark references were independently reviewed against cached OSM features.',
            'Inventory groups are provisional project associations, not an administrative spatial join.',
            'Press reports describe historical impacts or warnings; neither proves a current flood or surveyed footprint.',
            'The supplied manifest has a stale self-entry; all other member hashes match.',
            'Source headline reports 37 corridors but the literal list contains 38. These broad names are not point hotspots.',
            'The reported county inventory of 246 geocoded hotspots was not supplied.'],
        'attribution':['OpenStreetMap contributors, ODbL 1.0: https://www.openstreetmap.org/copyright',
            'Contains modified Copernicus Sentinel data (2026), via Microsoft Planetary Computer.',
            'Copernicus DEM GLO-30: https://registry.opendata.aws/copernicus-dem/; see product licence.',
            'Terrain derivatives produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.',
            'Administrative polygons: geoBoundaries / IEBC / OCHA ROSEA, CC BY 3.0 IGO.'],
        'groups':[{'name':g,'zone_id':None if g=='Langata (proposed)' else g.lower(),
            'site_count':sum(s['group']==g for s in sites),'located_count':sum(s['group']==g and s['geometry'] is not None for s in sites)} for g in GROUPS],
        'geocoding_review_notes':['Globe search found several road segments and a park, not an unambiguous damaged bridge: unlocated.',
            'Gumba search found a Bridge International Academy school and toilets, not a verified bridge: unlocated.',
            'Mathare school search first result is drinking water: rejected; selected the school amenity node.'],
        'collection_outcomes':[source_ref(r) for _,r in sorted(items.values(),key=lambda pair:pair[1]['identity']['label'])],
        'sites':sites,'corridors':corridors,'sources':sources}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('inventory_zip',type=Path)
    args=parser.parse_args();document=build(args.inventory_zip)
    OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_bytes(canonical_json(document))
    print(json.dumps({'sites':len(document['sites']),'located':sum(s['geometry'] is not None for s in document['sites']),
        'output':str(OUTPUT.relative_to(ROOT)),'sha256':hashlib.sha256(OUTPUT.read_bytes()).hexdigest()}))
