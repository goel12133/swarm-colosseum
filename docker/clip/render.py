"""Runs inside the colosseum-clip container: page -> frames (headless Chromium) -> mp4.

    python /in/render.py FROM TO SPEED [gif]

Reads /in/page.html (the viewer with one replay embedded), writes /out/clip.mp4, and with
`gif` also /out/clip.gif (for READMEs and chat apps that won't play video inline).
"""
import base64
import re
import subprocess
import sys
import tempfile
from pathlib import Path

frm, to, speed = sys.argv[1:4]
url = f"file:///in/page.html#clip={frm},{to},{speed}"
dom = subprocess.run(
    ["chromium", "--headless", "--no-sandbox", "--disable-gpu", "--force-dark-mode",
     "--force-device-scale-factor=1", "--window-size=1000,1000", "--hide-scrollbars",
     "--virtual-time-budget=120000", "--dump-dom", url],
    capture_output=True, text=True, timeout=600).stdout
m = re.search(r'<textarea id="clipframes">(.*?)</textarea>', dom, re.S)
if not m or not m.group(1).strip():
    sys.exit("no frames came back from the page")
frames = [f for f in m.group(1).split("\n") if f.startswith("data:image/png;base64,")]
tmp = Path(tempfile.mkdtemp())
for i, f in enumerate(frames):
    (tmp / f"{i:05d}.png").write_bytes(base64.b64decode(f.split(",", 1)[1]))
# The viewer advances one step per 60 ms, so frames come in at 50/3 fps; output is 30 fps
# H.264 yuv420p with faststart, which plays inline on phones.
subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "50/3",
                "-i", str(tmp / "%05d.png"), "-vf", "fps=30,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-profile:v", "high", "-level", "4.0", "-movflags", "+faststart",
                "/out/clip.mp4"], check=True, timeout=600)
if sys.argv[4:5] == ["gif"]:
    # Half size, 15 fps and one shared 64-colour palette keep a full match at 4x a few MB;
    # the viewer's flat colours survive the palette without dithering noise.
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "50/3",
                    "-i", str(tmp / "%05d.png"), "-filter_complex",
                    "fps=15,scale=360:-1:flags=lanczos,split[a][b];"
                    "[a]palettegen=max_colors=64:stats_mode=diff[p];"
                    "[b][p]paletteuse=dither=none:diff_mode=rectangle",
                    "-loop", "0", "/out/clip.gif"], check=True, timeout=600)
print(f"{len(frames)} frames")
