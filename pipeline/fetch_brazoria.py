"""
Downloads the Brazoria County inputs. Brazoria CAD's "Public GIS and Property Data Downloads" page links to pCloud
public folders; this resolves them through pCloud's public API.

  python fetch_brazoria.py --out brazoria [--year 2026]
      -> brazoria/br_certified.zip   certified appraisal export (PACS 8.0 layout, fixed width): APPRAISAL_INFO.TXT
                                     has owner, situs, values, state codes and the property's entity list;
                                     APPRAISAL_IMPROVEMENT_DETAIL.TXT has improvement areas
      -> brazoria/br_parcels.zip     current PARCELS shapefile (PID = property id), EPSG 2278

Hosts: brazoriacad.org, api.pcloud.com, def1..def4.pcloud.com (pCloud picks one per file).
"""
import argparse, json, os, re, urllib.parse

from fetch_fortbend import get

PAGE = "https://brazoriacad.org/public-gis-and-property-data-downloads/"
API = "https://api.pcloud.com"


def walk(meta, path=""):
    if meta.get("isfolder"):
        for m in meta.get("contents", []):
            yield from walk(m, path + meta["name"] + "/")
    else:
        yield path + meta["name"], meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="brazoria")
    ap.add_argument("--year", type=int, default=2026)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    codes = list(dict.fromkeys(re.findall(r"publink/show\?code=([A-Za-z0-9]+)", get(PAGE).decode("utf-8", "replace"))))
    files = {}
    for code in codes:
        meta = json.loads(get(f"{API}/showpublink?code={code}")).get("metadata", {})
        for path, m in walk(meta):
            files[path] = (code, m)
    want = {
        "br_certified.zip": rf"CURRENT CERTIFIED ROLL/{a.year}_CERTIFIED_ROLL/.*_{a.year}_BRAZORIA_COUNTY_CERTIFIED\.zip$",
        "br_parcels.zip": r"PARCEL LAYERS/PARCELS\.zip$",
    }
    for name, pattern in want.items():
        hits = sorted(p for p in files if re.search(pattern, p))
        if not hits:
            raise SystemExit(f"no file like {pattern!r} in Brazoria CAD's pCloud folders")
        code, m = files[hits[-1]]
        d = json.loads(get(f"{API}/getpublinkdownload?" + urllib.parse.urlencode({"code": code, "fileid": m["fileid"]})))
        hosts = [h for h in d["hosts"] if re.fullmatch(r"def\d\.pcloud\.com", h)] or d["hosts"]
        data = get(f"https://{hosts[0]}{d['path']}")
        open(os.path.join(a.out, name), "wb").write(data)
        print(f"{name}: {len(data) / 1e6:.0f} MB ({hits[-1]})", flush=True)


if __name__ == "__main__":
    main()
