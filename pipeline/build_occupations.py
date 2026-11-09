"""
Detailed occupations where people live, for the drive-time labor panel and the occupation map layer.

Source: ACS 5-year PUMS person file for Texas (psam_p48.csv, e.g. the 2020-2024 file from
www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_ptx.zip) and 2020 PUMA shapes (TIGER tl_<year>_48_puma20).
PUMAs (about 100,000 people each) are the finest geography with detailed occupation codes (SOCP).

For each PUMA touching the 8 counties: civilian employed residents (ESR 1 or 2, weighted by PWGTP) by occupation group
(data/labor/occupations.csv: SOC code prefixes, first match wins in file order, so the catch-all "51" comes last),
and median annual wages of full-time workers (WKHP >= 30, WAGP > 0, ADJINC to the survey's last year's dollars).
A PUMA median is used when it rests on at least MIN_N sample records, otherwise the 8-county median.

The page apportions PUMA counts to the drive-time bands through the census tract points of labor.json:
tract employed residents x the PUMA's occupation shares. Writes, in the layers folder:
  occupations.json   {"occ": [...], "puma": {code: {...}}, "tract_puma": {tract: code}, "region": {...}, "meta": {...}}
  pumas.json         PUMA polygons (simplified) for the occupation map layer

  python build_occupations.py --pums psam_p48.csv --puma tl_2023_48_puma20.shp --layers layers_out/web/data/layers
"""
import argparse, csv, json, os
import geopandas as gpd, numpy as np, pandas as pd

MIN_N = 30
here = os.path.dirname(os.path.abspath(__file__))


def wmedian(v, w):
    if len(v) == 0:
        return None
    o = np.argsort(v); v, w = v[o], w[o]; c = np.cumsum(w)
    return float(v[np.searchsorted(c, c[-1] / 2)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pums", required=True)
    ap.add_argument("--puma", required=True)
    ap.add_argument("--layers", required=True)
    ap.add_argument("--occupations", default=os.path.join(here, "..", "data", "labor", "occupations.csv"))
    ap.add_argument("--years", default="2020-2024")
    ap.add_argument("--oews", default=os.path.join(here, "..", "data", "labor", "oews_houston.csv"),
                    help="optional BLS OEWS wages for the Houston metro: columns soc (e.g. 53-7051), h10, h50, h90 (hourly); "
                         "from the 'May <year> metropolitan and nonmetropolitan area' file at bls.gov/oes (area 26420)")
    a = ap.parse_args()

    occ = list(csv.DictReader(open(a.occupations, encoding="utf-8")))
    for o in occ:
        o["prefixes"] = [s.strip().replace("X", "") for s in o["soc"].split(";") if s.strip()]

    lab = json.load(open(os.path.join(a.layers, "labor.json")))
    tr = gpd.GeoDataFrame([f["properties"] for f in lab["features"]],
                          geometry=gpd.points_from_xy([f["geometry"]["coordinates"][0] for f in lab["features"]],
                                                      [f["geometry"]["coordinates"][1] for f in lab["features"]]), crs=4326)
    pu = gpd.read_file(a.puma).to_crs(4326)
    j = gpd.sjoin(tr, pu[["PUMACE20", "NAMELSAD20", "geometry"]], how="left", predicate="within")
    tract_puma = {t: p for t, p in zip(j.tract, j.PUMACE20) if isinstance(p, str)}
    codes = sorted(set(tract_puma.values()))
    print(f"{len(tract_puma):,} tracts in {len(codes)} PUMAs")

    cols = ["PUMA", "PWGTP", "ESR", "SOCP", "WAGP", "WKHP", "ADJINC"]
    p = pd.read_csv(a.pums, usecols=cols, dtype={"PUMA": str, "SOCP": str})
    p["PUMA"] = p.PUMA.str.zfill(5)
    p = p[p.PUMA.isin(codes) & p.ESR.isin([1, 2])].copy()
    p["SOCP"] = p.SOCP.fillna("").str.strip()
    p["k"] = ""
    for o in occ:   # first match wins
        m = (p.k == "") & p.SOCP.apply(lambda s, pre=o["prefixes"]: any(s.startswith(x) for x in pre))
        p.loc[m, "k"] = o["key"]
    p["wage"] = p.WAGP * p.ADJINC / 1e6
    ft = (p.WKHP >= 30) & (p.WAGP > 0)
    print(f"{len(p):,} employed person records; {(p.k != '').sum():,} in the occupation groups")

    region = {"wage": [], "n": []}
    for o in occ:
        m = (p.k == o["key"]) & ft
        region["wage"].append(round(wmedian(p.wage[m].to_numpy(), p.PWGTP[m].to_numpy()) or 0))
        region["n"].append(int((p.k == o["key"]).sum()))
    out_p = {}
    names = dict(zip(pu.PUMACE20, pu.NAMELSAD20))
    for code, g in p.groupby("PUMA"):
        emp = float(g.PWGTP.sum())
        cnt, wage = [], []
        for i, o in enumerate(occ):
            m = g.k == o["key"]
            cnt.append(int(round(g.PWGTP[m].sum())))
            mf = m & ft.loc[g.index]
            w = wmedian(g.wage[mf].to_numpy(), g.PWGTP[mf].to_numpy()) if mf.sum() >= MIN_N else None
            wage.append(round(w) if w else None)
        out_p[code] = {"name": names.get(code, "").replace(" PUMA", ""), "emp": int(round(emp)), "c": cnt, "w": wage}
    bls = {}
    if os.path.exists(a.oews):   # each group gets the wages of its first 6-digit SOC code
        for r in csv.DictReader(open(a.oews, encoding="utf-8-sig")):
            bls[r["soc"].replace("-", "").strip()] = [float(r[c]) if r.get(c) not in (None, "", "*", "#") else None for c in ("h10", "h50", "h90")]
        print(f"BLS OEWS wages for {len(bls)} occupations")
    for o in occ:
        six = next((x for x in o["prefixes"] if len(x) == 6 and x in bls), None)
        o["bls"] = bls.get(six) if six else None
    doc = {"occ": [{k: o[k] for k in ("key", "label", "short", "group", "bls") if o.get(k) is not None} for o in occ], "puma": out_p, "tract_puma": tract_puma,
           "region": region, "meta": {"source": f"ACS {a.years} 5-year PUMS", "years": a.years, "min_n": MIN_N}}
    json.dump(doc, open(os.path.join(a.layers, "occupations.json"), "w"), separators=(",", ":"), allow_nan=False)
    shp = pu[pu.PUMACE20.isin(codes)].copy()
    shp["geometry"] = shp.to_crs(2278).geometry.simplify(150).to_crs(4326)
    shp = shp.rename(columns={"PUMACE20": "puma"})[["puma", "geometry"]]
    shp["geometry"] = shp.geometry.set_precision(1e-5)
    json.dump(json.loads(shp.to_json(drop_id=True)), open(os.path.join(a.layers, "pumas.json"), "w"), separators=(",", ":"))
    for o, w in zip(occ, region["wage"]):
        tot = sum(v["c"][occ.index(o)] for v in out_p.values())
        print(f"  {o['label'][:50]:50} {tot:>9,} residents  median ${w:,}")
    print(f"wrote occupations.json ({os.path.getsize(os.path.join(a.layers, 'occupations.json')) / 1e6:.2f} MB), "
          f"pumas.json ({os.path.getsize(os.path.join(a.layers, 'pumas.json')) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
