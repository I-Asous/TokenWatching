"""
Validates manifest.json and packages the browser extension into a zip.

Only files referenced by the manifest (and local scripts/styles/images referenced
by its HTML pages) are included, so the agents, dashboard, etc. never ship.

Usage: python scripts/package_extension.py [--check-version vX.Y.Z] [--out dist]
"""
import argparse
import json
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_KEYS = ("manifest_version", "name", "version")


class _RefParser(HTMLParser):
    """Collects local src/href references from an HTML page."""

    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("src", "href") and value and not re.match(r"^(\w+:|//|#)", value):
                self.refs.append(value.split("?")[0].split("#")[0])


def manifestRefs(manifest: dict) -> set[str]:
    """Returns every file path the manifest points at."""
    refs = set()

    def addIcons(icons):
        if isinstance(icons, str):
            refs.add(icons)
        elif isinstance(icons, dict):
            refs.update(icons.values())

    addIcons(manifest.get("icons"))
    for key in ("action", "browser_action", "page_action"):
        action = manifest.get(key, {})
        addIcons(action.get("default_icon"))
        if action.get("default_popup"):
            refs.add(action["default_popup"])
    background = manifest.get("background", {})
    if background.get("service_worker"):
        refs.add(background["service_worker"])
    refs.update(background.get("scripts", []))
    for script in manifest.get("content_scripts", []):
        refs.update(script.get("js", []))
        refs.update(script.get("css", []))
    for key in ("options_page", "devtools_page"):
        if manifest.get(key):
            refs.add(manifest[key])
    for key in ("options_ui", "side_panel"):
        page = manifest.get(key, {}).get("page") or manifest.get(key, {}).get("default_path")
        if page:
            refs.add(page)
    for entry in manifest.get("web_accessible_resources", []):
        resources = entry.get("resources", []) if isinstance(entry, dict) else [entry]
        refs.update(r for r in resources if "*" not in r)
    return {r.lstrip("/") for r in refs}


def collectFiles(manifest: dict) -> tuple[set[Path], list[str]]:
    """Resolves manifest refs plus nested HTML refs; returns (files, errors)."""
    files, errors = {ROOT / "manifest.json"}, []
    pending = [(ref, "manifest.json") for ref in manifestRefs(manifest)]
    while pending:
        ref, source = pending.pop()
        base = ROOT if source == "manifest.json" else (ROOT / source).parent
        path = (base / ref).resolve()
        if not path.is_relative_to(ROOT):
            errors.append(f"{source} references a file outside the repo: {ref}")
            continue
        if not path.is_file():
            errors.append(f"{source} references a missing file: {ref}")
            continue
        if path in files:
            continue
        files.add(path)
        if path.suffix == ".html":
            parser = _RefParser()
            parser.feed(path.read_text(encoding="utf-8"))
            rel = str(path.relative_to(ROOT))
            pending.extend((r, rel) for r in parser.refs)
    return files, errors


def main() -> int:
    """Entry point."""
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--check-version",
                      help="fail unless manifest version matches (e.g. a git tag)")
    args.add_argument("--out", default="dist", help="output directory for the zip")
    opts = args.parse_args()

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    errors = [f"manifest.json is missing '{k}'" for k in REQUIRED_KEYS if k not in manifest]
    if manifest.get("manifest_version") != 3:
        errors.append("manifest_version must be 3 (Chrome Web Store rejects MV2)")
    version = str(manifest.get("version", ""))
    if not re.fullmatch(r"\d+(\.\d+){0,3}", version):
        errors.append(f"version '{version}' must be 1-4 dot-separated integers")
    if opts.check_version and opts.check_version.lstrip("v") != version:
        errors.append(f"tag {opts.check_version} does not match manifest version {version}")

    files, fileErrors = collectFiles(manifest)
    errors.extend(fileErrors)
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1

    outDir = ROOT / opts.out
    outDir.mkdir(parents=True, exist_ok=True)
    zipPath = outDir / f"token-watching-{version}.zip"
    with zipfile.ZipFile(zipPath, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            bundle.write(path, path.relative_to(ROOT))
            print(f"  + {path.relative_to(ROOT)}")
    print(f"Packaged {len(files)} files -> {zipPath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
