"""Draw the Punjab map used on slide 5.

The first version plotted 22 district dots in an empty rectangle, which read as
scatter rather than as a map — there was nothing to tell you it was Punjab.

The fix uses data already in the database: 1,606 monitoring stations with
coordinates. Their point cloud traces the state's real outline, so the shape is
measured rather than drawn. It also puts the size of the network on the slide,
which the numbers alone never showed.

Written as a PNG because 1,606 PowerPoint shapes would bloat the file; the
district markers stay native shapes so their colours remain editable.
"""

from __future__ import annotations

import json
import pathlib

from PIL import Image, ImageDraw, ImageFilter

HERE = pathlib.Path(__file__).parent
OUT = HERE / "punjab.png"

# Rendered large, then placed at ~4.6 in wide — about 300 dpi on the slide.
W, H = 1400, 1180
PAD = 70

PAPER = (244, 242, 238)
CLOUD = (206, 214, 214)
CLOUD_EDGE = (176, 190, 192)


def main() -> None:
    stations = json.loads((HERE / "stations.json").read_text())
    lats = [s["lat"] for s in stations]
    lons = [s["lon"] for s in stations]
    lat0, lat1 = min(lats), max(lats)
    lon0, lon1 = min(lons), max(lons)

    # Equirectangular with a latitude correction, so Punjab is not stretched.
    import math
    kx = math.cos(math.radians((lat0 + lat1) / 2))
    span_x = (lon1 - lon0) * kx
    span_y = lat1 - lat0
    scale = min((W - 2 * PAD) / span_x, (H - 2 * PAD) / span_y)
    ox = (W - span_x * scale) / 2
    oy = (H - span_y * scale) / 2

    def project(lat, lon):
        x = ox + (lon - lon0) * kx * scale
        y = oy + (lat1 - lat) * scale
        return x, y

    # --- the cloud, blurred into a landmass then re-sharpened ---
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    for s in stations:
        x, y = project(s["lat"], s["lon"])
        md.ellipse([x - 17, y - 17, x + 17, y + 17], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(11))
    mask = mask.point(lambda v: 255 if v > 96 else 0)

    img = Image.new("RGB", (W, H), PAPER)
    land = Image.new("RGB", (W, H), CLOUD)
    img.paste(land, (0, 0), mask)

    # a soft edge on the landmass
    edge = mask.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(1.6))
    img.paste(Image.new("RGB", (W, H), CLOUD_EDGE), (0, 0), edge.point(lambda v: min(v * 3, 255)))

    # every station, faintly, over the landmass
    d = ImageDraw.Draw(img, "RGBA")
    for s in stations:
        x, y = project(s["lat"], s["lon"])
        d.ellipse([x - 3.2, y - 3.2, x + 3.2, y + 3.2], fill=(96, 122, 128, 150))

    # Crop to the landmass. Untrimmed, the state sat inside a wide margin, so
    # it rendered small on the slide and the legend fell over empty image.
    bbox = mask.getbbox()
    m = 18
    crop = (max(bbox[0] - m, 0), max(bbox[1] - m, 0),
            min(bbox[2] + m, W), min(bbox[3] + m, H))
    img = img.crop(crop)
    img.save(OUT)

    # hand the projection back so the slide can place district markers on it,
    # shifted by the crop so both agree on where a coordinate lands
    meta = {"lat0": lat0, "lat1": lat1, "lon0": lon0, "lon1": lon1,
            "kx": kx, "scale": scale,
            "ox": ox - crop[0], "oy": oy - crop[1],
            "w": crop[2] - crop[0], "h": crop[3] - crop[1]}
    (HERE / "punjab.json").write_text(json.dumps(meta))
    print(f"wrote {OUT}  ({W}x{H}, {len(stations)} stations)")


if __name__ == "__main__":
    main()
