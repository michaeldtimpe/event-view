#!/usr/bin/env python3
"""Build the physical-geography layer (seas, lakes, mountain ranges, rivers).

    build_features.py SRC_DIR OUT_DIR

SRC_DIR holds these Natural Earth 1:50m files (public domain) from
github.com/nvkelso/natural-earth-vector (geojson/):
    ne_50m_geography_marine_polys.geojson   ne_50m_lakes.geojson
    ne_50m_geography_regions_polys.geojson  ne_50m_rivers_lake_centerlines.geojson
OUT_DIR must already hold land.bin and countries.json (build_map.py).

Writes:
    water.bin      W*H bytes, index into features.json "water" (seas, then lakes)
    relief.bin     W*H bytes, index into features.json "relief" (mountain ranges)
    features.json  {"water": [null, ...], "relief": [null, ...], "rivers": [...]}
and adds a center, an angular radius and a continent to every country and
city in countries.json, which the quiz uses to frame its questions.
"""
import json
import math
import sys
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw

W, H = 1440, 720
# Source name -> the name asked for. Reservoirs are in only when they are household names.
LAKES = {
    "Lake Superior": "Lake Superior", "Lake Victoria": "Lake Victoria", "Lake Huron": "Lake Huron",
    "Lake Michigan": "Lake Michigan", "Lake Volta": "Lake Volta", "Lake Tanganyika": "Lake Tanganyika",
    "Great Bear Lake": "Great Bear Lake", "Lake Malawi": "Lake Malawi", "Lake Baikal": "Lake Baikal",
    "Great Slave Lake": "Great Slave Lake", "Lake Winnipeg": "Lake Winnipeg", "Lake Erie": "Lake Erie",
    "Lake Balkhash": "Lake Balkhash", "Lake Ontario": "Lake Ontario", "Lake Ladoga": "Lake Ladoga",
    "Lake Onega": "Lake Onega", "Lago Titicaca": "Lake Titicaca", "Lake Nasser": "Lake Nasser",
    "Lake Eyre North": "Lake Eyre", "Lake Athabasca": "Lake Athabasca", "Lake Kariba": "Lake Kariba",
    "Lake Turkana": "Lake Turkana", "Lago de Nicaragua": "Lake Nicaragua", "Issyk-Kul": "Issyk-Kul",
    "Lake Albert": "Lake Albert", "Vänern": "Vänern", "South Aral Sea": "Aral Sea", "North Aral Sea": "Aral Sea",
    "Lake Urmia": "Lake Urmia", "Lake Van": "Lake Van", "Great Salt Lake": "Great Salt Lake",
    "Qinghai Hu": "Qinghai Lake", "Lake Tana": "Lake Tana", "Tonlé Sap": "Tonlé Sap", "Lake Kivu": "Lake Kivu",
    "Lake Peipus": "Lake Peipus", "Lake Edward": "Lake Edward", "Lac Moeru": "Lake Mweru",
    "Reindeer Lake": "Reindeer Lake", "Lake Chad": "Lake Chad", "Lake Khanka": "Lake Khanka",
    "Poyang Hu": "Poyang Lake", "Dead Sea": "Dead Sea", "Lake Maracaibo": "Lake Maracaibo",
    "Lake Geneva": "Lake Geneva", "Lake Tahoe": "Lake Tahoe", "Lake Okeechobee": "Lake Okeechobee",
}

# Rank-4 seas and straits worth knowing, on top of everything ranked 0-3.
SEAS_EXTRA = {"Aegean Sea", "Ionian Sea", "Strait of Malacca", "Taiwan Strait", "Strait of Gibraltar",
              "Gulf of Finland", "Korea Strait", "Gulf of Tonkin", "Gulf of Saint Lawrence", "Solomon Sea",
              "Bismarck Sea", "Río de la Plata", "Makassar Strait", "Bohai Sea", "Florida Strait",
              "Molucca Sea", "Chesapeake Bay", "Bay of Fundy"}
# Named waters the source set lacks, as (name, west, east, south, north) boxes.
# Only the water cells inside each box are taken.
SEAS_BY_HAND = [("Strait of Hormuz", 55.7, 57.3, 25.9, 27.2), ("Bab-el-Mandeb", 43.0, 43.8, 12.2, 13.1)]
RANGES_DROP = {"Pensacola Mountains", "Ellsworth Mountains", "Queen Maud Mountains", "Crystal Mountain",
               "Central Highlands", "Appennino Ligure", "Siwalik Hills", "Cordillera Occidental",
               "Cordillera Oriental", "Cordillera Real", "Cordillera Blanca"}
RANGES_EXTRA = {"Dinaric Alps", "Balkan Mountains", "Pontic Mountains", "Guiana Highlands",
                "New Guinea Highlands", "Cantabrian Mountains", "Chersky Range", "Arakan Mountains"}
RANGES_RENAME = {"Ahag": "Ahaggar Mountains", "Pamir mountains": "Pamir Mountains",
                 "Southern Alps/Kā Tiritiri o te Moana": "Southern Alps"}
# Source name -> the name asked for. Several source segments fold into one river.
RIVERS = {
    "Amazonas": "Amazon", "Amazon": "Amazon", "Nile": "Nile", "White Nile": "Nile", "Albert Nile": "Nile",
    "Mountain Nile": "Nile", "Victoria Nile": "Nile", "Blue Nile": "Blue Nile", "Abay": "Blue Nile",
    "El Bahr el Azraq": "Blue Nile", "Mississippi": "Mississippi", "Missouri": "Missouri", "Ohio": "Ohio",
    "Yangtze": "Yangtze", "Chang": "Yangtze", "Tongtian": "Yangtze", "Tuotuo": "Yangtze",
    "Yellow": "Yellow River", "Huang": "Yellow River", "Lena": "Lena", "Ob": "Ob", "Irtysh": "Irtysh",
    "Ertis": "Irtysh", "Yenisey": "Yenisei", "Angara": "Angara", "Amur": "Amur", "Volga": "Volga",
    "Danube": "Danube", "Donau": "Danube", "Rhine": "Rhine", "Rhein": "Rhine", "Dnieper": "Dnieper",
    "Dnipro": "Dnieper", "Dnepre": "Dnieper", "Don": "Don", "Ural": "Ural", "Congo": "Congo",
    "Lualaba": "Congo", "Niger": "Niger", "Zambezi": "Zambezi", "Orange": "Orange", "Kasai": "Kasai",
    "Ubangi": "Ubangi", "Senegal": "Senegal", "Sénégal": "Senegal", "Limpopo": "Limpopo", "Mekong": "Mekong",
    "Brahmaputra": "Brahmaputra", "Dihang": "Brahmaputra", "Ganges": "Ganges", "Indus": "Indus",
    "Irrawaddy": "Irrawaddy", "Ayeyarwady": "Irrawaddy", "Salween": "Salween", "Nu": "Salween",
    "Euphrates": "Euphrates", "Al Furat": "Euphrates", "Firat": "Euphrates", "Tigris": "Tigris",
    "Dicle": "Tigris", "Mackenzie": "Mackenzie", "Yukon": "Yukon", "Columbia": "Columbia",
    "Colorado": "Colorado", "Rio Grande": "Rio Grande", "St. Lawrence": "St. Lawrence",
    "Arkansas": "Arkansas", "Snake": "Snake", "Paraná": "Paraná", "Orinoco": "Orinoco", "Madeira": "Madeira",
    "São  Francisco": "São Francisco", "Tocantins": "Tocantins", "Magdalena": "Magdalena",
    "Murray": "Murray", "Darling": "Darling", "Kolyma": "Kolyma", "Pechora": "Pechora", "Oder": "Oder",
    "Seine": "Seine", "Syr Darya": "Syr Darya", "Amu Darya": "Amu Darya", "Godavari": "Godavari",
    "Krishna": "Krishna", "Vistula": "Vistula", "Elbe": "Elbe", "Loire": "Loire", "Tagus": "Tagus",
    "Po": "Po", "Ebro": "Ebro", "Uruguay": "Uruguay", "Paraguay": "Paraguay", "Okavango": "Okavango",
    "Jordan": "Jordan", "Xi": "Pearl River (Xi)", "Helmand": "Helmand", "Saskatchewan": "Saskatchewan",
}

LAT = np.radians(90 - (np.arange(H) + 0.5) * 180 / H)[:, None] * np.ones((1, W))
LON = np.radians(-180 + (np.arange(W) + 0.5) * 360 / W)[None, :] * np.ones((H, 1))
VX, VY, VZ = np.cos(LAT) * np.sin(LON), np.sin(LAT), np.cos(LAT) * np.cos(LON)
AREA = np.cos(LAT)


def load(src, name):
    return json.load(open(f"{src}/{name}.geojson"))["features"]


def mask_of(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    img = Image.new("1", (W, H), 0)
    d = ImageDraw.Draw(img)
    for poly in polys:
        for i, ring in enumerate(poly):
            d.polygon([((x + 180) / 360 * W, (90 - y) / 180 * H) for x, y in ring], fill=0 if i else 1)
    return np.array(img, dtype=bool)


def frame(vx, vy, vz, w=None):
    """Center (lat, lon) and angular radius in degrees of a set of unit vectors."""
    w = np.ones_like(vx) if w is None else w
    c = np.array([(vx * w).sum(), (vy * w).sum(), (vz * w).sum()])
    c /= np.linalg.norm(c) or 1
    dots = np.clip(vx * c[0] + vy * c[1] + vz * c[2], -1, 1)
    return (round(math.degrees(math.asin(c[1])), 2), round(math.degrees(math.atan2(c[0], c[2])), 2),
            round(math.degrees(math.acos(dots.min())), 1))


def continent(land, countries, lat, lon, under=None):
    c = _continent(land, countries, lat, lon, under)
    # Natural Earth files all of Russia under Europe; east of the Urals is Asia.
    return "Asia" if c == "Europe" and not -30 <= lon <= 60 else c


def _continent(land, countries, lat, lon, under=None):
    if under is not None:
        ids = land[under]
        ids = ids[ids > 0]
        if ids.size:
            return countries[Counter(ids.tolist()).most_common(1)[0][0]]["cont"]
    r0, c0 = int((90 - lat) / 180 * H), int((lon + 180) / 360 * W)
    for rad in (1, 3, 6, 12, 24, 48, 96):
        ids = land[max(0, r0 - rad):r0 + rad + 1, max(0, c0 - rad):c0 + rad + 1]
        ids = ids[ids > 0]
        if ids.size:
            return countries[Counter(ids.tolist()).most_common(1)[0][0]]["cont"]
    return "World"


def main(src, out):
    land = np.fromfile(f"{out}/land.bin", dtype=np.uint8).reshape(H, W)
    meta = json.load(open(f"{out}/countries.json"))
    countries = meta["countries"]

    for i in range(1, len(countries)):
        m = land == i
        if m.any():
            countries[i]["lat"], countries[i]["lon"], countries[i]["rad"] = frame(VX[m], VY[m], VZ[m], AREA[m])
        else:
            countries[i]["lat"], countries[i]["lon"], countries[i]["rad"] = countries[i]["label"][1], countries[i]["label"][0], 1.0
    by_a3 = {c["a3"]: c for c in countries[1:]}
    for city in meta["cities"]:
        city["cont"] = by_a3[city["a3"]]["cont"] if city["a3"] in by_a3 else _continent(land, countries, city["lat"], city["lon"])

    # --- seas (drawn big to small so a strait sits on top of its ocean), then lakes ---
    water = np.zeros((H, W), dtype=np.uint8)
    water_meta = [None]
    seas = []
    for f in load(src, "ne_50m_geography_marine_polys"):
        p = f["properties"]
        name = p["name"].title().replace(" Of ", " of ") if p["featurecla"] == "ocean" else p["name_en"] or p["name"]
        if p["featurecla"] in ("river", "reef") or not name:
            continue
        if p["scalerank"] <= 3 or name in SEAS_EXTRA:
            seas.append((p["scalerank"], name, p["featurecla"], mask_of(f["geometry"])))
    seas.sort(key=lambda s: (s[0], -s[3].sum()))
    for rank, name, kind, m in seas:
        water[m] = len(water_meta)
        water_meta.append({"name": name, "kind": "ocean" if kind == "ocean" else "sea"})
    for name, west, east, south, north in SEAS_BY_HAND:
        lat, lon = np.degrees(LAT), np.degrees(LON)
        m = (lon >= west) & (lon <= east) & (lat >= south) & (lat <= north) & (land == 0)
        water[m] = len(water_meta)
        water_meta.append({"name": name, "kind": "sea"})
    lakes = {}
    for f in load(src, "ne_50m_lakes"):
        name = LAKES.get(f["properties"]["name"])
        if name:
            m = mask_of(f["geometry"])
            lakes[name] = lakes[name] | m if name in lakes else m
    for name, m in sorted(lakes.items(), key=lambda kv: -kv[1].sum()):
        water[m] = len(water_meta)
        water_meta.append({"name": name, "kind": "lake"})
    for i in range(1, len(water_meta)):
        m = water == i
        w = water_meta[i]
        if not m.any():
            w["gone"] = True
            continue
        w["lat"], w["lon"], w["rad"] = frame(VX[m], VY[m], VZ[m], AREA[m])
        w["cont"] = "World" if w["kind"] == "ocean" else continent(land, countries, w["lat"], w["lon"], m if w["kind"] == "lake" else None)

    # --- mountain ranges ---
    relief = np.zeros((H, W), dtype=np.uint8)
    relief_meta = [None]
    ranges = {}
    for f in load(src, "ne_50m_geography_regions_polys"):
        p = f["properties"]
        if p["FEATURECLA"] != "Range/mtn":
            continue
        name = p["NAME_EN"] or p["NAME"]
        if name in RANGES_DROP or not (p["SCALERANK"] <= 3 or name in RANGES_EXTRA):
            continue
        name = RANGES_RENAME.get(name, name)
        m = mask_of(f["geometry"])
        ranges[name] = ranges[name] | m if name in ranges else m
    for name, m in sorted(ranges.items(), key=lambda kv: -kv[1].sum()):
        relief[m] = len(relief_meta)
        relief_meta.append({"name": name, "kind": "range"})
    for i in range(1, len(relief_meta)):
        m = relief == i
        r = relief_meta[i]
        if m.sum() < 3:
            r["gone"] = True
            continue
        r["lat"], r["lon"], r["rad"] = frame(VX[m], VY[m], VZ[m], AREA[m])
        r["cont"] = continent(land, countries, r["lat"], r["lon"], m)

    # --- rivers ---
    rivers = {}
    for f in load(src, "ne_50m_rivers_lake_centerlines"):
        p = f["properties"]
        name = RIVERS.get(p.get("name_en")) or RIVERS.get(p.get("name"))
        if not name:
            continue
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        if name == "Colorado" and lines[0][0][1] < 25:      # the Argentine Colorado is a different river
            continue
        for line in lines:
            pts = [line[0]]
            for x, y in line[1:]:
                if abs(x - pts[-1][0]) + abs(y - pts[-1][1]) >= 0.12:
                    pts.append((x, y))
            if pts[-1] != tuple(line[-1]):
                pts.append(line[-1])
            rivers.setdefault(name, []).append([round(v, 2) for x, y in pts for v in (x, y)])
    river_meta = []
    for name, lines in sorted(rivers.items()):
        lon = np.radians(np.array([v for l in lines for v in l[0::2]]))
        lat = np.radians(np.array([v for l in lines for v in l[1::2]]))
        la, lo, rad = frame(np.cos(lat) * np.sin(lon), np.sin(lat), np.cos(lat) * np.cos(lon))
        river_meta.append({"name": name, "kind": "river", "lat": la, "lon": lo, "rad": rad,
                           "cont": continent(land, countries, la, lo), "lines": lines})

    water.tofile(f"{out}/water.bin")
    relief.tofile(f"{out}/relief.bin")
    dump = dict(ensure_ascii=False, separators=(",", ":"))
    json.dump({"water": water_meta, "relief": relief_meta, "rivers": river_meta}, open(f"{out}/features.json", "w"), **dump)
    json.dump(meta, open(f"{out}/countries.json", "w"), **dump)

    live = lambda xs, k: [x["name"] for x in xs[1:] if not x.get("gone") and x["kind"] == k]
    print("seas", len(live(water_meta, "sea")) + len(live(water_meta, "ocean")), "lakes", len(live(water_meta, "lake")),
          "ranges", len(live(relief_meta, "range")), "rivers", len(river_meta))
    print("LAKES:", ", ".join(live(water_meta, "lake")))
    print("RIVERS:", ", ".join(r["name"] for r in river_meta))
    print("rivers wanted but absent:", sorted(set(RIVERS.values()) - set(rivers)))
    print("lakes wanted but absent:", sorted(set(LAKES.values()) - set(lakes)))
    print("dropped (no cells):", [x["name"] for x in water_meta[1:] + relief_meta[1:] if x.get("gone")])
    print("continents:", Counter(x["cont"] for x in water_meta[1:] + relief_meta[1:] + river_meta if not x.get("gone")))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
