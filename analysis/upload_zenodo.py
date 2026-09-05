#!/usr/bin/env python3
"""Stage a Zenodo record from the release bundle, without publishing it.

This does every mechanical part of the upload and then stops. It creates the
deposition, reserves the DOI, uploads the files and writes the metadata, and
then prints a URL. Pressing publish is left to a person, because publishing is
irreversible: a published Zenodo record cannot be deleted, only superseded, and
its metadata carries author names that break double blind review.

Run it against the sandbox first. The sandbox is a full copy of Zenodo that
mints throwaway DOIs, so the whole flow can be rehearsed at no cost:

    ZENODO_TOKEN=... /usr/bin/python3 analysis/upload_zenodo.py \
        --record benchmark --target sandbox

Uploads are resumable. A file already on the deposition with a matching md5 is
skipped, so an interrupted 30 GB upload can be restarted with the same command.

Tokens: zenodo.org/account/settings/applications/tokens/new (and the same path
on sandbox.zenodo.org, which needs its own separate account and token). The
scopes needed are deposit:write and deposit:actions. Revoke it when done.
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BUNDLE = Path.home() / "ns3-v2x" / "runs" / "release"
RAW = Path.home() / "ns3-v2x" / "runs"
REPO = Path(__file__).resolve().parent.parent

# Zenodo requires an author list and will not accept a record without one.
# It is left empty deliberately so an authorless record cannot be staged by
# accident: fill it in before the first real upload, not during it.
# Each entry is {"name": "Family, Given", "affiliation": ..., "orcid": ...},
# orcid optional.
CREATORS = []

ENDPOINT = {
    "sandbox": "https://sandbox.zenodo.org/api",
    "zenodo": "https://zenodo.org/api",
}


def call(method, url, token, payload=None, body=None, length=None):
    headers = {"Authorization": "Bearer " + token}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    elif body is not None:
        data = body
        headers["Content-Type"] = "application/octet-stream"
        headers["Content-Length"] = str(length)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:800]
        sys.exit("HTTP %s on %s %s\n%s" % (e.code, method, url, detail))


def md5(path, chunk=1 << 22):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0


def benchmark_files():
    """The 2 GB derived corpus: what almost every user will actually download."""
    files = sorted(p for p in BUNDLE.iterdir() if p.is_file())
    files += sorted((BUNDLE / "shards").rglob("*.csv.gz"))
    return files


def raw_files():
    """The provenance layer. Every simulator table the corpus was built from."""
    return sorted(RAW.glob("campaign*/rx_ps*seed*.csv*"))


def code_files():
    """Not uploaded here. Zenodo archives a GitHub release on its own once the
    repository is switched on at zenodo.org/account/settings/github, which
    keeps the code record tied to a tag rather than to a manual upload."""
    return []


RECORDS = {
    "benchmark": (benchmark_files, "dataset"),
    "raw": (raw_files, "dataset"),
    "code": (code_files, "software"),
}


def metadata(record, upload_type):
    base = json.loads((BUNDLE / ".zenodo.json").read_text())
    meta = {
        "title": base["title"],
        "upload_type": upload_type,
        "description": base["description"],
        "version": base["version"],
        "license": base["license"],
        "keywords": base["keywords"],
        "access_right": "open",
        "creators": CREATORS,
        "prereserve_doi": True,
    }
    if record == "raw":
        meta["title"] = base["title"] + ": raw simulation layer"
        meta["description"] = (
            "The unaggregated simulator output behind the CV2X-IDS benchmark "
            "corpus: one row per received transport block, partitioned by seed "
            "and campaign. Most users want the benchmark record instead. This "
            "one exists so the windowing and the labels can be recomputed from "
            "source rather than trusted."
        )
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", required=True, choices=sorted(RECORDS))
    ap.add_argument("--target", default="sandbox", choices=sorted(ENDPOINT),
                    help="sandbox by default, because zenodo is irreversible")
    ap.add_argument("--deposition", type=int,
                    help="resume an existing draft instead of creating one")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be uploaded and stop")
    ap.add_argument("--token-file", type=Path,
                    help="read the token from this file instead of the "
                         "environment, so it never appears in a shell history "
                         "or a transcript. Default ~/.zenodo_token_<target>")
    args = ap.parse_args()

    lister, upload_type = RECORDS[args.record]
    files = lister()
    if not files:
        sys.exit("record %r has no files to upload. For 'code', switch the "
                 "repository on at zenodo.org/account/settings/github and cut "
                 "a GitHub release instead." % args.record)

    total = sum(p.stat().st_size for p in files)
    print("%s record: %d files, %s" % (args.record, len(files), human(total)))
    if args.dry_run:
        for p in files:
            print("   %10s  %s" % (human(p.stat().st_size), p.name))
        return

    if not CREATORS:
        sys.exit("CREATORS is empty. Zenodo will not accept a record without an "
                 "author list, and a record published with the wrong one cannot "
                 "be quietly fixed. Fill it in at the top of this file first.")

    default_file = Path.home() / (".zenodo_token_" + args.target)
    token_file = args.token_file or (default_file if default_file.exists() else None)
    if token_file:
        token = token_file.read_text().strip()
        print("token read from %s" % token_file)
    else:
        token = os.environ.get("ZENODO_TOKEN")
    if not token:
        sys.exit("no token. Write one to %s, or set ZENODO_TOKEN. Create it at "
                 % default_file +
                 "%s/account/settings/applications/tokens/new with the "
                 "deposit:write and deposit:actions scopes."
                 % ENDPOINT[args.target].replace("/api", ""))

    api = ENDPOINT[args.target]
    meta = metadata(args.record, upload_type)

    if args.deposition:
        dep = call("GET", "%s/deposit/depositions/%d" % (api, args.deposition), token)
        print("resuming draft %d" % dep["id"])
    else:
        dep = call("POST", api + "/deposit/depositions", token, payload={})
        print("created draft %d" % dep["id"])

    dep = call("PUT", "%s/deposit/depositions/%d" % (api, dep["id"]), token,
               payload={"metadata": meta})
    doi = dep["metadata"].get("prereserve_doi", {}).get("doi", "not reserved")
    print("reserved DOI %s" % doi)

    bucket = dep["links"]["bucket"]
    have = {f["filename"]: f.get("checksum", "").replace("md5:", "")
            for f in dep.get("files", [])}

    done = 0
    for i, path in enumerate(files, 1):
        size = path.stat().st_size
        if path.name in have and have[path.name] == md5(path):
            print("  [%3d/%d] skip     %-44s already uploaded" % (i, len(files), path.name))
            done += size
            continue
        print("  [%3d/%d] upload   %-44s %10s" % (i, len(files), path.name, human(size)),
              flush=True)
        with open(path, "rb") as fh:
            call("PUT", "%s/%s" % (bucket, path.name), token, body=fh, length=size)
        done += size
        print("           %s of %s" % (human(done), human(total)))

    url = "%s/uploads/%d" % (api.replace("/api", ""), dep["id"])
    print("\nstaged, not published.")
    print("  DOI reserved : %s" % doi)
    print("  draft        : %s" % url)
    print("\nReview it there and press Publish when the record should become "
          "public. Do not publish a named record while the paper is under "
          "double blind review.")


if __name__ == "__main__":
    main()
