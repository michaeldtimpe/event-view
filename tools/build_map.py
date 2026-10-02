#!/usr/bin/env python3
"""Build the globe's map data from Natural Earth (public domain).

    build_map.py COUNTRIES.geojson PLACES.geojson OUT_DIR

Inputs are ne_110m_admin_0_countries.geojson and
ne_110m_populated_places_simple.geojson from
github.com/nvkelso/natural-earth-vector (geojson/).

Writes:
    land.bin        W*H bytes, row 0 = 90N, col 0 = 180W; 0 is ocean,
                    otherwise an index into countries.json
    countries.json  {"w", "h", "countries": [null, {...}, ...], "cities": [...]}

Only needs re-running if the map itself should change; events live in
events.json and never touch this.
"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

W, H = 1440, 720  # quarter-degree cells


def rings(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        yield poly[0], poly[1:]


def px(ring):
    return [((lon + 180) / 360 * W, (90 - lat) / 180 * H) for lon, lat in ring]


def main(countries_path, places_path, out_dir):
    feats = json.load(open(countries_path))["features"]
    feats.sort(key=lambda f: f["properties"]["NAME"])
    grid = np.zeros((H, W), dtype=np.uint8)
    countries = [None]
    for i, f in enumerate(feats, start=1):
        p = f["properties"]
        # Each country gets its own mask so a hole (Lesotho inside South
        # Africa) never erases a neighbor that was drawn earlier.
        mask = Image.new("1", (W, H), 0)
        d = ImageDraw.Draw(mask)
        for outer, holes in rings(f["geometry"]):
            d.polygon(px(outer), fill=1)
            for h in holes:
                d.polygon(px(h), fill=0)
        grid[np.array(mask, dtype=bool)] = i
        countries.append({
            "name": p["NAME"],
            "long": p["NAME_LONG"],
            "a3": p["ADM0_A3"],
            "iso": p["ISO_A3_EH"],
            "cont": p["CONTINENT"],
            "sub": p["SUBREGION"],
            "pop": int(p["POP_EST"] or 0),
            "label": [round(p["LABEL_X"], 2), round(p["LABEL_Y"], 2)],
        })

    # Greedy coloring so no two neighbors share a land texture.
    adj = {i: set() for i in range(1, len(countries))}
    for a, b in ((grid[:, :-1], grid[:, 1:]), (grid[:-1, :], grid[1:, :])):
        m = (a != b) & (a > 0) & (b > 0)
        for x, y in set(zip(a[m].tolist(), b[m].tolist())):
            adj[x].add(y)
            adj[y].add(x)
    shade = {}
    for i in sorted(adj, key=lambda k: -len(adj[k])):
        used = {shade[n] for n in adj[i] if n in shade}
        shade[i] = next(s for s in range(8) if s not in used)
    for i in range(1, len(countries)):
        countries[i]["shade"] = shade[i]

    by_a3 = {c["a3"]: c for c in countries[1:]}
    cities = []
    for f in json.load(open(places_path))["features"]:
        p = f["properties"]
        cap = bool(p["adm0cap"])
        cities.append({
            "name": p["name"],
            "a3": p["adm0_a3"],
            "country": p["adm0name"],
            "cap": cap,
            "lat": round(p["latitude"], 2),
            "lon": round(p["longitude"], 2),
            "pop": int(p["pop_max"] or 0),
        })
        if cap and p["adm0_a3"] in by_a3 and "capital" not in by_a3[p["adm0_a3"]]:
            by_a3[p["adm0_a3"]]["capital"] = p["name"]

    grid.tofile(f"{out_dir}/land.bin")
    json.dump({"w": W, "h": H, "countries": countries, "cities": cities},
              open(f"{out_dir}/countries.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"{len(countries) - 1} countries, {len(cities)} cities, "
          f"{max(shade.values()) + 1} textures, land {100 * (grid > 0).mean():.1f}%")


if __name__ == "__main__":
    main(*sys.argv[1:4])
