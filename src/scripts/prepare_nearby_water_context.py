"""Offline historical nearby-water references, never flood labels or forecasts."""
from collections import Counter
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import zipfile

from src.api.services.operational_source_storage import LocalEvidenceStore,canonical_json
from src.scripts.prepare_hotspot_catalog import ROOT

PACKAGE_SHA256='8bb518412e752b4d18548f3dca79eb6f315bc5c203d4eb42cfa0aa2514f9ba78'
ARCHIVE_SHA256='6409ef50e77bfc9f21583cbfb08c24b23730206480da7153b47f9bb59ffe80f7'
PREFIX='NairobiFloodWatch_Hotspot_GIS_Verification_v0_3/'


def classify_reference(in_analysis,in_cloud,in_water,distance):
    if not in_analysis:return 'REFERENCE_OUTSIDE_2024_SCENE'
    if in_cloud:return 'REFERENCE_IN_2024_CLOUD'
    if in_water:return 'REFERENCE_INSIDE_2024_MAPPED_WATER'
    if distance is not None and distance<=250:return 'MAPPED_WATER_WITHIN_250M_OF_REFERENCE'
    if distance is not None and distance<=500:return 'MAPPED_WATER_WITHIN_500M_OF_REFERENCE'
    return 'NO_WATER_WITHIN_500M_IN_2024_SCENE'


class NativeScene:
    def __init__(self,archive_raw,provenance):
        from shapely import from_wkb
        from shapely.ops import unary_union
        from shapely.strtree import STRtree
        from src.scripts.prepare_unosat_evidence import read_native
        native={}
        with zipfile.ZipFile(io.BytesIO(archive_raw)) as z:
            def member(name):
                matches=[n for n in z.namelist() if n.rsplit('/',1)[-1]==name]
                if len(matches)!=1:raise ValueError('Missing or ambiguous native scene member')
                return z.read(matches[0])
            for kind,key in [('flood','native_flood_shp_sha256'),('coverage','native_analysis_shp_sha256'),('cloud','native_cloud_shp_sha256')]:
                rows,metadata=read_native(member,kind)
                digest=next(v['sha256'] for k,v in metadata['members'].items() if k.endswith('.shp'))
                if digest!=provenance[key]:raise ValueError('Historical native scene hash mismatch')
                native[kind]=[from_wkb(bytes.fromhex(r['wkb'])) for r in rows]
        if [len(native[k]) for k in ('flood','coverage','cloud')]!=[1,1,2]:raise ValueError('Unexpected native scene counts')
        self.coverage=self.metric(native['coverage'][0])
        self.clouds=unary_union([self.metric(g) for g in native['cloud']])
        self.usable=self.coverage.difference(self.clouds)
        self.parts=list(native['flood'][0].geoms);self.tree=STRtree(self.parts);self.cache={}

    @staticmethod
    def metric(geometry):
        from shapely.ops import transform
        from rasterio.warp import transform as project
        def convert(x,y,z=None):
            if isinstance(x,(int,float)):
                xx,yy=project('EPSG:4326','EPSG:32737',[x],[y]);return xx[0],yy[0]
            return project('EPSG:4326','EPSG:32737',list(x),list(y))
        return transform(convert,geometry)

    def inspect(self,position):
        from shapely.geometry import Point,box,GeometryCollection
        from shapely.ops import unary_union
        from shapely import make_valid
        if position is None:return {'status':'REFERENCE_UNLOCATED','distance_m':None,
            'mapped_water_area_m2':None,'usable_coverage_percent':None,'analysis_coverage_percent':None,'cloud_cover_percent':None}
        lon,lat=position;point=self.metric(Point(lon,lat));region=point.buffer(500,quad_segs=32)
        patches=[]
        for index in self.tree.query(box(lon-.006,lat-.006,lon+.006,lat+.006)):
            index=int(index)
            if index not in self.cache:
                g=self.parts[index]
                if not g.is_valid:g=make_valid(g,method='structure',keep_collapsed=False)
                self.cache[index]=self.metric(g)
            g=self.cache[index]
            if g.intersects(region):patches.append(g.intersection(region))
        local=unary_union(patches).intersection(self.usable) if patches else GeometryCollection()
        distance=round(point.distance(local),1) if not local.is_empty else None
        in_analysis=self.coverage.covers(point);in_cloud=self.clouds.covers(point)
        valid=in_analysis and not in_cloud
        return {'status':classify_reference(in_analysis,in_cloud,not local.is_empty and local.covers(point),distance),
            'distance_m':distance if valid else None,'mapped_water_area_m2':round(local.area,1) if valid else None,
            'usable_coverage_percent':round(100*self.usable.intersection(region).area/region.area,2),
            'analysis_coverage_percent':round(100*self.coverage.intersection(region).area/region.area,2),
            'cloud_cover_percent':round(100*self.clouds.intersection(region).area/region.area,2)}


def attach_context(document,package_path,archive_path):
    # CLI preparation only: use the isolated GIS packages and matching PROJ data.
    dependencies=ROOT/'data/hotspots/gis_dependencies'
    sys.path.insert(0,str(dependencies))
    os.environ['PROJ_DATA']=str(dependencies/'rasterio/proj_data')
    os.environ['PROJ_LIB']=os.environ['PROJ_DATA']
    os.environ['GDAL_DATA']=str(dependencies/'rasterio/gdal_data')
    package_raw=Path(package_path).read_bytes();archive_raw=Path(archive_path).read_bytes()
    if hashlib.sha256(package_raw).hexdigest()!=PACKAGE_SHA256 or hashlib.sha256(archive_raw).hexdigest()!=ARCHIVE_SHA256:
        raise ValueError('Reviewed nearby-water source identity changed')
    with zipfile.ZipFile(io.BytesIO(package_raw)) as z:
        qa=json.loads(z.read(PREFIX+'QA_STRUCTURAL_CHECK.json'))
        for name,digest in qa['files'].items():
            if hashlib.sha256(z.read(PREFIX+name)).hexdigest()!=digest:raise ValueError('Nearby-water package member integrity failure')
        provenance=json.loads(z.read(PREFIX+'Spatial_Processing_Provenance.json'))
    scene=NativeScene(archive_raw,provenance)
    store=LocalEvidenceStore(ROOT/'data/hotspots/evidence');package_ref=store.put('raw',package_raw);archive_ref=store.put('raw',archive_raw)
    index=store.root/'index/nearby-water-import-v03.json'
    if index.exists():receipt=store.read_json(json.loads(index.read_bytes()),'captures')
    else:
        receipt={'kind':'user_supplied_historical_gis_evidence','imported_at_utc':datetime.now(timezone.utc).isoformat(),
            'package':package_ref,'native_archive':archive_ref,'source_url':provenance['source_archive_url'],
            'original_network_receipt_time':None,'meaning':'Local import time is not satellite acquisition, source publication or original network receipt.'}
        index.write_bytes(canonical_json(store.put_json('captures',receipt)))
    if receipt['package']!=package_ref or receipt['native_archive']!=archive_ref:raise ValueError('Historical context import receipt changed')
    shared={'information_type':'historical_nearby_water_reference','observation_date':'2024-05-01',
        'acquired_at_utc':'2024-05-01T08:06:00Z','source_product_url':provenance['source_product_url'],
        'source_event':'FL20240426KEN','search_radius_m':500,'processing_crs':'EPSG:32737',
        'source_archive_sha256':ARCHIVE_SHA256,'source_package_sha256':PACKAGE_SHA256,
        'field_validation':'Not yet field validated','confirmed_flood_free':None,
        'actual_incident_point':None,'verified_flood_boundary':None,'operational_use_allowed':False,
        'method':'Native satellite-water parts repaired as needed, projected to UTM37S, clipped to a 500 m reference search window and clear analysed footprint.',
        'limitations':'One historical scene. Nearby water does not confirm flooding at the reference point. Outside coverage, cloud and no mapped water cannot establish safety. Search windows can overlap and are not flood boundaries.'}
    counts=Counter()
    for site in document['sites']:
        position=site['geometry']['coordinates'] if site['geometry'] else None
        context={**shared,**scene.inspect(position),'reference_coordinates':position,
            'reference_kind':site['reference_kind'],'reference_scope':'current_monitoring_point'}
        site['nearby_water_reference']=context;counts[context['status']]+=1
    document['nearby_water_source']={'receipt':receipt,'source_provenance':provenance,
        'reference_scope':'Recomputed from authentic native shapes at current map coordinates; supplied lookup statistics were not copied across moved pins.',
        'counts':dict(counts),'independent_flood_events':1}
    return document
