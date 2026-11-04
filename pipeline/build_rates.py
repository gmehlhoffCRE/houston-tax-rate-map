"""
HCAD combined tax rate builder.

Input : Real_jur_exempt.zip from https://hcad.org/pdata/pdata-property-downloads.html
Output: hcad_rate_table.csv        one row per jurisdiction (code, name, category, rates)
        hcad_combos.csv            one row per unique jurisdiction combination (rates, names, breakdown)
        hcad_account_rates.csv.gz  one row per account: combo_id + combined rates

Usage : python build_rates.py Real_jur_exempt.zip [--year 2025|2026] [--overrides rate_overrides.csv]
                               [--registry combo_registry.csv]

combo_id is stable across runs: each combination is keyed by its sorted "district:pct" set and
looked up in combo_registry.csv (created on first run, appended to after). Vector tiles store
combo_id, so a rate-only refresh (e.g. switching to 2026 rates) needs no re-tiling.

Rate columns in HCAD's jur_tax_dist_exempt_value_rate.txt:
  prop = prior tax year adopted rate (verified: 2025 Harris County 0.38096, Flood 0.04966, Port 0.0059)
  curr = current tax year rate, filled in by HCAD as jurisdictions are certified
--year 2025 uses prop; --year 2026 uses curr and falls back to prop where curr is not loaded yet.
overrides csv: columns tax_dist,rate (patches gaps or newer adopted rates).
"""
import argparse, re, zipfile
import numpy as np
import pandas as pd

CATEGORY = {
    "I": "ISD", "C": "City", "N": "City Industrial District", "J": "College District",
    "T": "County / Countywide", "W": "Water District (MUD/WCID/UD)", "A": "Defined Area",
    "D": "Drainage District", "E": "ESD", "F": "ESD", "B": "ESD",
    "M": "Management District", "Z": "Special District",
}
TIRZ_PAT = re.compile(r"TIRZ|TRIZ|T I F|\bZONE\b|\bZN\b|\(\d{3}\)")


def classify(tp, name):
    if not isinstance(tp, str):
        return ("Not assigned to any account", "base")
    if tp == "Z":
        return ("TIRZ", "excluded") if TIRZ_PAT.search(name or "") else ("Management / Improvement District", "mgmt")
    if tp == "M":
        return ("Management District", "mgmt")
    return (CATEGORY.get(tp, "Other"), "base")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--overrides")
    ap.add_argument("--registry", default="combo_registry.csv")
    a = ap.parse_args()

    z = zipfile.ZipFile(a.zip)
    rt = pd.read_csv(z.open("jur_tax_dist_exempt_value_rate.txt"), sep="\t", dtype=str)
    rt["tax_dist"] = rt.tax_dist.str.strip()
    rt = rt.drop_duplicates("tax_dist")[["tax_dist", "name", "prop", "curr"]]
    rt["rate_prior"] = rt.prop.astype(float)
    rt["rate_current"] = rt.curr.astype(float)

    # Read codes as strings, then categorize per chunk. pandas 3 infers integer categories from
    # dtype="category", which turns "001" into 1 and drops account-number leading zeros.
    from pandas.api.types import union_categoricals
    parts = []
    for ch in pd.read_csv(z.open("jur_value.txt"), sep="\t", chunksize=2_000_000,
                          usecols=["acct", "tax_district", "tp_cd", "pct_district"],
                          dtype={"acct": str, "tax_district": str, "tp_cd": str, "pct_district": "float32"}):
        parts.append(pd.DataFrame({c: ch[c].astype("category") for c in ["acct", "tax_district", "tp_cd"]}
                                  | {"pct_district": ch.pct_district.to_numpy()}))
    jv = pd.DataFrame({c: union_categoricals([p[c] for p in parts]) for c in ["acct", "tax_district", "tp_cd"]}
                      | {"pct_district": np.concatenate([p.pct_district.to_numpy() for p in parts])})
    del parts
    old = [c.strip() for c in jv.tax_district.cat.categories]
    uniq = sorted(set(old))
    remap = np.array([uniq.index(c) for c in old], dtype=np.int32)
    jv["tax_district"] = pd.Categorical.from_codes(remap[jv.tax_district.cat.codes.to_numpy()], uniq)
    jv = jv.rename(columns={"pct_district": "pct"})

    # jurisdiction table
    use = pd.DataFrame({
        "tp_cd": jv.groupby("tax_district", observed=True).tp_cd.first().astype(str),
        "accounts": jv.groupby("tax_district", observed=True).size(),
    })
    use.index = use.index.astype(str)
    t = rt.set_index("tax_dist").join(use, how="outer")
    t.index.name = "tax_dist"
    t = t.groupby(level=0).first()
    t["name"] = t.name.fillna("(not in HCAD rate file)").str.strip()
    t[["category", "bucket"]] = [classify(tp, n) for tp, n in zip(t.tp_cd, t.name)]
    t["accounts"] = t.accounts.fillna(0).astype(int)

    if a.year == 2025:
        t["rate_used"] = t.rate_prior
    else:
        t["rate_used"] = t.rate_current.where(t.rate_current > 0, t.rate_prior)
    if a.overrides:
        ov = pd.read_csv(a.overrides, dtype={"tax_dist": str}).set_index("tax_dist").rate
        t.loc[t.index.intersection(ov.index), "rate_used"] = ov
    t.loc[t.bucket == "excluded", "rate_used"] = 0.0
    t["rate_used"] = t.rate_used.fillna(0.0)
    t["missing_rate"] = (t.bucket != "excluded") & (t.rate_used == 0) & (t.accounts > 0)
    t.reset_index()[["tax_dist", "name", "tp_cd", "category", "bucket", "accounts",
                     "rate_prior", "rate_current", "rate_used", "missing_rate"]] \
        .sort_values(["category", "name"]).to_csv("hcad_rate_table.csv", index=False)

    # Accounts share a small number of jurisdiction "combos". Hash each account's
    # (district, pct) set, solve each combo once, then map accounts to combos.
    rng = np.random.default_rng(7)
    cats = list(jv.tax_district.cat.categories)
    salt = pd.Series(rng.integers(1, 2**62, len(cats), dtype=np.int64).astype(np.uint64), index=cats)
    pct_i = np.round(jv.pct.to_numpy() * 10000).astype(np.uint64)
    jv["h"] = salt.to_numpy()[jv.tax_district.cat.codes.to_numpy()] * pct_i
    key = jv.groupby("acct", observed=True).h.sum()
    combo_of_key = {k: i for i, k in enumerate(pd.unique(key.to_numpy()))}
    acct_combo = key.map(combo_of_key).astype(np.int32).rename("combo_id")
    rep = acct_combo.reset_index().drop_duplicates("combo_id").set_index("acct").combo_id
    jr = jv[jv.acct.isin(rep.index)].copy()
    jr["acct"] = jr.acct.astype(str)
    jr["tax_district"] = jr.tax_district.astype(str)
    jr["combo_id"] = jr.acct.map({str(k): v for k, v in rep.items()})

    # Stable IDs: key each combo by its sorted district:pct set, reuse IDs from the registry.
    ckey = (jr.assign(k=jr.tax_district + ":" + jr.pct.round(4).map("{:.4f}".format))
              .sort_values(["combo_id", "k"]).groupby("combo_id").k.agg("|".join))
    try:
        reg = pd.read_csv(a.registry, dtype={"combo_key": str}).set_index("combo_key").combo_id
    except FileNotFoundError:
        reg = pd.Series(dtype=np.int64, name="combo_id")
    nxt = int(reg.max()) + 1 if len(reg) else 0
    remap, added = {}, []
    for tmp_id, k in ckey.items():          # ckey is ordered by first appearance, like the old IDs
        if k in reg.index:
            remap[tmp_id] = int(reg[k])
        else:
            remap[tmp_id] = nxt; added.append((k, nxt)); nxt += 1
    if added:
        reg = pd.concat([reg, pd.Series({k: i for k, i in added}, name="combo_id")])
        reg.rename_axis("combo_key").reset_index().to_csv(a.registry, index=False)
    acct_combo = acct_combo.map(remap).astype(np.int32)
    rep = rep.map(remap)
    jr["combo_id"] = jr.combo_id.map(remap)
    print(f"combo registry: {len(reg):,} keys ({len(added):,} new) -> {a.registry}")
    jr = jr.join(t[["name", "category", "bucket", "rate_used", "missing_rate"]], on="tax_district")
    jr["w"] = jr.rate_used * jr.pct

    g = jr.groupby("combo_id")
    def names(mask, strip_suffix=False):
        n = jr[mask].name
        if strip_suffix:  # TIRZ rows repeat per participant: "MARKET SQUARE ADDITN (001)", "(061)"
            n = n.str.replace(r"\s*\(\d{3}\)", "", regex=True).str.strip()
        return n.groupby(jr[mask].combo_id).agg(lambda x: "; ".join(sorted(set(x))))
    combos = pd.DataFrame({
        "rate_base": jr[jr.bucket == "base"].groupby("combo_id").w.sum(),
        "rate_mgmt": jr[jr.bucket == "mgmt"].groupby("combo_id").w.sum(),
        "isd": names(jr.category == "ISD"),
        "city": names(jr.category.isin(["City", "City Industrial District"])),
        "water_districts": names(jr.category.isin(["Water District (MUD/WCID/UD)", "Defined Area", "Drainage District"])),
        "esd": names(jr.category == "ESD"),
        "college": names(jr.category == "College District"),
        "mgmt_districts": names(jr.bucket == "mgmt"),
        "tirz": names(jr.bucket == "excluded", strip_suffix=True),
        "n_missing_rates": jr[jr.missing_rate].groupby("combo_id").size(),
        "breakdown": jr[jr.bucket != "excluded"].sort_values("tax_district")
                     .assign(p=lambda d: d.tax_district + ":" + d.w.round(6).astype(str))
                     .groupby("combo_id").p.agg("|".join),
    }, index=pd.Index(sorted(rep.values), name="combo_id"))
    combos[["rate_base", "rate_mgmt"]] = combos[["rate_base", "rate_mgmt"]].fillna(0).round(6)
    combos["n_missing_rates"] = combos.n_missing_rates.fillna(0).astype(int)
    combos["rate_total_incl_mgmt"] = (combos.rate_base + combos.rate_mgmt).round(6)
    combos["accounts"] = acct_combo.value_counts().reindex(combos.index).fillna(0).astype(int)
    combos["tax_year"] = a.year
    combos.to_csv("hcad_combos.csv")

    acc = acct_combo.to_frame()
    acc.index = acc.index.astype(str)
    acc = acc.join(combos[["rate_base", "rate_mgmt", "rate_total_incl_mgmt"]], on="combo_id")
    acc.index.name = "acct"
    acc.to_csv("hcad_account_rates.csv.gz", compression="gzip")
    print(f"{len(acc):,} accounts | {len(combos):,} combos | {len(t):,} jurisdictions | "
          f"missing-rate jurisdictions in use: {int(t.missing_rate.sum())}")
    print(acc.rate_base.describe(percentiles=[.05, .5, .95]).round(3).to_string())


if __name__ == "__main__":
    main()
