"""Check actual CI exports and reject frozen/corrupt inputs before delivery.

Uses the existing media gate plus decoded mouth/hand regions. Region movement
does not establish phoneme-level lip synchronisation; that remains unverified.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, 'ci')
from verify_render import check

ROOT = Path('factory-presenter')
OUT = ROOT / 'out'
RAW = ROOT / 'assets/presenter-01.mp4'
FINAL = OUT / 'factory-presenter.mp4'


def frame(path, stamp, region=None):
    vf = 'scale=1920:1080'
    if region:
        vf += ',crop=' + region
    vf += ',scale=320:-2'
    data = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(stamp), '-i', str(path),
                                    '-frames:v', '1', '-vf', vf, '-f', 'image2pipe', '-vcodec', 'png', '-'], timeout=60)
    from io import BytesIO
    return Image.open(BytesIO(data)).convert('RGB')


def motion(path):
    results = {}
    for name, crop in [('mouth', '185:130:365:220'), ('hands', '650:280:70:720')]:
        samples = [np.asarray(frame(path, t, crop), dtype=np.float32) for t in (0.4, 1.4, 2.4, 3.4, 4.4, 5.4)]
        diffs = [float(np.mean(np.abs(a - b))) for a, b in zip(samples, samples[1:])]
        assert max(diffs) > 1.0, name + ' has no movement'
        results[name] = diffs
    return results


timing = json.loads((ROOT / 'build/timing.json').read_text())
assert timing['size'] == [1920, 1080] and len(timing['voice']) == 2
for voice, slot in zip(timing['voice'], timing['durations']):
    assert voice + 0.15 <= slot, 'voice would be cut at the shot boundary'
assert '-->' in FINAL.with_suffix('.srt').read_text()
probe = check(FINAL, 1920, 1080, 10.0, True)
actual_motion = motion(RAW)

frozen = OUT / 'frozen-negative-control.mp4'
still = OUT / 'negative-still.png'
frame(RAW, 0.4).save(still)
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-i', str(still), '-t', '6',
                '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(frozen)], check=True, timeout=120)
try:
    motion(frozen)
except AssertionError:
    motion_red = 'RED frozen person rejected; GREEN source mouth and hands move'
else:
    raise AssertionError('movement gate accepted a frozen person')
frozen.unlink(); still.unlink()

broken = OUT / 'truncated-negative-control.mp4'
broken.write_bytes(FINAL.read_bytes()[:64])
try:
    check(broken, 1920, 1080, 10.0, True)
except (AssertionError, subprocess.CalledProcessError, KeyError, StopIteration):
    decode_red = 'RED truncated MP4 rejected; GREEN final fully decoded'
else:
    raise AssertionError('decode gate accepted corrupt video')
broken.unlink()
check(FINAL, 1920, 1080, 10.0, True)
pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(FINAL), '-vn', '-ac', '1', '-ar', '16000',
                               '-f', 's16le', '-'], timeout=60)
samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
rms = float(np.sqrt(np.mean(samples ** 2)))
assert rms > 0.01, 'final audio is silent'

# Actual output frames, plus a six-frame close view of the moving face.
for file, path, times, crop in [
    ('final-review.jpg', FINAL, (0.5, 2, 4, 5.5, 7, 9.5), None),
    ('face-review.jpg', RAW, (0.4, 1.4, 2.4, 3.4, 4.4, 5.4), '430:450:230:0'),
]:
    thumbs = [ImageOps.contain(frame(path, t, crop), (640, 400)) for t in times]
    sheet = Image.new('RGB', (1920, 860), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, (thumb, t) in enumerate(zip(thumbs, times)):
        x, y = (i % 3) * 640, (i // 3) * 430
        sheet.paste(thumb, (x, y)); draw.text((x + 8, y + 402), f'{t:.1f}s', fill='black')
    sheet.save(OUT / file, quality=92)

receipt = {
    'test_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
    'upstream_sha': os.environ['SOURCE_SHA'], 'model_task_id': '455058692219309',
    'sha256': hashlib.sha256(FINAL.read_bytes()).hexdigest(), 'bytes': FINAL.stat().st_size,
    'raw_sha256': hashlib.sha256(RAW.read_bytes()).hexdigest(), 'probe': probe,
    'motion': actual_motion, 'motion_mutation': motion_red, 'decode_mutation': decode_red,
    'audio_rms': rms, 'voice_seconds': timing['voice'],
    'scope': 'real generated presenter movement, separate Edge TTS and native ecommerce assembly',
    'phoneme_lip_sync': 'NOT_VERIFIED', 'normal_speed_watch_and_listen': 'NOT_RUN',
    'clipcat_generation': 'NOT_RUN: browser sign-in required; no configured Clipcat API key',
}
(OUT / 'verification.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps({k: v for k, v in receipt.items() if k != 'probe'}, indent=2))
