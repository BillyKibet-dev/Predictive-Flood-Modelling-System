"""Offline inspection of cached GIS requests (never prints private configuration)."""
import json
import xml.etree.ElementTree as ET
from src.scripts.collect_hotspot_sources import STORE
from src.api.services.operational_source_storage import LocalEvidenceStore


def evidence():
    store = LocalEvidenceStore(STORE)
    return {r['identity']['label']: (store.read(r['raw'], 'raw'), r)
            for p in (STORE/'index').glob('*.json')
            for r in [store.read_json(json.loads(p.read_bytes()), 'captures')]
            if 'identity' in r and 'raw' in r}


if __name__ == '__main__':
    items = evidence()
    for label in ('cbd-osm-map', 'tmall-osm-map'):
        raw, receipt = items[label]
        doc = ET.fromstring(raw)
        nodes = {n.attrib['id']: (float(n.attrib['lon']), float(n.attrib['lat'])) for n in doc.findall('node')}
        ways = [(w, {t.attrib['k']:t.attrib['v'] for t in w.findall('tag')}) for w in doc.findall('way')]
        print(label)
        for w, tags in ways:
            if tags.get('junction') == 'roundabout' or tags.get('waterway'):
                coords = [nodes[n.attrib['ref']] for n in w.findall('nd')]
                print(w.attrib['id'], tags, [round(sum(p[i] for p in coords)/len(coords),7) for i in (0,1)])
        for w, tags in ways:
            if tags.get('name') != 'Kenyatta Avenue' or tags.get('highway') not in ('secondary','trunk'): continue
            ids = {n.attrib['ref'] for n in w.findall('nd')}
            for other, ot in ways:
                if ot.get('name') not in ('Moi Avenue','Uhuru Highway'):continue
                overlap = ids & {n.attrib['ref'] for n in other.findall('nd')}
                if overlap: print('JUNCTION',w.attrib['id'],other.attrib['id'],ot['name'],[(n,nodes[n]) for n in sorted(overlap)])
    item = json.loads(items['sentinel-search'][0])['features'][0]
    print('XML_ASSETS', {k:v for k,v in item['assets'].items() if 'xml' in v.get('type','') or 'metadata' in k})
