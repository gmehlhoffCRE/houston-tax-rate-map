"""
Downloads the Galveston County inputs from Galveston CAD's website.

  python fetch_galveston.py --out galveston [--year 2026]
      -> galveston/gv_certified.zip   certified roll export (PACS 8.0 layout), "Preliminary and Certified Roll
                                      Export Data" page
      -> galveston/gv_parcels.zip     parcels shapefile from the "GIS Data" page (PID = property id)

Then: build_pacs_rates.py --prefix gv --letter G --offset 110000 --src galveston
        --units data/galveston/gv_units_2025.csv --out data
Rates: GCAD's "2025 Galveston Tax Rates" sheet (data/galveston/gcad_2025_tax_rates.pdf). The Comptroller's 2025
special district file has copied rates for several Galveston districts, so it is not used here.
Host: galvestoncad.org.
"""
import argparse, os, re

from fetch_fortbend import get

ROLL_PAGE = "https://galvestoncad.org/preliminary-and-certified-roll-export-data/"
GIS_PAGE = "https://galvestoncad.org/gis-data/"


def link(page, pattern):
    html = get(page).decode("utf-8", "replace")
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        if re.search(pattern, re.sub(r"<[^>]+>|\s+", " ", text) + " " + href, re.I):
            return href
    raise SystemExit(f"no link like {pattern!r} on {page}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="galveston")
    ap.add_argument("--year", type=int, default=2026)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for name, page, pattern in (("gv_certified.zip", ROLL_PAGE, rf"^\s*{a.year} Certified Roll"),
                                ("gv_parcels.zip", GIS_PAGE, r"/parcels\.zip$")):
        url = link(page, pattern)
        data = get(url)
        open(os.path.join(a.out, name), "wb").write(data)
        print(f"{name}: {len(data) / 1e6:.0f} MB from {url}", flush=True)


if __name__ == "__main__":
    main()
