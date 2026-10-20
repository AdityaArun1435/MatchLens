"""Assemble PNG frames (named 000123.png where the number is the capture time in ms) into one GIF.

    python scripts/make_gif.py frames_dir docs/screenshots/live.gif --width 800
"""
import argparse
from pathlib import Path

from PIL import Image


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("frames", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--width", type=int, default=800)
    p.add_argument("--colors", type=int, default=192)
    args = p.parse_args()

    files = sorted(args.frames.glob("*.png"))
    times = [int(f.stem) for f in files]
    frames = []
    for f in files:
        im = Image.open(f).convert("RGB")
        im = im.resize((args.width, round(im.height * args.width / im.width)), Image.LANCZOS)
        frames.append(im.quantize(colors=args.colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    durations = [max(40, min(600, b - a)) for a, b in zip(times, times[1:])] + [1500]  # hold the last frame
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(args.out, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"{len(frames)} frames, {sum(durations) / 1000:.1f}s, {args.out.stat().st_size / 1e6:.2f} MB -> {args.out}")


if __name__ == "__main__":
    main()
