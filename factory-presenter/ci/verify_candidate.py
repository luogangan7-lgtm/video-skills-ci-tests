"""Bind imported CI media to unchanged generation code before evaluating it.

Called only by factory-sync-acceptance.yml. Reads the pinned generation commit,
checks exported hashes and extracts the delivered mix as evaluation audio.
No second narration is generated and no media is processed on local machines.
"""
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import urllib.request

from PIL import Image, ImageDraw, ImageOps

ROOT = Path('factory-presenter')
OUT = ROOT / 'out'
WORK = ROOT / 'build/lipsync'
GENERATION = 'a012a877ae13c58a170c70df9dffa261066a930b'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frame(path, stamp, region=None):
    vf = f'crop={region}' if region else 'null'
    data = subprocess.check_output(['ffmpeg', '-v', 'error', '-ss', str(stamp), '-i', str(path),
                                    '-vf', vf, '-frames:v', '1', '-f', 'image2pipe',
                                    '-vcodec', 'png', '-'], timeout=60)
    return Image.open(BytesIO(data)).convert('RGB')


def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true'
    WORK.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((OUT / 'lipsync-receipt.json').read_text())
    assert receipt['test_sha'] == GENERATION and receipt['run_id'] == '40081026748'
    assert digest(OUT / 'factory-presenter-fixed.mp4') == receipt['final_sha256']
    assert digest(OUT / 'lipsync-master.mp4') == receipt['master_sha256']
    baseline = json.loads((OUT / 'verification.json').read_text())
    assert baseline['test_sha'] == GENERATION
    assert digest(OUT / 'factory-presenter.mp4') == baseline['sha256']
    url = f'https://raw.githubusercontent.com/luogangan7-lgtm/video-skills-ci-tests/{GENERATION}/factory-presenter/ci/lipsync.py'
    with urllib.request.urlopen(url, timeout=30) as response:
        generation_code = response.read()
    generation_hash = hashlib.sha256(generation_code).hexdigest()
    assert generation_hash == digest(ROOT / 'ci/lipsync.py'), 'render code changed: regenerate the candidate'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(OUT / 'factory-presenter-fixed.mp4'),
                    '-vn', '-ac', '1', '-ar', '16000', '-t', '6',
                    str(WORK / 'evaluation.wav')], check=True, timeout=60)
    evidence = dict(evaluation_sha=os.environ['GITHUB_SHA'], evaluation_run=os.environ['GITHUB_RUN_ID'],
                    generation_sha=GENERATION, generation_run='40081026748',
                    generation_code_sha256=generation_hash, generation_code_unchanged=True,
                    final_sha256=receipt['final_sha256'],
                    evaluation_audio_sha256=digest(WORK / 'evaluation.wav'),
                    evaluation_audio='exact delivered AAC decoded to mono16k, includes original music',
                    original_driving_voice_sha256=receipt['driving_voice_sha256'])
    (OUT / 'candidate-provenance.json').write_text(json.dumps(evidence, indent=2))
    for name, videos, stamps, region in [
        ('final-export-review.jpg', [OUT / 'factory-presenter-fixed.mp4']*6, [.2,1.2,2.4,3.6,4.8,5.7], None),
        ('product-before-after.jpg', [OUT / 'same-crop-baseline.mp4']*3+[OUT / 'factory-presenter-fixed.mp4']*3,
         [.2,2.4,4.8]*2, '650:650:140:380'),
        ('face-before-after.jpg', [OUT / 'factory-presenter.mp4']*3+[OUT / 'lipsync-master.mp4']*3,
         [.4,1.6,3.2]*2, '450:520:740:150'),
    ]:
        sheet = Image.new('RGB', (1800, 880), 'white')
        draw = ImageDraw.Draw(sheet)
        for j, (video, stamp) in enumerate(zip(videos, stamps)):
            im = ImageOps.contain(frame(video, stamp, region), (600, 410))
            x, y = j%3*600, j//3*440
            sheet.paste(im, (x, y))
            draw.text((x+5, y+415), f'{video.name} {stamp:.2f}s', fill='black')
        sheet.save(OUT / name, quality=95)
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
