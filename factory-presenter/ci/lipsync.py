"""Audio-drive the existing face on CI; never synthesize the held product.

Called by factory-lipsync.yml after the pinned ecommerce native assembler.
Uses unchanged MuseTalk VAE/UNet/audio modules, CPU float32, pinned MIT models.
Only an elliptical lower-face mask is composited; source frames remain on disk.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np
import torch
from huggingface_hub import hf_hub_download
from PIL import Image, ImageDraw, ImageOps
from transformers import WhisperModel

sys.path.insert(0, str(Path('musetalk-upstream').resolve()))
from musetalk.models.vae import VAE
from musetalk.models.unet import UNet, PositionalEncoding
from musetalk.utils.audio_processor import AudioProcessor

ROOT = Path('factory-presenter')
OUT = ROOT / 'out'
WORK = ROOT / 'build/lipsync'
WORK.mkdir(parents=True, exist_ok=True)
MODELS = WORK / 'models'
FPS, COUNT = 30, 180
CROP = (192, 0, 1536, 864)
FACE = (740, 150, 1190, 670)


def run(args):
    subprocess.run(args, check=True, timeout=180)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def download_models():
    specs = [
        ('TMElyralab/MuseTalk', '2bcb936e2fddb4d86db4c62fd45b387d0c061571',
         ['musetalkV15/musetalk.json', 'musetalkV15/unet.pth'], 'musetalk'),
        ('stabilityai/sd-vae-ft-mse', '31f26fdeee1355a5c34592e401dd41e45d25a493',
         ['config.json', 'diffusion_pytorch_model.bin'], 'vae'),
        ('openai/whisper-tiny', '169d4a4341b33bc18d8881c4b69c2e104e1cc0af',
         ['config.json', 'pytorch_model.bin', 'preprocessor_config.json'], 'whisper'),
    ]
    receipts = []
    for repo, revision, files, name in specs:
        for file in files:
            path = hf_hub_download(repo, file, revision=revision, local_dir=str(MODELS / name))
            receipts.append(dict(repo=repo, revision=revision, file=file, sha256=digest(path), bytes=Path(path).stat().st_size))
    (OUT / 'model-receipts.json').write_text(json.dumps(receipts, indent=2))


def prepare():
    # The native assembler inserts exactly 150ms silence before its voice.
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(ROOT / 'build/tts/l00.wav'),
         '-af', 'adelay=150:all=1,apad', '-t', '6', '-ar', '16000', '-ac', '1', str(WORK / 'drive.wav')])
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(ROOT / 'build/video_noaudio.mp4'),
         '-vf', 'fps=30,tpad=stop_mode=clone:stop_duration=0.2', '-t', '6', str(WORK / 'source-%03d.png')])
    assert len(list(WORK.glob('source-*.png'))) == COUNT


def contact_sheet(paths, name, region=None):
    sheet = Image.new('RGB', (1800, 800), 'white')
    draw = ImageDraw.Draw(sheet)
    for j, i in enumerate([6, 36, 72, 108, 144, 171]):
        im = Image.open(paths(i)).convert('RGB')
        if region:
            im = im.crop(region)
        im = ImageOps.contain(im, (600, 370))
        x, y = j % 3 * 600, j // 3 * 400
        sheet.paste(im, (x, y)); draw.text((x+5, y+375), f'{i/FPS:.2f}s', fill='black')
    sheet.save(OUT / name, quality=95)


@torch.inference_mode()
def main():
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'CI execution required'
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    torch.manual_seed(24024)
    started = time.monotonic()
    download_models()
    prepare()
    device = torch.device('cpu')
    vae = VAE(model_path=str(MODELS / 'vae'), use_float16=False)
    unet = UNet(str(MODELS / 'musetalk/musetalkV15/musetalk.json'),
                str(MODELS / 'musetalk/musetalkV15/unet.pth'), device=device)
    vae.vae.eval(); unet.model.eval()
    pe = PositionalEncoding(d_model=384).eval()
    whisper = WhisperModel.from_pretrained(str(MODELS / 'whisper')).to(device).eval()
    ap = AudioProcessor(str(MODELS / 'whisper'))
    features, length = ap.get_audio_feature(str(WORK / 'drive.wav'))
    chunks = ap.get_whisper_chunk(features, device, torch.float32, whisper, length, fps=FPS)
    assert len(chunks) == COUNT
    del whisper, ap, features
    x1, y1, x2, y2 = FACE
    fw, fh = x2-x1, y2-y1
    yy, xx = np.mgrid[:fh, :fw]
    # Mouth and adjacent jaw only. The upper face and the product are untouched.
    radius = np.sqrt(((xx-fw*.50)/(fw*.37))**2 + ((yy-fh*.72)/(fh*.25))**2)
    alpha = np.clip((1.0-radius)/.22, 0, 1)[..., None]
    protection = []
    for i in range(COUNT):
        frame = cv2.imread(str(WORK / f'source-{i+1:03d}.png'))
        assert frame is not None and frame.shape[:2] == (1080, 1920)
        crop = cv2.resize(frame[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
        latent = vae.get_latents_for_unet(crop)
        condition = pe(chunks[i:i+1])
        pred = unet.model(latent, torch.tensor([0]), encoder_hidden_states=condition).sample
        face = cv2.resize(vae.decode_latents(pred)[0], (fw, fh), interpolation=cv2.INTER_LANCZOS4)
        result = frame.copy()
        result[y1:y2, x1:x2] = np.rint(face*alpha + frame[y1:y2, x1:x2]*(1-alpha)).clip(0, 255).astype(np.uint8)
        protected = np.ones(frame.shape[:2], dtype=bool)
        protected[y1:y2, x1:x2] = False
        assert np.array_equal(result[protected], frame[protected]), 'non-face pixels changed'
        protection.append(True)
        cv2.imwrite(str(WORK / f'synced-{i+1:03d}.png'), result)
        if i % 15 == 0:
            print(json.dumps({'frame': i, 'total': COUNT, 'elapsed': round(time.monotonic()-started, 2)}), flush=True)
    # First encode the unchanged-composition master, then the tighter delivery.
    master = OUT / 'lipsync-master.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-framerate', '30', '-i', str(WORK / 'synced-%03d.png'),
         '-i', str(OUT / 'factory-presenter.mp4'), '-map', '0:v', '-map', '1:a',
         '-t', '6', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p',
         '-c:a', 'copy', '-movflags', '+faststart', str(master)])
    view = 'crop=1536:864:192:0,scale=1920:1080:flags=lanczos'
    final = OUT / 'factory-presenter-fixed.mp4'
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(master), '-vf',
         view + ',unsharp=5:5:0.35:5:5:0,ass=factory-presenter/build/subs.ass',
         '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-c:a', 'copy',
         '-movflags', '+faststart', str(final)])
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(ROOT / 'build/video_noaudio.mp4'),
         '-vf', view + ',tpad=stop_mode=clone:stop_duration=0.2', '-t', '6',
         '-c:v', 'libx264', '-crf', '16', '-pix_fmt', 'yuv420p', str(OUT / 'same-crop-baseline.mp4')])
    contact_sheet(lambda i: WORK / f'synced-{i+1:03d}.png', 'face-sync-review.jpg', FACE)
    contact_sheet(lambda i: WORK / f'synced-{i+1:03d}.png', 'full-sync-review.jpg')
    contact_sheet(lambda i: WORK / f'synced-{i+1:03d}.png', 'product-preserved-review.jpg', (350, 400, 760, 940))
    receipt = dict(test_sha=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                   model_source_sha=os.environ['MUSETALK_SHA'], frames=COUNT, fps=FPS,
                   driving_voice_sha256=digest(WORK / 'drive.wav'), final_sha256=digest(final),
                   master_sha256=digest(master), duration=6, face_bbox=FACE, crop=CROP,
                   protected_source_frames=sum(protection), non_face_exact_pixel_preservation=True,
                   product_scale=1.25, sharpening='unsharp amount0.35, no new product details generated',
                   elapsed_seconds=round(time.monotonic()-started, 3),
                   phoneme_sync='AUDIO_DRIVEN_REQUIRES_INDEPENDENT_SYNC_ACCEPTANCE')
    (OUT / 'lipsync-receipt.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
