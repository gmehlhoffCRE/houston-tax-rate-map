"""
Downloads the Chambers County inputs from Chambers CAD's "Records | Data | Reports" page.

  python fetch_chambers.py --out chambers [--roll-year 2026]
      -> chambers/ch_roll.csv          certified real and personal appraisal roll (Excel/CSV export): one row per
                                       account and owner, with up to 12 taxing unit codes (Jur 1..Jur 12),
                                       market value, state class, situs, owner
      -> chambers/ch_parcels.zip       newest "Chamber CAD Tax Parcels" shapefile (ParcelCAMA = roll Parcel_ID)

The page's file names carry upload timestamps, so links are found by their titles. Host: www.chamberscad.org.
"""
import argparse, html, os, re

from fetch_fortbend import get

PAGE = "https://www.chamberscad.org/home/DataRecords"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="chambers")
    ap.add_argument("--roll-year", type=int, default=2026)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    page = get(PAGE).decode("utf-8", "replace")
    links = [(html.unescape(h), re.sub(r"\s+", " ", t).strip())
             for h, t in re.findall(r"href='(/Forms/[^']+)'>([^<]+)</a>", page)]

    def find(pattern):
        hits = [h for h, t in links if re.search(pattern, t, re.I)]
        if not hits:
            raise SystemExit(f"no link titled like {pattern!r} on {PAGE}")
        return "https://www.chamberscad.org" + hits[0].replace(" ", "%20")

    roll = find(rf"^{a.roll_year} Certified (Real and Personal )?Appraisal Roll.*(Excel|CSV)")
    parcels = find(r"Tax Parcels")   # the page lists the newest first
    for url, name in ((roll, "ch_roll.csv"), (parcels, "ch_parcels.zip")):
        data = get(url)
        open(os.path.join(a.out, name), "wb").write(data)
        print(f"{name}: {len(data) / 1e6:.1f} MB from {url}", flush=True)


if __name__ == "__main__":
    main()
