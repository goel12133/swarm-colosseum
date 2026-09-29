# Renderer for replay clips: headless Chromium drives the real viewer, ffmpeg encodes.
# Tools only -- the render script and the page are mounted read-only at run time, and the
# container runs with --network none, as a non-root user.
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends chromium ffmpeg fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 clip
USER clip
WORKDIR /home/clip
