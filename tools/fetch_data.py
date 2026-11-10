"""Download the pinned public snapshot this project analyses, or verify it against upstream/MANIFEST.json.

Sources are US federal government works: the eCFR point-in-time XML of 42 CFR Part 438 and the Federal Register
documents that amended it. Run `python3 tools/fetch_data.py` to refresh, `--verify` to check the checksums.
"""

import argparse
import gzip
import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "upstream"
ECFR = "https://www.ecfr.gov/api/versioner/v1"
FR = "https://www.federalregister.gov/api/v1"
AGENT = "regulatory-change-research/1.0"
FR_FIELDS = (
    "document_number",
    "title",
    "type",
    "action",
    "publication_date",
    "effective_on",
    "dates",
    "cfr_references",
    "correction_of",
    "corrections",
    "full_text_xml_url",
    "html_url",
    "citation",
    "start_page",
    "end_page",
)


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
    time.sleep(1)  # one request a second: both sites ask clients to be gentle
    return body


def save(relative, body, manifest, url):
    path = DATA / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    manifest[relative] = {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def fetch():
    manifest = {}
    versions_url = f"{ECFR}/versions/title-42.json?part=438"
    versions = get(versions_url)
    save("ecfr/versions.json", versions, manifest, versions_url)
    for date in sorted({v["date"] for v in json.loads(versions)["content_versions"]}):
        url = f"{ECFR}/full/{date}/title-42.xml?part=438"
        save(f"ecfr/part438-{date}.xml", get(url), manifest, url)
    query = "&".join(
        [
            "per_page=100",
            "conditions[cfr][title]=42",
            "conditions[cfr][part]=438",
            "conditions[publication_date][gte]=2016-01-01",
            "order=oldest",
        ]
        + [f"fields[]={f}" for f in FR_FIELDS]
    )
    listing_url = f"{FR}/documents.json?{query}"
    listing = get(listing_url)
    save("fr/documents.json", listing, manifest, listing_url)
    for document in json.loads(listing)["results"]:
        if url := document.get("full_text_xml_url"):
            save(f"fr/{document['document_number']}.xml", get(url), manifest, url)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    (DATA / "MANIFEST.json").write_text(json.dumps({"fetched_at": stamp, "files": manifest}, indent=1) + "\n")


def verify():
    files = json.loads((DATA / "MANIFEST.json").read_text())["files"]
    bad = [
        name
        for name, meta in files.items()
        if hashlib.sha256((DATA / name).read_bytes()).hexdigest() != meta["sha256"]
    ]
    print(f"{len(files) - len(bad)}/{len(files)} files match" + (f"; mismatched: {bad}" if bad else ""))
    return not bad


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="check upstream/ against MANIFEST.json")
    args = parser.parse_args()
    if args.verify:
        raise SystemExit(0 if verify() else 1)
    fetch()
