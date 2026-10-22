# Video skill evaluation — GitHub CI only

This isolated test repository evaluates the public upstream skills at exact commits.
No production assets, credentials or paid model calls are used. No local project execution.

| Source | Commit | Native test |
|---|---|---|
| Clipcat-ai/clipcat-skill | 7888594dfb5fea29e40a50077d51a7dade97f66f | Documentation/dependency audit only: video creation uses hosted video models and Clipcat API credentials. No generation submitted. |
| xianyu110/ecommerce-video-skills | 96c49b349b7d975bda8f05ce6669c1d33500c269 | Unmodified `scripts/assemble.py`, supplied fictional AURA bottle demo, offline and English Edge TTS routes. |
| iart-ai/ecommerce-video-skills | 2bd0dd19c9b2df5230f5d8f7453861b9681e49b4 | Exact FFmpeg zoompan command from photo-slideshow/references/ken-burns.md, synthetic test chart and native probe script. This is a documented primitive test, not a complete Remotion product-demo/promo implementation. |

Acceptance: native render; actual H.264/yuv420p at the expected resolution, 30fps and duration;
AAC/48kHz/stereo and SRT/timing for assembled examples; full decode; reject a truncated MP4;
changing within-shot frames; source and test SHA, run ID and output SHA256 in the artifact.
Visual contact sheets are reviewed separately. Frame changes are photo/camera motion, not generated human action.

All rendering and checks run on GitHub-hosted runners. The voice route uses Microsoft's online Edge TTS;
the offline route uses neither TTS nor a video model. A failed external voice request stays a failed test.
Artifacts expire after seven days. Upstream sources are never modified.
