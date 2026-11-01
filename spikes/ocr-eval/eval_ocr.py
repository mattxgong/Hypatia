"""Compare local OCR engines on study-material photos (Phase 10, W3).

    python eval_ocr.py generate samples/synthetic   # make labelled test images
    python eval_ocr.py run samples/synthetic        # score every engine found
    python eval_ocr.py run samples/real             # your own photos

`run` reads every .jpg/.jpeg/.png/.webp in the folder. A same-named .txt holds
the expected text; with it the image is scored (character and word error
rate), without it the OCR text is only printed, to judge by eye.

Images go through the pipeline planned for ingestion first: EXIF rotation,
then a downscale to a 2500 px long edge.

Engines: RapidOCR (`pip install rapidocr onnxruntime`) and Tesseract (the
`tesseract` binary on PATH or in TESSERACT_CMD). Missing engines are skipped.
"""

from __future__ import annotations

import csv
import io
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

MAX_EDGE = 2500
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
FONT_DIRS = [
    Path("C:/Windows/Fonts"),
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
    Path("/usr/share/fonts"),
]

# Lecture-style text: definitions, numbers, symbols and a formula or two.
TEXTS = [
    (
        "Photosynthesis converts light energy into chemical energy. The light reactions "
        "take place in the thylakoid membranes and produce ATP and NADPH."
    ),
    (
        "Newton's second law: F = ma. A 2 kg mass accelerating at 3 m/s^2 needs a net "
        "force of 6 N. Momentum p = mv is conserved in a closed system."
    ),
    (
        "Week 7 - Supply and Demand. When the price rises, quantity demanded falls. "
        "Elasticity = % change in quantity / % change in price."
    ),
    (
        "Mitochondria are the site of aerobic respiration. Glycolysis happens in the "
        "cytoplasm; the Krebs cycle happens in the matrix."
    ),
    (
        "Big-O notation: binary search runs in O(log n) time, merge sort in O(n log n), "
        "and bubble sort in O(n^2) in the worst case."
    ),
    (
        "The French Revolution began in 1789. Causes: debt from wars, food shortages, and "
        "resentment of the privileges held by the clergy and nobility."
    ),
    (
        "Midterm review: chapters 3-6. Bring a calculator. Exam is on Thursday, 14 Nov, "
        "in room B-204 from 10:00 to 11:30."
    ),
    (
        "An enzyme lowers the activation energy of a reaction. Its activity depends on "
        "temperature, pH, and substrate concentration."
    ),
]


def _font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for name in names:
        for folder in FONT_DIRS:
            for path in folder.rglob(name) if folder.exists() else []:
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def _page(
    text: str,
    font: ImageFont.FreeTypeFont,
    size: tuple[int, int],
    ink: tuple[int, int, int],
    paper: tuple[int, int, int],
    wrap: int,
) -> Image.Image:
    image = Image.new("RGB", size, paper)
    draw = ImageDraw.Draw(image)
    y = size[1] // 10
    for line in textwrap.wrap(text, wrap):
        draw.text((size[0] // 12, y), line, font=font, fill=ink)
        y += int(font.size * 1.5)
    return image


def _lighting(image: Image.Image, strength: float) -> Image.Image:
    """Darken one corner, like a room light falling off across a board."""
    w, h = image.size
    mask = Image.linear_gradient("L").rotate(35, expand=True).resize((w, h))
    shade = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(shade, image, mask.point(lambda v: int(v * strength)))


def _noise(image: Image.Image, amount: int, rng: random.Random) -> Image.Image:
    noise = Image.effect_noise(image.size, amount).convert("RGB")
    return Image.blend(image, noise, 0.12 if amount else 0)


def _perspective(image: Image.Image, skew: float) -> Image.Image:
    """A page photographed from below and to one side."""
    w, h = image.size
    dx, dy = w * skew, h * skew * 0.6
    # Where the output's upper-left, lower-left, lower-right and upper-right
    # corners sample the input. Outside the page shows as the background.
    quad = (-dx, -dy, -dx * 0.3, h + dy * 0.3, w + dx * 0.2, h, w + dx, -dy * 0.2)
    return image.transform(
        (w, h), Image.Transform.QUAD, quad, Image.Resampling.BICUBIC, fillcolor=(90, 80, 70)
    )


def _jpeg(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")


def _cases() -> list[tuple[str, Callable[[random.Random], tuple[Image.Image, str]]]]:
    print_fonts = ["times.ttf", "Times New Roman.ttf", "DejaVuSerif.ttf"]
    sans = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]
    marker = ["comic.ttf", "Comic Sans MS.ttf"]
    hand = ["Inkfree.ttf", "segoepr.ttf"]
    mono = ["consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf"]

    def handout(t: str, size: int = 34) -> Image.Image:
        return _page(t, _font(print_fonts, size), (1700, 1100), (20, 20, 20), (250, 250, 245), 70)

    def slide(t: str) -> Image.Image:
        return _page(t, _font(sans, 64), (1920, 1080), (255, 255, 255), (25, 45, 110), 42)

    def board(t: str, font: list[str]) -> Image.Image:
        return _page(t, _font(font, 60), (2000, 1200), (30, 50, 140), (238, 240, 236), 46)

    def case(build: Callable[[str, random.Random], Image.Image], text: str):
        return lambda rng: (build(text, rng), text)

    t = TEXTS
    return [
        ("handout_clean", case(lambda s, r: handout(s), t[0])),
        ("handout_small_text", case(lambda s, r: handout(s, 22), t[6])),
        ("handout_jpeg_q35", case(lambda s, r: _jpeg(handout(s), 35), t[3])),
        ("handout_angled", case(lambda s, r: _jpeg(_perspective(handout(s), 0.12), 80), t[1])),
        (
            "handout_angled_shadow",
            case(lambda s, r: _jpeg(_lighting(_perspective(handout(s), 0.18), 0.6), 75), t[7]),
        ),
        (
            "handout_skew_4deg",
            case(lambda s, r: handout(s).rotate(4, expand=True, fillcolor="gray"), t[5]),
        ),
        ("handout_blur", case(lambda s, r: handout(s).filter(ImageFilter.GaussianBlur(2.2)), t[2])),
        ("slide_clean", case(lambda s, r: slide(s), t[4])),
        (
            "slide_projector_photo",
            case(
                lambda s, r: _jpeg(
                    _noise(
                        _perspective(slide(s), 0.08).filter(ImageFilter.GaussianBlur(1.6)), 40, r
                    ),
                    70,
                ),
                t[1],
            ),
        ),
        ("whiteboard_marker", case(lambda s, r: _lighting(board(s, marker), 0.35), t[2])),
        (
            "whiteboard_marker_photo",
            case(
                lambda s, r: _jpeg(
                    _noise(_perspective(_lighting(board(s, marker), 0.45), 0.1), 30, r), 70
                ),
                t[0],
            ),
        ),
        ("handwriting_inkfree", case(lambda s, r: board(s, hand), t[3])),
        (
            "handwriting_photo",
            case(lambda s, r: _jpeg(_perspective(_lighting(board(s, hand), 0.4), 0.1), 75), t[6]),
        ),
        (
            "code_listing",
            case(
                lambda s, r: _page(s, _font(mono, 30), (1700, 900), (0, 0, 0), (255, 255, 255), 72),
                t[4],
            ),
        ),
        (
            "low_light_noisy",
            case(lambda s, r: _jpeg(_noise(_lighting(handout(s), 0.8), 60, r), 60), t[5]),
        ),
        ("sideways_exif", case(lambda s, r: handout(s), t[7])),
    ]


def generate(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    for name, build in _cases():
        image, text = build(rng)
        path = folder / f"{name}.jpg"
        if name == "sideways_exif":
            # Stored on its side with an EXIF tag saying so, as phones do.
            exif = Image.Exif()
            exif[0x0112] = 6  # rotate 90 CW to display
            image.rotate(90, expand=True).save(path, quality=92, exif=exif)
        else:
            image.save(path, quality=92)
        path.with_suffix(".txt").write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {len(_cases())} labelled images to {folder}")


def prepare(path: Path) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    return image


def _rapidocr() -> Callable[[Image.Image], str] | None:
    try:
        from rapidocr import RapidOCR
    except ImportError:
        return None
    engine = RapidOCR()

    def run(image: Image.Image) -> str:
        result = engine(image)
        return "\n".join(result.txts or ())

    return run


def _tesseract() -> Callable[[Image.Image], str] | None:
    command = os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
    if not command:
        return None

    def run(image: Image.Image) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "page.png"
            image.save(src)
            done = subprocess.run(
                [command, str(src), "stdout", "-l", "eng", "--psm", "3"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        return done.stdout

    return run


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _edit_distance(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def error_rates(expected: str, actual: str) -> tuple[float, float]:
    """Character and word error rates; 0 is perfect, and above 1 is possible."""
    exp, act = normalize(expected), normalize(actual)
    cer = _edit_distance(list(exp), list(act)) / max(len(exp), 1)
    wer = _edit_distance(exp.split(), act.split()) / max(len(exp.split()), 1)
    return cer, wer


def run(folder: Path) -> None:
    engines = {name: make() for name, make in (("rapidocr", _rapidocr), ("tesseract", _tesseract))}
    missing = [name for name, engine in engines.items() if engine is None]
    if missing:
        print(f"Skipping (not installed): {', '.join(missing)}")
    active = {name: engine for name, engine in engines.items() if engine is not None}
    if not active:
        sys.exit("No OCR engine available.")

    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    rows = []
    for path in images:
        image = prepare(path)
        label = path.with_suffix(".txt")
        expected = label.read_text(encoding="utf-8") if label.exists() else None
        for name, engine in active.items():
            start = time.perf_counter()
            text = engine(image)
            seconds = time.perf_counter() - start
            row = {"image": path.name, "engine": name, "seconds": round(seconds, 2)}
            if expected is None:
                print(f"\n--- {path.name} [{name}, {seconds:.1f}s]\n{text.strip()}")
            else:
                cer, wer = error_rates(expected, text)
                row |= {"cer": round(cer, 3), "wer": round(wer, 3)}
            row["text"] = normalize(text)
            rows.append(row)

    out = folder / "results.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, ["image", "engine", "seconds", "cer", "wer", "text"])
        writer.writeheader()
        writer.writerows(rows)

    scored = [r for r in rows if "cer" in r]
    if scored:
        print(f"\n{'image':28} " + "  ".join(f"{n:>18}" for n in active))
        print(f"{'':28} " + "  ".join(f"{'CER   WER   sec':>18}" for _ in active))
        for path in images:
            cells = []
            for name in active:
                r = next(
                    (r for r in scored if r["image"] == path.name and r["engine"] == name), None
                )
                cells.append(
                    f"{r['cer']:5.3f} {r['wer']:5.3f} {r['seconds']:5.2f}" if r else " " * 18
                )
            if any(c.strip() for c in cells):
                print(f"{path.stem:28} " + "  ".join(f"{c:>18}" for c in cells))
        for name in active:
            mine = [r for r in scored if r["engine"] == name]
            cer = sum(r["cer"] for r in mine) / len(mine)
            wer = sum(r["wer"] for r in mine) / len(mine)
            sec = sum(r["seconds"] for r in mine) / len(mine)
            print(f"mean {name:23} CER {cer:.3f}  WER {wer:.3f}  {sec:.2f}s/image")
    print(f"\nFull output: {out}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("generate", "run"):
        sys.exit(__doc__)
    {"generate": generate, "run": run}[sys.argv[1]](Path(sys.argv[2]))
