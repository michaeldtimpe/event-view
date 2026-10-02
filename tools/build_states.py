#!/usr/bin/env python3
"""Build the US states and Canadian provinces layer.

    build_states.py SRC_DIR OUT_DIR

SRC_DIR holds ne_50m_admin_1_states_provinces.geojson and
ne_10m_populated_places_simple.geojson (Natural Earth, public domain).
OUT_DIR must already hold land.bin and countries.json.

Writes:
    states.bin   W*H bytes, index into states.json "states"; only set on
                 cells the country raster gives to the parent country
    states.json  {"states": [null, {...}, ...], "capitals": [...]}
"""
import json
import sys

import numpy as np

from build_features import AREA, H, VX, VY, VZ, W, frame, load, mask_of


def main(src, out):
    land = np.fromfile(f"{out}/land.bin", dtype=np.uint8).reshape(H, W)
    countries = json.load(open(f"{out}/countries.json"))["countries"]
    index = {c["a3"]: i for i, c in enumerate(countries) if c}
    wanted = {"USA": ("State",), "CAN": ("Province", "Territory")}      # leaves out the District of Columbia

    feats = [f for f in load(src, "ne_50m_admin_1_states_provinces")
             if f["properties"]["type_en"] in wanted.get(f["properties"]["adm0_a3"], ())]
    feats.sort(key=lambda f: (f["properties"]["adm0_a3"] != "USA", f["properties"]["name"]))
    grid = np.zeros((H, W), dtype=np.uint8)
    states = [None]
    for i, f in enumerate(feats, start=1):
        p = f["properties"]
        m = mask_of(f["geometry"]) & (land == index[p["adm0_a3"]])
        grid[m] = i
        states.append({"name": p["name"], "postal": p["postal"], "parent": p["adm0_a3"], "kind": p["type_en"].lower(),
                       "sub": ", ".join(x for x in (p["region_sub"], p["region"]) if x),
                       "label": [round(p["longitude"], 2), round(p["latitude"], 2)]})
    # The two rasters come from different scales, so the coasts disagree by a
    # cell here and there. Hand each leftover cell to the neighbor beside it
    # that belongs to the same country.
    parent_of = np.array([0] + [index[s["parent"]] for s in states[1:]], dtype=np.uint8)
    home = np.isin(land, [index[a3] for a3 in wanted])
    for _ in range(40):
        todo = home & (grid == 0)
        if not todo.any():
            break
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            near = np.roll(grid, (dy, dx), axis=(0, 1))
            take = todo & (near > 0) & (grid == 0) & (parent_of[near] == land)
            grid[take] = near[take]

    adj = {i: set() for i in range(1, len(states))}
    for a, b in ((grid[:, :-1], grid[:, 1:]), (grid[:-1, :], grid[1:, :])):
        m = (a != b) & (a > 0) & (b > 0)
        for x, y in set(zip(a[m].tolist(), b[m].tolist())):
            adj[x].add(y)
            adj[y].add(x)
    shade = {}
    for i in sorted(adj, key=lambda k: -len(adj[k])):
        shade[i] = next(s for s in range(8) if s not in {shade[n] for n in adj[i] if n in shade})

    caps = {}
    for f in load(src, "ne_10m_populated_places_simple"):
        p = f["properties"]
        if p["adm0_a3"] in wanted and p["featurecla"] == "Admin-1 capital":
            name = " ".join(p["name"].split())
            caps[p["adm1name"]] = {"name": "Quebec City" if name == "Québec" else name, "country": p["adm1name"],
                                   "parent": p["adm0_a3"], "lat": round(p["latitude"], 2), "lon": round(p["longitude"], 2)}
    for i in range(1, len(states)):
        s, m = states[i], grid == i
        s["shade"] = shade[i]
        s["cells"] = int(m.sum())
        if m.any():
            s["lat"], s["lon"], s["rad"] = frame(VX[m], VY[m], VZ[m], AREA[m])
        else:                                   # too small for the raster: still askable as a point
            s["lat"], s["lon"], s["rad"] = s["label"][1], s["label"][0], 1.5
        s["capital"] = caps[s["name"]]["name"]

    grid.tofile(f"{out}/states.bin")
    json.dump({"states": states, "capitals": [caps[s["name"]] for s in states[1:]]},
              open(f"{out}/states.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(len(states) - 1, "states and provinces,", len(caps), "capitals,", max(shade.values()) + 1, "textures")
    print("no cells:", [s["name"] for s in states[1:] if not s["cells"]])
    print("smallest:", sorted((s["cells"], s["name"]) for s in states[1:])[:8])
    print("cells without a state or province:", int((home & (grid == 0)).sum()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
