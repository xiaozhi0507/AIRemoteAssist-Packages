"""Reproduce the pinned Windows bundle from official Node, ripgrep and Playwright distributions."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import zipfile

HERE = Path(__file__).resolve().parent
WORK = Path(sys.argv[1]).resolve()
WORK.mkdir(parents=True, exist_ok=True)
VERSIONS = json.loads((HERE / "packages.json").read_text(encoding="utf-8-sig"))
LOCK = json.loads((HERE / "package-lock.json").read_text(encoding="utf-8-sig"))
PLAYWRIGHT = LOCK["packages"]["node_modules/playwright"]["version"]
BROWSER_DIR = WORK / "browsers"
ROOT = "Playwright-" + PLAYWRIGHT

def fetch(url, filename, digest, algorithm="sha256"):
    path = WORK / filename
    if not path.exists():
        subprocess.run(["curl.exe", "--fail", "--location", "--retry", "3", "--output", str(path), url], check=True)
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, algorithm).hexdigest()
    if actual.lower() != digest.lower():
        raise ValueError("Unexpected digest: " + filename)
    return path

def add(archive, name, source):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError(name)
    with archive.open(name, "w", force_zip64=True) as target:
        shutil.copyfileobj(source, target, 1024 * 1024)

def build():
    output = WORK / VERSIONS["OfflineDevTools"]["FileName"]
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as out:
        for product in ("Node", "Ripgrep"):
            item = VERSIONS[product]
            path = fetch(item["Url"], product + ".zip", item["Sha256"])
            with zipfile.ZipFile(path) as source:
                for entry in source.infolist():
                    if entry.is_dir():
                        continue
                    name = entry.filename
                    if product == "Ripgrep":
                        name = "ripgrep-" + item["Version"] + "/" + name.split("/", 1)[1]
                    with source.open(entry) as stream:
                        add(out, name, stream)
        for module in ("playwright", "playwright-core"):
            key = "node_modules/" + module
            spec = LOCK["packages"][key]
            expected = base64.b64decode(spec["integrity"].removeprefix("sha512-")).hex()
            path = fetch(spec["resolved"], module + ".tgz", expected, "sha512")
            with tarfile.open(path) as source:
                for entry in source:
                    if entry.isdir():
                        continue
                    if not entry.isfile() or not entry.name.startswith("package/"):
                        raise ValueError(entry.name)
                    with source.extractfile(entry) as stream:
                        add(out, ROOT + "/" + key + "/" + entry.name[8:], stream)
        # ZIP timestamps and file attributes are included in the published archive hash.
        metadata = json.loads((HERE / "browser-metadata.json").read_text(encoding="utf-8"))
        for name, timestamp, attributes in metadata:
            entry = zipfile.ZipInfo(ROOT + "/browsers/" + name, tuple(timestamp))
            entry.external_attr = attributes
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.compress_level = 5
            with (BROWSER_DIR / name).open("rb") as stream, out.open(entry, "w") as target:
                shutil.copyfileobj(stream, target, 1024 * 1024)
    with output.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != VERSIONS["OfflineDevTools"]["Sha256"].lower():
            raise ValueError("Development bundle SHA-256 differs from the original.")
    print(output)

if __name__ == "__main__":
    build()
