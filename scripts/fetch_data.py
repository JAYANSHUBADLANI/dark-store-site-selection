"""Download the external datasets this project depends on.

Nothing here is committed to the repository. The population raster is fetched
into data/raw/ on first run and cached there afterwards.

The population source is the JRC Global Human Settlement Layer, taken as a
single 1000km Mollweide tile rather than the global mosaic. Bengaluru sits well
inside tile R8_C26, so 47 MB is fetched instead of several gigabytes. The tile
index is computed rather than hardcoded, so pointing this at another city is a
config change, see scripts/tile_index.py.

Run:  python scripts/fetch_data.py
"""

from __future__ import annotations

import argparse
import sys
import time
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.config import load_config, paths  # noqa: E402
from src.tiles import ghsl_tile_for_point, ghsl_tile_url  # noqa: E402


def download(url: str, destination: Path, chunk_bytes: int = 1 << 20) -> Path:
    """Stream a URL to disk, writing to a partial file and renaming on success."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print(
            f"  already present, skipping: {destination.name} "
            f"({destination.stat().st_size / 1e6:.0f} MB)"
        )
        return destination

    partial = destination.with_suffix(destination.suffix + ".partial")
    request = Request(url, headers={"User-Agent": "dark-store-site-selection/0.1"})

    started = time.time()
    with urlopen(request) as response, open(partial, "wb") as handle:
        total = int(response.headers.get("Content-Length", 0))
        written = 0
        while True:
            chunk = response.read(chunk_bytes)
            if not chunk:
                break
            handle.write(chunk)
            written += len(chunk)
            if total:
                print(
                    f"\r  {written/1e6:6.0f} / {total/1e6:.0f} MB "
                    f"({100.0 * written / total:5.1f}%)",
                    end="",
                    flush=True,
                )
    print()

    if total and written != total:
        partial.unlink(missing_ok=True)
        raise IOError(f"incomplete download: got {written} bytes, expected {total}")

    partial.rename(destination)
    print(
        f"  done in {time.time() - started:.0f}s "
        f"({destination.stat().st_size / 1e6 / max(time.time() - started, 1):.1f} MB/s)"
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-download even if the file is already cached",
    )
    args = parser.parse_args()

    cfg = load_config()
    raw_dir = paths(cfg)["raw"]

    lon, lat = cfg["city"]["reference_point"]
    tile = ghsl_tile_for_point(lon, lat)
    url = ghsl_tile_url(tile, cfg)
    archive = raw_dir / Path(url).name

    print("Population raster: JRC GHS-POP R2023A, 100m, epoch 2020, Mollweide")
    print(f"  city reference point: {lon}, {lat}")
    print(f"  resolved tile: {tile}")
    print(f"  source: {url}")

    if args.force:
        archive.unlink(missing_ok=True)

    download(url, archive)

    print("\nExtracting the GeoTIFF from the archive")
    with zipfile.ZipFile(archive) as zf:
        members = [n for n in zf.namelist() if n.lower().endswith(".tif")]
        if not members:
            raise IOError(f"no .tif inside {archive.name}")
        for member in members:
            target = raw_dir / Path(member).name
            if target.exists():
                print(f"  already extracted: {target.name}")
                continue
            with zf.open(member) as source, open(target, "wb") as handle:
                handle.write(source.read())
            print(f"  wrote {target.name} ({target.stat().st_size / 1e6:.0f} MB)")

    print(
        "\nThe OSM road network and boundary are pulled live by the pipeline and "
        "cached under data/interim/, so there is nothing to fetch for them here."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
