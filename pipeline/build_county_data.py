"""
Countywide data export for the tiled Harris County map.

Inputs
  --gis    folder with Parcels.gdb (or pass --parcels) and the overlay downloads
           (City, School, Water_district, Emergency, Special, TIRZ: unzipped folders or the .zip files)
  --cama   Real_acct_owner.zip (or an extracted real_acct.txt)
  --rates  folder with build_rates.py outputs: hcad_account_rates.csv.gz, hcad_combos.csv, hcad_rate_table.csv

Outputs (under --out)
  parcels.geojsonl                  WGS84 parcels for tippecanoe (build_tiles.sh). Properties:
                                    a = HCAD account, c = combo_id (-1 = no rate data), t = type group, v = appraised value
  web/data/combos.json              rates, names and per-type account counts for every combo, jurisdiction names
  web/data/boundaries/<key>.json    dissolved boundary lines with label points, one file per overlay
  bucket/shards/a/<prefix>.json     account records (owner, address, values, combo, map point), adaptive prefix shards
  bucket/shards/s/<prefix>.json     search index: owner and address words, adaptive prefix shards
  bucket/shards/manifest.json       which prefixes were split into longer prefixes

Usage
  python build_county_data.py --gis ./gis --cama ./Real_acct_owner.zip --rates ../data --out ./out
  python build_county_data.py ... --bbox -95.25 29.665 -95.10 29.77     (subset, for testing)
"""
import argparse, glob, json, os, re, shutil, time, zipfile
import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely
from pyproj import Transformer

TYPE_KEYS = ["res", "com", "ind", "vac", "util", "ex", "other"]  # index = tile property t, must match the web page
# Words skipped as search keys (still matched when typed alongside a longer word). Keep in sync with STOP in the page.
STOP = set("""llc inc ltd lp llp co corp company the of and etal et al est estate trust trustee trustees
st dr rd ln ave av blvd ct cir pl way pkwy fwy hwy tr trl ste unit apt bldg n s e w ne nw se sw""".split())
OVERLAYS = [("city", "City"), ("isd", "School"), ("water", "Water_district"), ("esd", "Emergency"),
            ("special", "Special"), ("tirz", "TIRZ")]
SEARCH_MAX, ACCT_MAX, PARTIAL_CAP = 3000, 3000, 60


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def clean(v):
    return " ".join(v.split()) if isinstance(v, str) else ""


def norm_words(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower().replace("'", "")).split()


def type_group(cls):
    c = cls or ""
    if not c:
        return 6
    if c[0] in "ABE":
        return 0
    if c.startswith("F1"):
        return 1
    if c.startswith("F2"):
        return 2
    return {"C": 3, "J": 4, "X": 5}.get(c[0], 6)


def to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- inputs
def read_real_acct(path):
    if path.endswith(".zip"):
        z = zipfile.ZipFile(path)
        opener = lambda: z.open("real_acct.txt")
    else:
        opener = lambda: open(path, "rb")
    header = opener().readline().decode("latin-1").rstrip("\r\n").split("\t")
    want = ["acct", "mailto", "site_addr_1", "site_addr_2", "state_class", "tot_appr_val", "bld_ar", "land_ar"]
    use = [c for c in want if c in header]
    parts = []
    for ch in pd.read_csv(opener(), sep="\t", dtype=str, chunksize=400_000, encoding="latin-1",
                          quoting=3, usecols=use):
        ch["acct"] = ch.acct.str.strip()
        parts.append(ch)
    ra = pd.concat(parts).drop_duplicates("acct").set_index("acct")
    for c in want[1:]:
        if c not in ra:
            ra[c] = None
    return ra


def find_source(gis, name):
    for pat in (f"{name}/**/*.shp", f"{name}*/**/*.shp", f"**/{name}*.shp"):
        hits = glob.glob(os.path.join(gis, pat), recursive=True)
        if hits:
            return hits[0]
    for z in glob.glob(os.path.join(gis, f"{name}*.zip")):
        inner = [n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith(".shp")]
        if inner:
            return f"/vsizip/{os.path.abspath(z)}/{inner[0]}"
    hits = glob.glob(os.path.join(gis, f"{name}*.gpkg")) + glob.glob(os.path.join(gis, f"{name}*.geojson"))
    return hits[0] if hits else None


# ---------------------------------------------------------------- parcels
def export_parcels(a, acct_info, out_path):
    src = a.parcels or os.path.join(a.gis, "Parcels.gdb")
    info = pyogrio.read_info(src, layer=a.parcels_layer)
    crs = info["crs"]
    total = info["features"]
    bbox = None
    if a.bbox:
        tr = Transformer.from_crs(4326, crs, always_xy=True)
        W, S, E, N = a.bbox
        xs, ys = tr.transform([W, E, W, E], [S, S, N, N])
        bbox = (min(xs), min(ys), max(xs), max(ys))
    cols = [c for c in ("HCAD_NUM_1", "HCAD_NUM", "CurrOwner") if c in info["fields"]]
    acct_col = "HCAD_NUM_1" if "HCAD_NUM_1" in cols else "HCAD_NUM"
    log(f"parcels: {total:,} features in {src} ({crs})")

    points = {}   # acct -> (lon, lat, area) of its largest polygon
    owners = {}   # parcel owner, fallback when real_acct has none
    n_written = n_norate = 0
    step = 250_000
    with open(out_path, "w") as fo:
        for off in range(0, total, step):
            g = pyogrio.read_dataframe(src, layer=a.parcels_layer, columns=cols, bbox=bbox,
                                       skip_features=off, max_features=step, force_2d=True)
            if not len(g):
                continue
            g = g[g[acct_col].notna() & g.geometry.notna()]
            g = g[~g.geometry.is_empty]
            g["acct"] = g[acct_col].astype(str).str.strip()
            g = g[g.acct.str.len() > 0]
            g["geometry"] = g.geometry.simplify(0.5)         # source units are feet; removes digitizing noise
            area = g.geometry.area.to_numpy()
            rp = gpd.GeoSeries(g.geometry.representative_point(), crs=g.crs).to_crs(4326)
            rx, ry = rp.x.to_numpy(), rp.y.to_numpy()
            g = g.to_crs(4326)
            geoms = shapely.transform(g.geometry.to_numpy(), lambda c: np.round(c, 6))
            gj = shapely.to_geojson(geoms)
            info_rows = acct_info.reindex(g.acct)
            combo = info_rows.combo_id.fillna(-1).astype(int).to_numpy()
            tgrp = info_rows.t.fillna(6).astype(int).to_numpy()
            val = info_rows.val.to_numpy()
            for i, (acct, geo) in enumerate(zip(g.acct.to_numpy(), gj)):
                if geo is None:
                    continue
                v = val[i]
                props = {"a": acct, "c": int(combo[i]), "t": int(tgrp[i]), "v": int(v) if v == v and v is not None else 0}
                fo.write('{"type":"Feature","properties":' + json.dumps(props, separators=(",", ":")) +
                         ',"geometry":' + geo + "}\n")
                n_written += 1
                n_norate += combo[i] < 0
                prev = points.get(acct)
                if prev is None or area[i] > prev[2]:
                    points[acct] = (round(float(rx[i]), 5), round(float(ry[i]), 5), area[i])
            if "CurrOwner" in g:
                for acct, o in zip(g.acct, g.CurrOwner):
                    if isinstance(o, str) and acct not in owners:
                        owners[acct] = clean(o)
            log(f"  {min(off + step, total):,}/{total:,} read, {n_written:,} written")
            if bbox is not None and off == 0 and len(g) < step:
                break   # bbox reads ignore skip_features beyond the matches
    log(f"parcels written: {n_written:,} ({n_norate:,} without a rate combo)")
    return points, owners


# ---------------------------------------------------------------- shards
def write_adaptive(df, base, maxn, outdir, payload, records, partial_cap):
    """df has columns tok (str) and rid (int, records index). Files are named by token prefix.
    A prefix with more than maxn records is split into longer prefixes; its own file then holds
    only exact-token matches (or the first partial_cap records) and is marked partial."""
    os.makedirs(outdir, exist_ok=True)
    split, nfiles, biggest = [], 0, 0
    stack = [(df, base)]
    while stack:
        sub, L = stack.pop()
        for pre, g in sub.groupby(sub.tok.str[:L], sort=False):
            rids = np.unique(g.rid.to_numpy())
            longer = g.tok.str.len().to_numpy() > L
            if len(rids) <= maxn or not longer.any():
                body = {"r": [payload(records, r) for r in rids]}
            else:
                split.append(pre)
                exact = np.unique(g.rid.to_numpy()[~longer])
                body = {"r": [payload(records, r) for r in (exact if len(exact) else rids)[:partial_cap]], "p": 1}
                stack.append((g[longer], L + 1))
            with open(os.path.join(outdir, pre + ".json"), "w") as f:
                json.dump(body, f, separators=(",", ":"), ensure_ascii=False)
            nfiles += 1
            biggest = max(biggest, len(body["r"]))
    return sorted(split), nfiles, biggest


# ---------------------------------------------------------------- boundaries
def export_boundaries(a, outdir):
    os.makedirs(outdir, exist_ok=True)
    clip = None
    if a.bbox:
        W, S, E, N = a.bbox
        clip = shapely.box(W - .02, S - .02, E + .02, N + .02)
    for key, name in OVERLAYS:
        src = find_source(a.gis, name)
        if not src:
            log(f"  boundary {key}: no source for {name}, skipped")
            continue
        o = pyogrio.read_dataframe(src, force_2d=True)
        ncol = next((c for c in o.columns if c.lower() == "name"), None)
        if ncol is None or not len(o):
            log(f"  boundary {key}: no name field in {src}, skipped")
            continue
        o = o[[ncol, "geometry"]].rename(columns={ncol: "name"})
        o = o[o.geometry.notna()]
        if o.crs and o.crs.is_geographic:
            o = o.to_crs(2278)
        o["geometry"] = o.geometry.buffer(0).simplify(15)
        o = o.to_crs(4326)
        if clip is not None:
            o = gpd.clip(o, clip)
        o["name"] = o["name"].astype(str).str.replace(r"\s*\(\d{3}\)", "", regex=True).str.strip()
        o = o.dissolve(by="name", as_index=False)
        feats = []
        for _, r in o.iterrows():
            if r.geometry is None or r.geometry.is_empty:
                continue
            lp = r.geometry.representative_point()
            line = shapely.transform(r.geometry.boundary, lambda c: np.round(c, 5))
            feats.append({"type": "Feature", "properties": {"name": r["name"], "lp": [round(lp.x, 5), round(lp.y, 5)]},
                          "geometry": json.loads(shapely.to_geojson(line))})
        with open(os.path.join(outdir, key + ".json"), "w") as f:
            json.dump({"type": "FeatureCollection", "features": feats}, f, separators=(",", ":"))
        log(f"  boundary {key}: {len(feats)} areas from {src}")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gis", required=True)
    ap.add_argument("--parcels", help="parcel source (default <gis>/Parcels.gdb)")
    ap.add_argument("--parcels-layer", default=None)
    ap.add_argument("--cama", required=True, help="Real_acct_owner.zip or real_acct.txt")
    ap.add_argument("--rates", required=True)
    ap.add_argument("--out", default="out")
    ap.add_argument("--bbox", nargs=4, type=float, help="W S E N subset (testing)")
    ap.add_argument("--value-year", type=int, default=2026)
    ap.add_argument("--skip-boundaries", action="store_true")
    a = ap.parse_args()

    web = os.path.join(a.out, "web", "data")
    shards = os.path.join(a.out, "bucket", "shards")
    for d in (web, shards):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)

    # rates and account attributes
    log("reading rates")
    ar = pd.read_csv(os.path.join(a.rates, "hcad_account_rates.csv.gz"), dtype={"acct": str},
                     usecols=["acct", "combo_id"]).set_index("acct")
    cb = pd.read_csv(os.path.join(a.rates, "hcad_combos.csv"), dtype=str, keep_default_na=False).set_index("combo_id")
    rt = pd.read_csv(os.path.join(a.rates, "hcad_rate_table.csv"), dtype={"tax_dist": str}).set_index("tax_dist")
    log("reading real_acct")
    ra = read_real_acct(a.cama)
    acct = ar.join(ra, how="outer")
    acct["combo_id"] = acct.combo_id.fillna(-1).astype(int)
    acct["t"] = [type_group(c) for c in acct.state_class.fillna("").str.strip()]
    acct["val"] = pd.to_numeric(acct.tot_appr_val, errors="coerce")
    log(f"accounts: {len(acct):,} ({(acct.combo_id < 0).sum():,} without a rate combo)")

    # parcels -> geojsonl
    os.makedirs(a.out, exist_ok=True)
    points, parcel_owner = export_parcels(a, acct, os.path.join(a.out, "parcels.geojsonl"))

    # account records. In bbox mode keep only accounts that have a parcel in the box.
    if a.bbox:
        acct = acct[acct.index.isin(points.keys())]
    owner = acct.mailto.map(clean)
    miss = owner == ""
    owner[miss] = [parcel_owner.get(x, "") for x in acct.index[miss]]
    pt = [points.get(x) for x in acct.index]
    rec = pd.DataFrame({
        "acct": acct.index.to_numpy(), "owner": owner.to_numpy(),
        "addr": acct.site_addr_1.map(clean).to_numpy(), "city": acct.site_addr_2.map(clean).to_numpy(),
        "cls": acct.state_class.map(clean).to_numpy(), "val": acct.val.to_numpy(),
        "bld": acct.bld_ar.map(to_int).to_numpy(), "land": acct.land_ar.map(to_int).to_numpy(),
        "combo": acct.combo_id.to_numpy(),
        "x": [int(round(p[0] * 1e5)) if p else None for p in pt],
        "y": [int(round(p[1] * 1e5)) if p else None for p in pt],
    })
    # highest value first, so each shard lists the most significant matches first
    rec = rec.sort_values("val", ascending=False, na_position="last").reset_index(drop=True)
    R = rec.to_dict("list")
    R["val"] = [None if v != v else int(v) for v in R["val"]]
    R["x"] = [None if v != v or v is None else int(v) for v in R["x"]]
    R["y"] = [None if v != v or v is None else int(v) for v in R["y"]]

    def acct_payload(R, i):
        return [R["acct"][i], R["owner"][i], R["addr"][i], R["city"][i], R["cls"][i], R["val"][i],
                R["bld"][i], R["land"][i], int(R["combo"][i]), R["x"][i], R["y"][i]]

    def search_payload(R, i):
        return [R["acct"][i], R["owner"][i], R["addr"][i], R["x"][i], R["y"][i]]

    log("writing account shards")
    adf = pd.DataFrame({"tok": rec.acct, "rid": np.arange(len(rec))})
    a_split, a_files, a_big = write_adaptive(adf, 4, ACCT_MAX, os.path.join(shards, "a"), acct_payload, R, PARTIAL_CAP)
    log(f"  {a_files:,} files, largest {a_big:,} records, {len(a_split):,} split prefixes")

    log("building search index")
    toks, rids = [], []
    for i, (o, ad) in enumerate(zip(R["owner"], R["addr"])):
        words = {w for w in norm_words(o) + norm_words(ad) if len(w) >= 3 and w not in STOP and w != "0"}
        toks.extend(words)
        rids.extend([i] * len(words))
    sdf = pd.DataFrame({"tok": toks, "rid": np.array(rids, dtype=np.int32)})
    del toks, rids
    log(f"  {len(sdf):,} word entries")
    s_split, s_files, s_big = write_adaptive(sdf, 3, SEARCH_MAX, os.path.join(shards, "s"), search_payload, R, PARTIAL_CAP)
    log(f"  {s_files:,} files, largest {s_big:,} records, {len(s_split):,} split prefixes")

    # combos.json
    log("writing combos.json")
    jur_codes = set()
    combos = []
    counts = pd.crosstab(acct.combo_id, acct.t).reindex(columns=range(7), fill_value=0)
    for cid, r in cb.iterrows():
        cid = int(cid)
        parts = []
        for x in filter(None, r.breakdown.split("|")):
            code, w = x.split(":")
            parts.append([code, round(float(w), 6)])
            jur_codes.add(code)
        mb = sum(1 for c, _ in parts if c in rt.index and bool(rt.loc[c, "missing_rate"]) and rt.loc[c, "bucket"] == "base")
        mm = sum(1 for c, _ in parts if c in rt.index and bool(rt.loc[c, "missing_rate"]) and rt.loc[c, "bucket"] == "mgmt")
        tirz = "; ".join(sorted({re.sub(r"\s*\(\d{3}\)", "", t).strip() for t in r.tirz.split(";") if t.strip()}))
        n = counts.loc[cid].tolist() if cid in counts.index else [0] * 7
        combos.append({"id": cid, "b": round(float(r.rate_base), 6), "m": round(float(r.rate_mgmt), 6),
                       "isd": r.isd, "city": r.city, "water": r.water_districts, "esd": r.esd, "college": r.college,
                       "mg": r.mgmt_districts, "tirz": tirz, "mb": mb, "mm": mm, "p": parts, "n": [int(v) for v in n]})
    jur = {c: [rt.loc[c, "name"], rt.loc[c, "category"], rt.loc[c, "bucket"]] for c in sorted(jur_codes) if c in rt.index}
    tax_year = int(cb.tax_year.iloc[0]) if "tax_year" in cb and len(cb) else 2025
    meta = {"taxYear": tax_year, "valueYear": a.value_year, "built": time.strftime("%Y-%m-%d"),
            "accounts": int(len(acct)), "parcels": int(len(points)), "noRateAccounts": int((acct.combo_id < 0).sum()),
            "noRateByType": [int(x) for x in np.bincount(acct.t[acct.combo_id < 0], minlength=7)],
            "types": TYPE_KEYS, "bbox": a.bbox or [-95.97, 29.49, -94.90, 30.18]}
    with open(os.path.join(web, "combos.json"), "w") as f:
        json.dump({"meta": meta, "jur": jur, "combos": combos}, f, separators=(",", ":"), ensure_ascii=False)
    with open(os.path.join(shards, "manifest.json"), "w") as f:
        json.dump({"built": meta["built"], "a": {"base": 4, "split": a_split}, "s": {"base": 3, "split": s_split}},
                  f, separators=(",", ":"))

    if not a.skip_boundaries:
        log("writing boundaries")
        export_boundaries(a, os.path.join(web, "boundaries"))
    log("done")


if __name__ == "__main__":
    main()
