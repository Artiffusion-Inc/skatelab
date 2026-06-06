# E2E Test Resources

## test_video.mp4

Required by `gallery-upload.yaml` via Maestro's `addMedia` command.

**Spec:** Short (~3s) MP4 video, H.264 codec, minimal resolution (e.g. 480p).

**How to create:**

```bash
# Using ffmpeg (install via brew install ffmpeg)
ffmpeg -f lavfi -i testsrc=duration=3:size=640x480:rate=30 \
       -f lavfi -i sine=frequency=440:duration=3 \
       -c:v libx264 -c:a aac -y test_video.mp4
```

**How to add:**

Place `test_video.mp4` in this directory. The file is not committed to git (listed in `.gitignore`).

## CI

For CI, the test video must be checked into LFS or stored as a workflow artifact. Add to `.gitattributes`:

```
mobile/e2e/maestro/resources/test_video.mp4 filter=lfs diff=lfs merge=lfs -text
```