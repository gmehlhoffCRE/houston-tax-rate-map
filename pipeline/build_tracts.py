"""
Census tract layer for the map's population growth and labor heat maps.

  python build_tracts.py --census raw/census --out out
      -> out/web/data/layers/tracts.json

For every 2020 census tract in the 8 counties:
  p10        2010 census population, re-tabulated to the 2020 tract (Census 2010-2020 tract relationship file):
             a split 2010 tract's people go to its pieces in proportion to 2020 population on each piece
  p20        2020 census population (P.L. 94-171 redistricting file, POP100)
  p23        ACS 2019-2023 5-year estimate (B01003)
  emp        employed residents 16+ (ACS 2019-2023, C24010), then residents employed in each job group:
    mgmt     management, business and financial
    tech     computer, engineering and science
    health   healthcare practitioners, technicians and support
    office   office and administrative support
    sales    sales and related
    service  food, cleaning, personal care and protective services
    constr   construction and extraction
    maint    installation, maintenance and repair
    prod     production
    trans    transportation (drivers and other transportation jobs)
    matl     material moving (warehouse, freight and stock handlers)
  co_g       county population growth 2020-2024, percent (Census population estimates, vintage 2024)

Inputs (www2.census.gov, all in --census):
  tx2010.pl.zip, tx2020.pl.zip                        /census_2010/01-Redistricting_File--PL_94-171/Texas/,
                                                      /programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Texas/
  tl_2020_48_tract20.zip                              /geo/tiger/TIGER2020PL/LAYER/TRACT/2020/
  tab20_tract20_tract10_st48.txt                      /geo/docs/maps-data/data/rel2020/tract/
  acsdt5y2023-b01003.dat, acsdt5y2023-c24010.dat      /programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/
  co-est2024-alldata.csv                              /programs-surveys/popest/datasets/2020-2024/counties/totals/
"""
import argparse, csv, io, json, os, zipfile
from collections import defaultdict
import geopandas as gpd

COUNTIES = {"201": "Harris", "157": "Fort Bend", "339": "Montgomery", "473": "Waller", "071": "Chambers",
            "039": "Brazoria", "291": "Liberty", "167": "Galveston"}
# C24010 line numbers for men; women are the same line + 36
JOBS = {"mgmt": [4], "tech": [7], "health": [16, 20], "office": [29], "sales": [28], "service": [19, -20],
        "constr": [32], "maint": [33], "prod": [35], "trans": [36], "matl": [37]}


def keep(geoid):
    return geoid[:2] == "48" and geoid[2:5] in COUNTIES


def pl2010(path):
    """2010 PL geo header (fixed width): tract summary level 140, POP100 at columns 319-327."""
    out = {}
    with zipfile.ZipFile(path) as z, z.open("txgeo2010.pl") as f:
        for ln in io.TextIOWrapper(f, encoding="latin-1"):
            if ln[8:11] == "140":
                g = ln[27:29] + ln[29:32] + ln[54:60]
                if keep(g):
                    out[g] = int(ln[318:327])
    return out


def pl2020(path):
    """2020 PL geo header (pipe-delimited): SUMLEV is field 3, GEOID field 9, POP100 the 7th field from the end."""
    out = {}
    with zipfile.ZipFile(path) as z, z.open("txgeo2020.pl") as f:
        for ln in io.TextIOWrapper(f, encoding="latin-1"):
            r = ln.rstrip("\n").split("|")
            if r[2] == "140":
                g = r[8][-11:]
                if keep(g):
                    out[g] = int(r[-7])
    return out


def sf(path):
    with open(path, encoding="utf-8") as f:
        head = f.readline().rstrip("\n").split("|")
        for ln in f:
            if ln.startswith("1400000US48"):
                r = dict(zip(head, ln.rstrip("\n").split("|")))
                if keep(r["GEO_ID"][-11:]):
                    yield r["GEO_ID"][-11:], r


def num(v):
    try:
        x = float(v)
        return 0 if x < 0 else x
    except (TypeError, ValueError):
        return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default="raw/census")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    c = lambda n: os.path.join(a.census, n)

    p10_old, p20 = pl2010(c("tx2010.pl.zip")), pl2020(c("tx2020.pl.zip"))
    print(f"2010 census: {len(p10_old):,} tracts, {sum(p10_old.values()):,} people; "
          f"2020: {len(p20):,} tracts, {sum(p20.values()):,}")
    # 2010 people into 2020 tracts by land-area share of each 2010 tract
    # weight each piece of a 2010 tract by the 2020 population living on it (2020 tract population x its land share),
    # so a split tract's 2010 people follow where homes are, not empty land; land area alone if nobody lived there
    parts, land20 = [], {}
    with open(c("tab20_tract20_tract10_st48.txt"), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter="|"):
            t10, t20, part = r["GEOID_TRACT_10"], r["GEOID_TRACT_20"], float(r["AREALAND_PART"] or 0)
            land20[t20] = float(r["AREALAND_TRACT_20"] or 0)
            if t10 in p10_old:
                parts.append((t10, t20, part))
    wsum, asum = defaultdict(float), defaultdict(float)
    for t10, t20, part in parts:
        wsum[t10] += p20.get(t20, 0) * part / (land20[t20] or 1); asum[t10] += part
    p10 = defaultdict(float)
    for t10, t20, part in parts:
        if wsum[t10] > 0:
            p10[t20] += p10_old[t10] * (p20.get(t20, 0) * part / (land20[t20] or 1)) / wsum[t10]
        elif asum[t10] > 0:
            p10[t20] += p10_old[t10] * part / asum[t10]
    print(f"2010 people re-tabulated to 2020 tracts: {sum(p10.values()):,.0f}")

    p23 = {g: int(num(r["B01003_E001"])) for g, r in sf(c("acsdt5y2023-b01003.dat"))}
    jobs = {}
    for g, r in sf(c("acsdt5y2023-c24010.dat")):
        e = lambda i: num(r.get("C24010_E%03d" % i))
        d = {"emp": int(e(1))}
        for k, lines in JOBS.items():
            d[k] = int(round(sum((1 if i > 0 else -1) * (e(abs(i)) + e(abs(i) + 36)) for i in lines)))
        jobs[g] = d
    co = {}
    with open(c("co-est2024-alldata.csv"), encoding="latin-1") as f:
        for r in csv.DictReader(f):
            if r["STATE"] == "48" and r["COUNTY"] in COUNTIES:
                b, e24 = float(r["ESTIMATESBASE2020"]), float(r["POPESTIMATE2024"])
                co[r["COUNTY"]] = round(100 * (e24 - b) / b, 1)
    print("county growth 2020-2024 (%):", {COUNTIES[k]: v for k, v in co.items()})

    g = gpd.read_file("zip://" + c("tl_2020_48_tract20.zip"))
    g = g[g.COUNTYFP20.isin(COUNTIES)].copy()
    g = g[g.ALAND20.astype(float) > 0]   # skip all-water tracts
    m = g.to_crs(2278); m["geometry"] = m.geometry.simplify(25 * 3.2808, preserve_topology=True); g = m.to_crs(4326)
    feats = []
    for r in g.itertuples():
        t = r.GEOID20
        props = {"t": t, "p10": int(round(p10.get(t, 0))), "p20": p20.get(t, 0), "p23": p23.get(t, 0),
                 "co_g": co.get(t[2:5]), "sqmi": round(float(r.ALAND20) / 2589988.11, 2), **jobs.get(t, {"emp": 0})}
        geo = json.loads(gpd.GeoSeries([r.geometry]).to_json())["features"][0]["geometry"]
        def rnd(x):
            return [rnd(v) for v in x] if isinstance(x, list) and x and isinstance(x[0], list) else [round(x[0], 5), round(x[1], 5)]
        geo["coordinates"] = rnd(geo["coordinates"])
        feats.append({"type": "Feature", "properties": props, "geometry": geo})
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    out = os.path.join(od, "tracts.json")
    json.dump({"type": "FeatureCollection", "features": feats,
               "meta": {"census": [2010, 2020], "acs": "2019-2023", "popest": 2024}}, open(out, "w"), separators=(",", ":"))
    print(f"{len(feats):,} tracts -> {out} ({os.path.getsize(out) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
