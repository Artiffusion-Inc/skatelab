# Test Video Asset

This directory should contain `test_video.mp4` for Maestro E2E tests.

## Requirements

- Format: MP4 (H.264, AAC audio)
- Duration: 5-10 seconds
- Size: < 5 MB
- Content: A figure skating element (axel jump) for realistic processing

## How to create

```bash
# From an existing session video, extract a short clip:
ffmpeg -i source_video.mp4 -ss 0:00 -t 0:08 -c:v libx264 -c:a aac -b:v 1M -s 640x480 \
  mobile/e2e/maestro/assets/test_video.mp4

# Or create a synthetic test video:
ffmpeg -f lavfi -i "color=c=blue:s=640x480:d=1:r=30" -c:v libx264 -c:a aac -b:v 1M -t 8 \
  mobile/e2e/maestro/assets/test_video.mp4
```

This file should be committed directly to git (no LFS needed at <5MB).