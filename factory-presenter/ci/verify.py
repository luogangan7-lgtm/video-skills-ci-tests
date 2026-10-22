"""Check actual CI exports and reject frozen/corrupt inputs before delivery.

Uses the existing media gate, decoded mouth motion and source fidelity.
Contact and product anatomy still require independent actual-frame review;
movement alone does not establish contact or phoneme-level lip synchronisation.
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
RAW = ROOT / 'assets/presenter-fixed.mp4'
FINAL = OUT / 'factory-presenter.mp4'
TIMES = (0.2, 1.2, 2.4, 3.6, 4.8, 5.7)


def frame(path, stamp, region=None):
    vf = 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080'
    if region:
        vf += ',crop=' + region
    vf += ',scale=320:-2'
    data = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(stamp), '-i', str(path),
                                    '-frames:v', '1', '-vf', vf, '-f', 'image2pipe', '-vcodec', 'png', '-'], timeout=60)
    from io import BytesIO
    return Image.open(BytesIO(data)).convert('RGB')


def motion(path):
    results = {}
    for name, crop in [('mouth', '250:130:860:470'), ('grip', '500:520:250:420')]:
        # Area reduction suppresses H.264 block noise. A frozen lossy encode
        # must fail too: per-pixel codec noise is not presenter movement.
        samples = []
        for t in TIMES:
            img = frame(path, t, crop)
            img = img.resize((64, round(img.height * 64 / img.width)), Image.Resampling.BOX)
            samples.append(np.asarray(img, dtype=np.float32))
        diffs = [float(np.mean(np.abs(a - b))) for a, b in zip(samples, samples[1:])]
        print(json.dumps({'path': str(path), 'region': name, 'motion_diffs': diffs}), flush=True)
        # The presenter must speak; a safely held device need not move.
        # Keep grip measurements for review, without requiring a hand gesture.
        if name == 'mouth':
            assert max(diffs) > 3.0, name + ' has no meaningful movement above codec noise'
        results[name] = diffs
    return results


def source_fidelity(path):
    # Exclude the lower caption band. Detect card overlays and substituted scenes
    # against actual source pixels, rather than trusting storyboard declarations.
    diffs = []
    for t in TIMES:
        a = np.asarray(frame(path, t, '1920:850:0:0'), dtype=np.float32)
        b = np.asarray(frame(RAW, t, '1920:850:0:0'), dtype=np.float32)
        diff = float(np.mean(np.abs(a - b)))
        assert diff < 12.0, f'continuous handheld source replaced or overlaid at {t}s: {diff}'
        diffs.append(diff)
    return diffs


# Actual output frames, plus a six-frame close view of the moving face.
for file, path, times, crop in [
    ('final-review.jpg', FINAL, TIMES, None),
    ('face-review.jpg', RAW, TIMES, '700:700:650:0'),
    ('grip-review.jpg', FINAL, TIMES, '540:600:220:370'),
]:
    thumbs = [ImageOps.contain(frame(path, t, crop), (640, 400)) for t in times]
    sheet = Image.new('RGB', (1920, 860), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, (thumb, t) in enumerate(zip(thumbs, times)):
        x, y = (i % 3) * 640, (i // 3) * 430
        sheet.paste(thumb, (x, y)); draw.text((x + 8, y + 402), f'{t:.1f}s', fill='black')
    sheet.save(OUT / file, quality=92)


timing = json.loads((ROOT / 'build/timing.json').read_text())
assert timing['size'] == [1920, 1080] and len(timing['voice']) == 1
for voice, slot in zip(timing['voice'], timing['durations']):
    assert voice + 0.15 <= slot, 'voice would be cut at the shot boundary'
assert '-->' in FINAL.with_suffix('.srt').read_text()
probe = check(FINAL, 1920, 1080, 6.0, True)
actual_motion = motion(RAW)
final_motion = motion(FINAL)
fidelity = source_fidelity(FINAL)

frozen = OUT / 'frozen-negative-control.mp4'
still = OUT / 'negative-still.png'
frame(RAW, 0.4).save(still)
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-loop', '1', '-i', str(still), '-t', '6',
                '-r', '30', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(frozen)], check=True, timeout=120)
try:
    motion(frozen)
except AssertionError:
    motion_red = 'RED frozen person rejected; GREEN source and final mouth move; grip is measured without requiring gestures'
else:
    raise AssertionError('movement gate accepted a frozen person')
frozen.unlink(); still.unlink()

card = OUT / 'sidecard-negative-control.mp4'
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(FINAL), '-vf',
                'drawbox=x=1250:y=65:w=590:h=880:color=white:t=fill', '-an',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(card)],
               check=True, timeout=120)
try:
    source_fidelity(card)
except AssertionError:
    layout_red = 'RED encoded sidecard overlay rejected; GREEN continuous handheld source preserved'
else:
    raise AssertionError('source fidelity gate accepted a sidecard overlay')
card.unlink()
source_fidelity(FINAL)

broken = OUT / 'truncated-negative-control.mp4'
broken.write_bytes(FINAL.read_bytes()[:64])
try:
    check(broken, 1920, 1080, 6.0, True)
except (AssertionError, subprocess.CalledProcessError, KeyError, StopIteration):
    decode_red = 'RED truncated MP4 rejected; GREEN final fully decoded'
else:
    raise AssertionError('decode gate accepted corrupt video')
broken.unlink()
check(FINAL, 1920, 1080, 6.0, True)
pcm = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(FINAL), '-vn', '-ac', '1', '-ar', '16000',
                               '-f', 's16le', '-'], timeout=60)
samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
rms = float(np.sqrt(np.mean(samples ** 2)))
assert rms > 0.01, 'final audio is silent'


receipt = {
    'test_sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
    'upstream_sha': os.environ['SOURCE_SHA'], 'model_task_id': '455070782542247',
    'sha256': hashlib.sha256(FINAL.read_bytes()).hexdigest(), 'bytes': FINAL.stat().st_size,
    'raw_sha256': hashlib.sha256(RAW.read_bytes()).hexdigest(), 'probe': probe,
    'motion': actual_motion, 'motion_mutation': motion_red, 'decode_mutation': decode_red,
    'final_motion': final_motion, 'source_fidelity_mae': fidelity, 'layout_mutation': layout_red,
    'audio_rms': rms, 'voice_seconds': timing['voice'],
    'scope': 'one continuous generated handheld source; separate Edge TTS; native ecommerce assembly',
    'source_resolution': 'native 1080P, six seconds',
    'handheld_contact_and_anatomy': 'REQUIRES_INDEPENDENT_ACTUAL_FRAME_REVIEW',
    'phoneme_lip_sync': 'NOT_VERIFIED', 'normal_speed_watch_and_listen': 'NOT_RUN',
    'clipcat_generation': 'NOT_RUN: browser sign-in required; no configured Clipcat API key',
}
(OUT / 'verification.json').write_text(json.dumps(receipt, indent=2))
print(json.dumps({k: v for k, v in receipt.items() if k != 'probe'}, indent=2))
