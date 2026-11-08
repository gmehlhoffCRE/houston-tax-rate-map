"""
Labor detail for the drive-time labor shed: adds occupation, earnings and job counts to each census tract in the
labor layer (labor.json from build_layers.py, ACS employment status by tract centroid).

  python build_labor.py --layers layers_out/web/data/layers [--raw layers_raw] [--acs-year 2023] [--lodes-year 2024]

Adds to every tract:
  ptm, prod, trans, matl   residents employed in production, transportation and material moving occupations
                           (all three, then each), ACS 5-year table C24010 (Census table-based summary file; the
                           API now wants a key, the summary files do not)
  ptm_earn, earn           median earnings of those workers and of all workers, ACS B24021 (dollars, 12 months)
  rac_tot, rac_ind         workers living in the tract (primary jobs) and those working in manufacturing, wholesale
                           trade or transportation and warehousing (LEHD LODES RAC, NAICS 31-33, 42, 48-49)
  wac_tot, wac_ind, wac_tw jobs located in the tract: all, the same industrial group, transportation and
                           warehousing only (LEHD LODES WAC) -- the competition for the same workers

Hosts: www2.census.gov (ACS summary files, streamed: 245 + 180 MB nationwide), lehd.ces.census.gov.
"""
import argparse, csv, gzip, io, json, os, sys, urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from fetch_fortbend import get

SF = "https://www2.census.gov/programs-surveys/acs/summary_file/{y}/table-based-SF/data/5YRData/acsdt5y{y}-{t}.dat"
LODES = "https://lehd.ces.census.gov/data/lodes/LODES8/tx/{kind}/tx_{kind}_S000_JT01_{y}.csv.gz"
C24010 = {"ptm": ("C24010_E034", "C24010_E070"), "prod": ("C24010_E035", "C24010_E071"),
          "trans": ("C24010_E036", "C24010_E072"), "matl": ("C24010_E037", "C24010_E073")}


def sf_rows(url, keep):
    """Streams a pipe-delimited ACS summary file and yields rows (dicts) whose GEO_ID passes keep()."""
    req = urllib.request.Request(url, headers={"User-Agent": "tax-rate-map-pipeline"})
    with urllib.request.urlopen(req, timeout=600) as r:
        lines = io.TextIOWrapper(r, encoding="utf-8", errors="replace")
        head = next(lines).rstrip("\n").split("|")
        for ln in lines:
            if keep(ln[:30]):
                yield dict(zip(head, ln.rstrip("\n").split("|")))
IND = ("CNS05", "CNS06", "CNS08")   # manufacturing, wholesale trade, transportation and warehousing


def num(v):
    try:
        x = float(v)
        return None if x < 0 else x   # ACS codes missing values as large negatives
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", required=True)
    ap.add_argument("--raw", default="layers_raw")
    ap.add_argument("--acs-year", type=int, default=2023)
    ap.add_argument("--lodes-year", type=int, default=2024)
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True)
    path = os.path.join(a.layers, "labor.json")
    lab = json.load(open(path))
    tracts = {f["properties"]["tract"]: f["properties"] for f in lab["features"]}
    print(f"{len(tracts):,} tracts", flush=True)

    # ACS by tract from the table-based summary files (Texas tracts only: GEO_ID 1400000US48...)
    tx = lambda h: h.startswith("1400000US48")
    got = 0
    for r in sf_rows(SF.format(y=a.acs_year, t="c24010"), tx):
        p = tracts.get(r["GEO_ID"][-11:])
        if p is None:
            continue
        for k, (m, f) in C24010.items():
            p[k] = int((num(r.get(m)) or 0) + (num(r.get(f)) or 0))
        got += 1
    print(f"ACS {a.acs_year} C24010: {got:,} tracts", flush=True)
    got = 0
    for r in sf_rows(SF.format(y=a.acs_year, t="b24021"), tx):
        p = tracts.get(r["GEO_ID"][-11:])
        if p is None:
            continue
        e = num(r.get("B24021_E033")); p["ptm_earn"] = int(e) if e else None
        e = num(r.get("B24021_E001")); p["earn"] = int(e) if e else None
        got += 1
    print(f"ACS {a.acs_year} B24021: {got:,} tracts", flush=True)

    # LODES RAC (where workers live) and WAC (where jobs are), blocks summed to tracts
    for kind in ("rac", "wac"):
        fp = os.path.join(a.raw, f"tx_{kind}_{a.lodes_year}.csv.gz")
        if not os.path.exists(fp):
            open(fp, "wb").write(get(LODES.format(kind=kind, y=a.lodes_year)))
        tot, ind, tw = defaultdict(int), defaultdict(int), defaultdict(int)
        with gzip.open(fp, "rt") as fh:
            rd = csv.DictReader(fh); key = "h_geocode" if kind == "rac" else "w_geocode"
            for r in rd:
                t = r[key][:11]
                if t not in tracts:
                    continue
                tot[t] += int(r["C000"]); ind[t] += sum(int(r[c]) for c in IND); tw[t] += int(r["CNS08"])
        for t, p in tracts.items():
            p[kind + "_tot"] = tot.get(t, 0); p[kind + "_ind"] = ind.get(t, 0)
            if kind == "wac":
                p["wac_tw"] = tw.get(t, 0)
        print(f"LODES {kind.upper()} {a.lodes_year}: {sum(tot.values()):,} primary jobs, {sum(ind.values()):,} industrial", flush=True)
    lab["meta"] = {"acs": a.acs_year, "lodes": a.lodes_year}
    json.dump(lab, open(path, "w"), separators=(",", ":"))
    print(f"wrote {path} ({os.path.getsize(path) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
