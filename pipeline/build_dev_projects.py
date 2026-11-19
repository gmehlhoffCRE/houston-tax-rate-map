"""
Development projects from the Texas Department of Licensing and Regulation's Architectural Barriers registry (TABS).
Every commercial or public building project in Texas costing $50,000 or more must be registered with TDLR before
construction, with its address, estimated cost, square footage, scope and estimated start and completion dates, so
the registry is a good early signal of new buildings.

  python build_dev_projects.py --raw layers_raw/tabs --embed out8 --out layers_out [--since 01/01/2025]
      -> layers_out/web/data/layers/dev_projects.json

Steps:
  1. List every project registered in the 8 counties since --since (TABS project search, 100 per request).
  2. Fetch the details page for candidates: new construction or additions of $1M+, or any project whose name looks
     industrial (warehouse, distribution, manufacturing...) at $250k+ (renovations at $5M+). Pages are cached in
     --raw, so reruns only fetch new projects. Requests are paced (0.35 s apart).
  3. Classify: industrial (warehouse, distribution, logistics, manufacturing, plant, cold storage, data center, flex,
     industrial park...) or other commercial; self storage is its own class.
  4. Locate: the project address is matched to an appraisal account address in the same city (the map's parcel
     records), then to the address alone when that is unique. Unmatched projects are left out and counted.

Stage from TDLR's estimated dates and status: planned (start in the future), under construction (started, completion
in the future), completed (completion passed or TDLR inspection complete), kept for 2 years after completion.

Host: www.tdlr.texas.gov
"""
import argparse, glob, html, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import date, datetime

BASE = "https://www.tdlr.texas.gov/TABS/Search"
COUNTIES = {2101: "Harris", 2079: "Fort Bend", 2167: "Montgomery", 2237: "Waller", 2036: "Chambers",
            2020: "Brazoria", 2146: "Liberty", 2084: "Galveston"}
WORK = {9001: "New construction", 9002: "Renovation", 9003: "Addition"}
STATUS = {3001: "Inspection complete", 3007: "Closed", 3008: "Registered", 3009: "Plan review complete"}
IND = re.compile(r"warehouse|distribution|logistic|industrial|manufactur|\bplant\b|fabricat|cold storage|freezer|"
                 r"data ?cent|\bflex\b|tilt[- ]?wall|shell bldg|shell building|spec building|business park|"
                 r"commerce (park|center)|trade (park|center)|cross[- ]?dock|\btruck|\bterminal\b|processing|assembly|"
                 r"machine shop|\bshop building|office/?warehouse|\bo/w\b|industrial park|logistics park|rail ?park", re.I)
SELF_STORAGE = re.compile(r"self[- ]?storage|mini[- ]?storage|storage units|climate controlled storage", re.I)
NOT_IND = re.compile(r"church|school|elementary|middle school|high school|apartment|residen|clubhouse|restaurant|"
                     r"retail|hotel|clinic|hospital|medical|dental|daycare|church", re.I)
GAP = 1.5   # TDLR resets connections when requests come faster


def http(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "tax-rate-map-pipeline",
                                                          "X-Requested-With": "XMLHttpRequest"})
    for i in range(8):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == 7:
                raise
            time.sleep(min(120, 5 * 2 ** i)); print(f"  retry {i + 1} after {e}", flush=True)


def list_county(code, since, raw):
    path = os.path.join(raw, f"list_{code}.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 86400:
        return json.load(open(path))
    rows, start, total = [], 0, None
    pdir = os.path.join(raw, "pages"); os.makedirs(pdir, exist_ok=True)
    while total is None or start < total:
        pp = os.path.join(pdir, f"{code}_{since.replace('/', '')}_{start}.json")   # page cache: a restart resumes here
        if os.path.exists(pp) and time.time() - os.path.getmtime(pp) < 86400:
            d = json.load(open(pp))
        else:
            d = json.loads(http(f"{BASE}/SearchProjects", {
                "draw": 1, "start": start, "length": 100, "order[0][column]": 0, "order[0][dir]": "asc",
                "LocationCounty": code, "RegistrationDateBegin": since}))
            json.dump(d, open(pp, "w")); time.sleep(GAP)
        total = d["recordsFiltered"]; rows += d["data"]; start += 100
    rows = list({r["ProjectNumber"]: r for r in rows}.values())
    json.dump(rows, open(path, "w"))
    print(f"  {COUNTIES[code]}: {len(rows):,} projects registered since {since}", flush=True)
    return rows


def details(num, raw):
    path = os.path.join(raw, "det", num + ".txt")
    if os.path.exists(path):
        return open(path).read()
    t = http(f"{BASE}/Project/{num}"); time.sleep(GAP)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", t, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "|", t)); t = re.sub(r"\s*\|[\s|]*", "|", t)
    os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w").write(t)
    return t


def field(t, label):
    m = re.search(r"\|" + re.escape(label) + r":?\|([^|]*)", t)
    return m.group(1).strip() if m else ""


SUFFIX = {"STREET": "ST", "DRIVE": "DR", "ROAD": "RD", "AVENUE": "AVE", "AV": "AVE", "BOULEVARD": "BLVD",
          "LANE": "LN", "PARKWAY": "PKWY", "HIGHWAY": "HWY", "FREEWAY": "FWY", "FRWY": "FWY", "COURT": "CT",
          "CIRCLE": "CIR", "PLACE": "PL", "TRAIL": "TRL", "WAY": "WAY", "EXPRESSWAY": "EXPY", "SUITE": "STE",
          "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "FM": "FM", "FARM": "FM", "STATE": "STATE",
          "INTERSTATE": "IH", "I": "IH", "INTERSTATE HIGHWAY": "IH"}


def norm(a):
    a = re.sub(r"[.,#]", " ", (a or "").upper())
    a = re.sub(r"\b(STE|SUITE|UNIT|BLDG|BUILDING)\b.*$", "", a)
    w = [SUFFIX.get(x, x) for x in a.split()]
    return " ".join(w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="layers_raw/tabs")
    ap.add_argument("--embed", required=True, help="parcel build folder with bucket/shards (address -> location)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--since", default="01/01/2025")
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True)

    print("listing TABS projects", flush=True)
    rows = [r for code in COUNTIES for r in list_county(code, a.since, a.raw)]
    def cand(r):
        cost, w = r.get("EstimatedCost") or 0, r.get("TypeOfWork")
        name = f"{r.get('ProjectName') or ''} {r.get('FacilityName') or ''}"
        ind = bool(IND.search(name)) and not NOT_IND.search(name)
        return (w in (9001, 9003) and cost >= 1_000_000) or (ind and ((w in (9001, 9003) and cost >= 250_000) or cost >= 5_000_000))
    cands = [r for r in rows if cand(r)]
    print(f"{len(rows):,} projects; {len(cands):,} candidates for details", flush=True)

    # address index from the parcel records
    idx, idx_a = {}, {}
    for f in glob.glob(os.path.join(a.embed, "bucket", "shards", "a", "*.json")):
        for r in json.load(open(f))["r"]:
            ad, city, x, y = norm(r[2]), (r[3] or "").upper().strip(), r[9], r[10]
            if not ad or x is None:
                continue
            idx.setdefault((ad, city), (x / 1e5, y / 1e5, r[0]))
            idx_a.setdefault(ad, []).append((x / 1e5, y / 1e5, r[0]))
    print(f"address index: {len(idx):,} addresses", flush=True)

    today = date.today(); feats = []; miss = 0; n = 0
    for r in cands:
        n += 1
        if n % 200 == 0:
            print(f"  details {n:,}/{len(cands):,}", flush=True)
        t = details(r["ProjectNumber"], a.raw)
        addr, cityzip = field(t, "Location Address"), ""
        m = re.search(r"\|Location Address:\|[^|]*\|([^|]*)\|", t)
        if m:
            cityzip = m.group(1)
        city = re.sub(r",.*$", "", cityzip).upper().strip()
        hit = idx.get((norm(addr), city))
        if not hit:
            c = idx_a.get(norm(addr), [])
            hit = c[0] if len(c) == 1 or (c and all(abs(q[0] - c[0][0]) < .01 and abs(q[1] - c[0][1]) < .01 for q in c)) else None
        if not hit:
            miss += 1; continue
        scope = field(t, "Scope of Work"); sqft = field(t, "Square Footage")
        sq = int(re.sub(r"[^\d]", "", sqft.split(" ")[0]) or 0) if sqft else 0
        name, fac = r.get("ProjectName") or "", r.get("FacilityName") or ""
        text = f"{name} {fac} {scope}"
        kind = "storage" if SELF_STORAGE.search(text) else "ind" if IND.search(text) and not NOT_IND.search(f"{name} {fac}") else "other"
        d = lambda s: datetime.fromisoformat(s[:10]).date() if s else None
        st, en = d(r.get("EstimatedStartDate")), d(r.get("EstimatedEndDate"))
        if r.get("ProjectStatus") in (3001, 3007) or (en and en < today):
            stage = "done"
            if en and (today - en).days > 730:
                continue
        elif st and st > today:
            stage = "planned"
        else:
            stage = "building"
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(hit[0], 5), round(hit[1], 5)]},
                      "properties": {"id": r["ProjectNumber"], "name": name.strip()[:90], "fac": fac.strip()[:60],
                                     "addr": addr.title(), "city": city.title(), "co": COUNTIES.get(r.get("County"), ""),
                                     "work": WORK.get(r.get("TypeOfWork"), ""), "cost": int(r.get("EstimatedCost") or 0),
                                     "sqft": sq, "start": st.isoformat() if st else "", "end": en.isoformat() if en else "",
                                     "stage": stage, "kind": kind, "owner": field(t, "Owner Name")[:70],
                                     "scope": scope[:220], "status": STATUS.get(r.get("ProjectStatus"), ""),
                                     "reg": (r.get("ProjectCreatedOn") or "")[:10]}})
    od = os.path.join(a.out, "web", "data", "layers"); os.makedirs(od, exist_ok=True)
    out = os.path.join(od, "dev_projects.json")
    json.dump({"type": "FeatureCollection", "features": feats,
               "meta": {"source": "TDLR TABS", "since": a.since, "built": today.isoformat()}}, open(out, "w"), separators=(",", ":"))
    from collections import Counter
    print(f"{len(feats):,} located ({miss:,} addresses not matched) -> {out}")
    print("by kind:", dict(Counter(f["properties"]["kind"] for f in feats)), " by stage:", dict(Counter(f["properties"]["stage"] for f in feats)))


if __name__ == "__main__":
    main()
