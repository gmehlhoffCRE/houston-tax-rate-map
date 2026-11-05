"""
Montgomery County rates in the same shape as the Harris pipeline, so build_county_data.py can map it.

Inputs
  --src        folder with mc_parcels_raw.geojsonl (fetch_fortbend.py --prefix mc, City of Houston MCAD mirror)
  --workbook   Montgomery_County_Tax_Rates_2025_2026.xlsx (tax office Truth in Taxation rates, by entity name)
  --codes      mc_tax_office_codes_2026.csv (MCAD code -> name for the 68 units the tax office collects)
  --code-map   mc_code_map.csv: MCAD code -> workbook entity. Written on first run with every code found on
               parcels; edit it (or replace it with MCAD's list) and rerun. Columns:
                 code, entity (exact workbook name, or blank), kind (rate | no_rate | unknown),
                 basis (how it was matched), confirmed (yes | no), parcels
Outputs (into --out): mc_rate_table.csv, mc_combos.csv, mc_account_rates.csv.gz, mc_combo_registry.csv
        (into --src): mc_real_acct.txt, mc_parcels.gpkg

MCAD lists taxing units per parcel as codes (TAXINGUNIT, e.g. "CAD,CHO,GMO,HM1,JNH,RCH,SNC"). Rates come
from the workbook by entity name; "No Tax Levied" counts as 0. Appraised values are not in the mirror, so
Montgomery accounts carry no value until MCAD's certified export is added.

Usage: python build_montgomery_rates.py --src montgomery --workbook ../data/montgomery/...xlsx \
         --codes ../data/montgomery/mc_tax_office_codes_2026.csv --code-map ../data/montgomery/mc_code_map.csv \
         --out ../data --year 2025
"""
import argparse, collections, json, os, re
import numpy as np, pandas as pd, geopandas as gpd, shapely

MC_OFFSET = 60000
# tax office names that differ from the workbook's
NAME_OVERRIDES = {"CWT": "Woodlands Township, The", "MSM": "Southern Montgomery County MUD",
                  "T03": "Porter MUD - Hendricks Defined Area", "T06": "New Caney MUD - Hendricks Defined Area",
                  "T08": "Porter MUD - Montgomery Crossing Defined Area", "RU1": "Woodlands Road Utility District 1, The"}


def norm(s):
    s = str(s).lower()
    s = re.sub(r",\s*(city|town) of$", "", s); s = re.sub(r"^(city|town|village) of ", "", s)
    s = s.replace("montgomery co ", "montgomery county ").replace(" dist", " district").replace("districtrict", "district")
    s = s.replace(" no.", " north").replace(" cc", " college system").replace(" cons ", " consolidated ")
    s = re.sub(r"\bmud 0(\d)\b", r"mud \1", s).replace("the ", "")
    return re.sub(r"[^a-z0-9]", "", s)


def category(cat, name):
    n = name.lower()
    if "management district" in n:
        return ("Management District", "mgmt")
    if cat == "County" or "hospital" in n:
        return ("County / Countywide", "base")
    if cat == "Cities" or "township" in n:
        return ("City", "base")
    if cat == "School Districts":
        return ("ISD", "base")
    if cat == "Emergency Service Districts":
        return ("ESD", "base")
    if "college" in n:
        return ("College District", "base")
    if re.search(r"\bdd\b|drainage", n):
        return ("Drainage District", "base")
    return ("Water District (MUD/WCID/UD)", "base")


def suggest(code, wnames, cat_of):
    m = re.fullmatch(r"M(\d+)", code)
    if m and f"Montgomery County MUD {int(m.group(1))}" in wnames:
        return f"Montgomery County MUD {int(m.group(1))}", "rate", "suggested: M + number = MUD number"
    m = re.fullmatch(r"ME(\d+)", code)
    if m and f"East Montgomery County MUD {int(m.group(1))}" in wnames:
        return f"East Montgomery County MUD {int(m.group(1))}", "rate", "suggested: ME + number = East Montgomery County MUD"
    m = re.fullmatch(r"MR(\d+)", code)
    if m and f"Roman Forest PUD {m.group(1)}" in wnames:
        return f"Roman Forest PUD {m.group(1)}", "rate", "suggested: MR + number = Roman Forest PUD (MR4 is PUD 4)"
    fixed = {"MW1": "Woodlands MUD 1", "MWM": "Woodlands Metro Center MUD", "MSC": "Spring Creek UD",
             "MWC205": "Montgomery County WCID 205", "CHO": "Houston, City of"}
    if code in fixed and fixed[code] in wnames:
        return fixed[code], "rate", "suggested: name initials and location"
    if re.fullmatch(r"S[A-Z]{2}", code):
        hits = [e for e in wnames if cat_of[e] == "School Districts" and e.upper().startswith(code[1:3])]
        if len(hits) == 1:
            return hits[0], "rate", "suggested: S + ISD initials (SCO = Conroe ISD)"
    if re.match(r"(Z|RZ|ZE)", code) or code == "FTZ":
        return "", "no_rate", "zone (TIRZ / reinvestment / foreign trade): no rate, unconfirmed"
    if re.fullmatch(r"P[A-Z0-9]+", code):
        return "", "no_rate", "public improvement district: assessment, not a rate, unconfirmed"
    return "", "unknown", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="montgomery")
    ap.add_argument("--workbook", required=True)
    ap.add_argument("--codes", required=True)
    ap.add_argument("--code-map", required=True)
    ap.add_argument("--out", default="../data")
    ap.add_argument("--year", type=int, default=2025, choices=[2025, 2026])
    a = ap.parse_args()

    # ---- rates by entity name
    w = pd.read_excel(a.workbook, header=3)
    w.columns = ["category", "entity", "status", "a26", "mo26", "ds26", "nnr26", "nnrmo26", "var26",
                 "a25", "mo25", "ds25", "nnr25", "nnrmo25", "var25", "d", "dp", "coll", "phone", "notes"][:len(w.columns)]
    w = w[w.entity.notna()].copy()
    w["entity"] = w.entity.astype(str).str.strip()
    col = f"a{str(a.year)[2:]}"
    no_levy = w.status.fillna("").str.contains(f"{a.year}: No Tax Levied")
    w["rate"] = pd.to_numeric(w[col], errors="coerce")
    w.loc[no_levy & w.rate.isna(), "rate"] = 0.0
    wnames = set(w.entity); cat_of = dict(zip(w.entity, w.category)); rate_of = dict(zip(w.entity, w.rate))
    wnorm = {norm(e): e for e in w.entity}

    # ---- parcels
    rows, geoms = [], []
    with open(os.path.join(a.src, "mc_parcels_raw.geojsonl")) as f:
        for line in f:
            ft = json.loads(line)
            p = ft["properties"]
            if p.get("PARCEL_ID") is None or not ft.get("geometry"):
                continue
            rows.append(p); geoms.append(json.dumps(ft["geometry"]))
    P = pd.DataFrame(rows)
    P["acct"] = P.PARCEL_ID.astype("int64").astype(str)

    def units(s):
        return sorted({u.strip() for u in re.split(r"[,;]", str(s or "")) if u.strip() and u.strip() != "CAD"})
    P["units"] = P.TAXINGUNIT.map(units)
    P["key"] = P.units.map("|".join)
    acc = P.drop_duplicates("acct")[["acct", "key", "units"]]
    used = collections.Counter(u for us in acc.units for u in us)
    print(f"{len(P):,} parcel shapes, {len(acc):,} accounts, {len(used)} unit codes")

    # ---- code map: create on first run, then respect edits
    if os.path.exists(a.code_map):
        cm = pd.read_csv(a.code_map, dtype=str, keep_default_na=False)
        new = [c for c in used if c not in set(cm.code)]
    else:
        cm = pd.DataFrame(columns=["code", "entity", "kind", "basis", "confirmed", "parcels"]); new = list(used)
    if new:
        tax_office = pd.read_csv(a.codes, dtype=str)
        tname = dict(zip(tax_office.code, tax_office.name))
        add = []
        for c in new:
            if c in tname:
                e = NAME_OVERRIDES.get(c) or wnorm.get(norm(tname[c]), "")
                add.append([c, e, "rate" if e else "unknown", f"tax office list: {tname[c]}", "yes" if e else "no", ""])
            else:
                e, kind, basis = suggest(c, wnames, cat_of)
                add.append([c, e, kind, basis, "no", ""])
        cm = pd.concat([cm, pd.DataFrame(add, columns=cm.columns)], ignore_index=True)
    cm["parcels"] = cm.code.map(used).fillna(0).astype(int).astype(str)
    cm.sort_values(["confirmed", "parcels"], key=lambda s: s if s.name == "confirmed" else -s.astype(int)) \
      .to_csv(a.code_map, index=False)
    CM = cm.set_index("code")
    print("code map:", cm.kind.value_counts().to_dict(), "| confirmed:", (cm.confirmed == "yes").sum())

    # ---- rate table, one row per code
    recs = []
    for c, r in CM.iterrows():
        if r.kind == "no_rate":
            cat = ("TIRZ", "excluded") if not c.startswith("P") else ("Public Improvement District", "excluded")
            recs.append(["MC-" + c, f"{'Zone' if not c.startswith('P') else 'Improvement district'} {c}", *cat, 0.0, False])
        elif r.kind == "rate" and r.entity in wnames:
            rt = rate_of[r.entity]
            recs.append(["MC-" + c, r.entity, *category(cat_of[r.entity], r.entity), 0.0 if pd.isna(rt) else float(rt), pd.isna(rt)])
        else:
            recs.append(["MC-" + c, f"Unit {c} (not yet matched)", "Other", "base", 0.0, True])
    t = pd.DataFrame(recs, columns=["tax_dist", "name", "category", "bucket", "rate_used", "missing_rate"])
    t["accounts"] = t.tax_dist.str[3:].map(used).fillna(0).astype(int)
    t["missing_rate"] = t.missing_rate & (t.accounts > 0)
    t["tp_cd"] = ""; t["rate_prior"] = t.rate_used; t["rate_current"] = np.nan
    t[["tax_dist", "name", "tp_cd", "category", "bucket", "accounts", "rate_prior", "rate_current",
       "rate_used", "missing_rate"]].to_csv(os.path.join(a.out, "mc_rate_table.csv"), index=False)
    T = t.set_index("tax_dist")

    # ---- combos with stable ids
    reg_path = os.path.join(a.out, "mc_combo_registry.csv")
    reg = pd.read_csv(reg_path, keep_default_na=False).set_index("combo_key").combo_id if os.path.exists(reg_path) \
        else pd.Series(dtype=np.int64)
    nxt = int(reg.max()) + 1 if len(reg) else MC_OFFSET
    keys = acc.key.value_counts(); ids = {}
    for k in keys.index:
        if k in reg.index:
            ids[k] = int(reg[k])
        else:
            ids[k] = nxt; reg[k] = nxt; nxt += 1
    reg.rename("combo_id").rename_axis("combo_key").reset_index().to_csv(reg_path, index=False)
    out = []
    for k, n in keys.items():
        r = T.reindex(["MC-" + c for c in k.split("|")] if k else [])
        names = lambda m: "; ".join(sorted(set(r[m].name)))
        base = r[r.bucket == "base"].rate_used.sum(); mgmt = r[r.bucket == "mgmt"].rate_used.sum()
        out.append({"combo_id": ids[k], "rate_base": round(base, 6), "rate_mgmt": round(mgmt, 6),
                    "isd": names(r.category == "ISD"), "city": names(r.category == "City"),
                    "water_districts": names(r.category.isin(["Water District (MUD/WCID/UD)", "Drainage District"])),
                    "esd": names(r.category == "ESD"), "college": names(r.category == "College District"),
                    "mgmt_districts": names(r.bucket == "mgmt"), "tirz": names(r.category == "TIRZ"),
                    "pid": names(r.category == "Public Improvement District"),
                    "n_missing_rates": int(r.missing_rate.fillna(True).sum()),
                    "breakdown": "|".join(f"{c}:{round(float(v), 6)}" for c, v, b in zip(r.index, r.rate_used, r.bucket)
                                          if b != "excluded"),
                    "rate_total_incl_mgmt": round(base + mgmt, 6), "accounts": int(n), "tax_year": a.year})
    C = pd.DataFrame(out).sort_values("combo_id")
    C.to_csv(os.path.join(a.out, "mc_combos.csv"), index=False)
    ar = acc.assign(combo_id=acc.key.map(ids)).merge(C[["combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]], on="combo_id")
    ar[["acct", "combo_id", "rate_base", "rate_mgmt", "rate_total_incl_mgmt"]].to_csv(
        os.path.join(a.out, "mc_account_rates.csv.gz"), index=False, compression="gzip")

    # ---- account details (real_acct layout); land area from the parcel shape
    g = gpd.GeoDataFrame({"acct": P.acct}, geometry=shapely.from_geojson(geoms), crs=4326).to_crs(2278)
    land = g.assign(sf=g.geometry.area).groupby("acct").sf.sum()
    first = P.drop_duplicates("acct").set_index("acct")
    addr = first.ADDRESS.fillna("").astype(str)
    ra = pd.DataFrame({
        "acct": first.index, "mailto": first.OWNER.fillna("").values,
        "site_addr_1": addr.str.split(",").str[0].str.strip().values,
        "site_addr_2": addr.str.extract(r",\s*(.+?)\s+TX\b")[0].fillna("").str.strip().values,
        "state_class": first.STATECLASS.fillna("").values, "tot_appr_val": np.nan,
        "bld_ar": pd.to_numeric(first.IMPR_SQ_FT, errors="coerce").values,
        "land_ar": land.reindex(first.index).round().values,
    })
    ra.to_csv(os.path.join(a.src, "mc_real_acct.txt"), sep="\t", index=False, encoding="latin-1", errors="replace")
    g.to_file(os.path.join(a.src, "mc_parcels.gpkg"), driver="GPKG")

    miss_acc = int(C[C.n_missing_rates > 0].accounts.sum())
    print(f"{len(C):,} combos; {miss_acc:,} accounts touch a unit without a rate yet")
    print("base rate, accounts weighted:", ar.rate_base.describe(percentiles=[.05, .5, .95]).round(3).to_dict())


if __name__ == "__main__":
    main()
