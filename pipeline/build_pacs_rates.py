"""
Rates for a county whose appraisal district publishes a PACS 8.0 appraisal export (Brazoria, Galveston), in the
same shape as the Harris pipeline, so build_county_data.py can map it.

Inputs
  --src     folder with <prefix>_certified.zip (the CAD's certified export) and <prefix>_parcels.zip (a parcel
            shapefile whose --pid-field is the property id); fetch_brazoria.py / fetch_galveston.py write them
  --units   data/<county>/<prefix>_units_2025.csv: one row per entity code with name, category, bucket and 2025
            adopted rate. Codes and names come from the export's APPRAISAL_ENTITY_TOTALS.TXT; rates from the
            Texas Comptroller 2025 rates and levies files, matched by name (hand matches noted)
  --prefix  br | gv: output file prefix; --letter B | G: account prefix; --offset: first combo id
Outputs (into --out): <prefix>_rate_table.csv, _combos.csv, _account_rates.csv.gz, _combo_registry.csv
        (into --src): <prefix>_real_acct.txt, <prefix>_parcels.gpkg

APPRAISAL_INFO.TXT lists each property's entities, so no polygon overlay is needed. Accounts are the letter +
the CAD's property id (plain ids collide across counties). Values are certified market value; exemptions,
ag use value and abatements are not applied. Building area is the sum of main-area improvement segments
(type codes MA*, plus numeric commercial occupancy codes); garages, porches, patios and paving are left out.

Usage: python build_pacs_rates.py --prefix br --letter B --offset 90000 --src brazoria \\
         --units ../data/brazoria/br_units_2025.csv --out ../data
"""
import argparse, collections, io, os, re, zipfile
import numpy as np, pandas as pd, geopandas as gpd

F = lambda line, a, b: line[a - 1:b].strip()   # 1-based inclusive positions from the PACS layout


def num(s, dec=0):
    try:
        return int(s) / 10 ** dec if s else np.nan
    except ValueError:
        return np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--units", required=True)
    ap.add_argument("--out", default="../data")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--prefix", required=True, help="file prefix, e.g. br or gv")
    ap.add_argument("--letter", required=True, help="account prefix letter, e.g. B or G")
    ap.add_argument("--offset", type=int, required=True, help="first combo id, e.g. 90000")
    ap.add_argument("--pid-field", default="PID", help="property id field in the parcel shapefile")
    a = ap.parse_args()
    X = a.prefix
    UP = X.upper() + "-"
    L = a.letter

    U = pd.read_csv(a.units, dtype={"code": str}, keep_default_na=False).set_index("code")
    U["rate"] = pd.to_numeric(U[f"rate_{a.year}"])
    z = zipfile.ZipFile(os.path.join(a.src, f"{X}_certified.zip"))
    member = lambda tag: next(n for n in z.namelist() if n.endswith(tag))

    # ---- properties (one line per property and owner)
    recs = {}
    with io.TextIOWrapper(z.open(member("_APPRAISAL_INFO.TXT")), encoding="latin-1") as f:
        for line in f:
            pid = F(line, 1, 12).lstrip("0")
            ents = {e.strip() for e in F(line, 5202, 5341).split(",") if e.strip()}
            mv = num(F(line, 4214, 4227))
            r = recs.get(pid)
            if r is None:
                situs = " ".join(x for x in (F(line, 4460, 4474), F(line, 1040, 1049), F(line, 1050, 1099),
                                             F(line, 1100, 1109)) if x)
                recs[pid] = r = {"owner": F(line, 609, 678), "addr": situs, "city": F(line, 1110, 1139),
                                 "cls": F(line, 2732, 2741) or F(line, 2742, 2751), "mv": mv,
                                 "acres": num(F(line, 1660, 1675), 4), "ents": ents, "type": F(line, 13, 17),
                                 "owners": 1}
            else:   # partial owners: union of entities, the larger value, "ET AL" on the owner
                r["ents"] |= ents; r["owners"] += 1
                r["mv"] = np.nanmax([r["mv"], mv])
    print(f"{len(recs):,} properties", flush=True)

    # ---- building area: main-area improvement segments
    bld = collections.Counter()
    main = re.compile(r"^(MA|\d+$)")
    with io.TextIOWrapper(z.open(member("_APPRAISAL_IMPROVEMENT_DETAIL.TXT")), encoding="latin-1") as f:
        for line in f:
            if main.match(F(line, 41, 50)):
                area = num(F(line, 94, 108).split(".")[0])
                if area == area:
                    bld[F(line, 1, 12).lstrip("0")] += area

    unknown = sorted({e for r in recs.values() for e in r["ents"]} - set(U.index))
    if unknown:
        raise SystemExit(f"entity codes missing from {a.units}: {unknown}")
    acc = pd.DataFrame({"acct": [L + p for p in recs],
                        "units": [sorted(e for e in r["ents"] if U.bucket[e] != "excluded" or U.category[e] == "TIRZ")
                                  for r in recs.values()]})
    acc["key"] = acc.units.map("|".join)
    print(f"{(acc.key == '').sum():,} properties list no taxing unit (left without a rate)")
    acc = acc[acc.key != ""]

    # ---- rate table
    used = pd.Series([c for us in acc.units for c in us]).value_counts()
    t = pd.DataFrame({"tax_dist": UP + U.index, "name": U.name.values, "tp_cd": "", "category": U.category.values,
                      "bucket": U.bucket.values, "accounts": [int(used.get(c, 0)) for c in U.index],
                      "rate_prior": U.rate.values, "rate_current": np.nan, "rate_used": U.rate.values,
                      "missing_rate": False})
    t.to_csv(os.path.join(a.out, f"{X}_rate_table.csv"), index=False)
    T = t.set_index("tax_dist")

    # ---- combos with stable ids
    reg_path = os.path.join(a.out, f"{X}_combo_registry.csv")
    reg = pd.read_csv(reg_path, keep_default_na=False).set_index("combo_key").combo_id if os.path.exists(reg_path) \
        else pd.Series(dtype=np.int64)
    nxt = int(reg.max()) + 1 if len(reg) else a.offset
    keys = acc.key.value_counts(); ids = {}
    for k in keys.index:
        if k in reg.index:
            ids[k] = int(reg[k])
        else:
            ids[k] = nxt; reg[k] = nxt; nxt += 1
    reg.rename("combo_id").rename_axis("combo_key").reset_index().to_csv(reg_path, index=False)
    out = []
    for k, n in keys.items():
        rr = T.reindex([UP + c for c in k.split("|")])
        names = lambda m: "; ".join(sorted(set(rr[m].name)))
        base = rr[rr.bucket == "base"].rate_used.sum(); mgmt = rr[rr.bucket == "mgmt"].rate_used.sum()
        out.append({"combo_id": ids[k], "rate_base": round(base, 6), "rate_mgmt": round(mgmt, 6),
                    "isd": names(rr.category == "ISD"), "city": names(rr.category == "City"),
                    "water_districts": names(rr.category.isin(["Water District (MUD/WCID/UD)", "Drainage District"])
                                             & (rr.rate_used > 0)),
                    "esd": names(rr.category == "ESD"), "college": names(rr.category == "College District"),
                    "mgmt_districts": names((rr.bucket == "mgmt") & (rr.rate_used > 0)),
                    "tirz": names(rr.category == "TIRZ"), "pid": "", "n_missing_rates": 0,
                    "breakdown": "|".join(f"{c}:{round(float(v), 6)}" for c, v, b in
                                          zip(rr.index, rr.rate_used, rr.bucket) if b != "excluded"),
                    "rate_total_incl_mgmt": round(base + mgmt, 6), "accounts": int(n), "tax_year": a.year})
    C = pd.DataFrame(out).sort_values("combo_id")
    C.to_csv(os.path.join(a.out, f"{X}_combos.csv"), index=False)
    ar = acc.assign(combo_id=acc.key.map(ids)).merge(C[["combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]],
                                                     on="combo_id")
    ar[["acct", "combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]].to_csv(
        os.path.join(a.out, f"{X}_account_rates.csv.gz"), index=False, compression="gzip")

    # ---- account details (real_acct layout)
    ra = pd.DataFrame({
        "acct": [L + p for p in recs],
        "mailto": [r["owner"] + (" ET AL" if r["owners"] > 1 else "") for r in recs.values()],
        "site_addr_1": [r["addr"] for r in recs.values()], "site_addr_2": [r["city"] for r in recs.values()],
        "state_class": [r["cls"] for r in recs.values()], "tot_appr_val": [r["mv"] for r in recs.values()],
        "bld_ar": [bld.get(p, np.nan) or np.nan for p in recs],
        "land_ar": [round(r["acres"] * 43560) if r["acres"] == r["acres"] else np.nan for r in recs.values()],
    })
    ra.to_csv(os.path.join(a.src, f"{X}_real_acct.txt"), sep="\t", index=False, encoding="latin-1", errors="replace")

    # ---- parcel shapes keyed by account
    zp = os.path.join(a.src, f"{X}_parcels.zip")
    shp = [n for n in zipfile.ZipFile(zp).namelist() if n.lower().endswith(".shp")][0]
    g = gpd.read_file(f"/vsizip/{os.path.abspath(zp)}/{shp}", columns=[a.pid_field])
    g = g[pd.to_numeric(g[a.pid_field], errors="coerce").fillna(0) > 0]
    g["acct"] = L + pd.to_numeric(g[a.pid_field]).astype("int64").astype(str)
    g = g[g.geometry.notna()][["acct", "geometry"]]
    g = g.to_crs(2278) if g.crs and g.crs.to_epsg() != 2278 else g
    g["geometry"] = g.geometry.make_valid()
    g.to_file(os.path.join(a.src, f"{X}_parcels.gpkg"), driver="GPKG")
    print(f"{len(g):,} parcel shapes, {g.acct.isin(set(acc.acct)).mean():.1%} with a rate; "
          f"{acc.acct.isin(set(g.acct)).mean():.1%} of rated accounts have a shape (personal property, minerals do not)")
    print(f"{len(C):,} combos; building area on {sum(1 for v in ra.bld_ar if v == v):,} properties")
    print("base rate, accounts weighted:", ar.rate_base.describe(percentiles=[.05, .5, .95]).round(3).to_dict())


if __name__ == "__main__":
    main()
