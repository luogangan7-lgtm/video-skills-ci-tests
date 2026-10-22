"""Prepare the CI-only factory test inputs; preserve the official product pixels.

Called by factory-presenter.yml; depends on Pillow and FFmpeg, then hands the
storyboard to the unchanged, pinned ecommerce-video-skills assembler.
"""
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path('factory-presenter')
ASSETS = ROOT / 'assets'
OUT = ROOT / 'out'
OUT.mkdir(exist_ok=True)
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
NAVY = '#062b4f'


def text(draw, pos, value, size, fill=NAVY, bold=False):
    draw.text(pos, value, font=ImageFont.truetype(BOLD if bold else FONT, size), fill=fill)


product = Image.open(ASSETS / 'product.png').convert('RGB')
assert product.size == (850, 1080), 'unexpected official product source'
assert hashlib.sha256((ASSETS / 'product.png').read_bytes()).hexdigest() == 'ee3db821975dba15127aa5e08b6793c37bbd9a9a124e6be13bf80feac634d349'

# A separate image card keeps the real device out of generative-video redraws.
card = Image.new('RGB', (590, 880), 'white')
d = ImageDraw.Draw(card)
text(d, (48, 34), 'DAERDO', 26, bold=True)
text(d, (44, 90), 'G25BT', 72, bold=True)
text(d, (48, 186), 'Rechargeable + Bluetooth', 28)
p = ImageOps.contain(product, (460, 580), Image.Resampling.LANCZOS)
card.paste(p, ((590 - p.width) // 2, 250))
card.save(ASSETS / 'presenter-card.png')
subprocess.run([
    'ffmpeg', '-y', '-v', 'error', '-i', str(ASSETS / 'presenter-01.mp4'),
    '-i', str(ASSETS / 'presenter-card.png'), '-filter_complex',
    '[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[b];[b][1:v]overlay=1250:65[v]',
    '-map', '[v]', '-t', '6', '-r', '30', '-c:v', 'libx264', '-crf', '18',
    '-pix_fmt', 'yuv420p', '-an', str(ASSETS / 'presenter-card.mp4')
], check=True, timeout=180)

detail = Image.new('RGB', (1920, 1080), '#f8fafc')
d = ImageDraw.Draw(detail)
text(d, (125, 95), 'DAERDO', 36, bold=True)
text(d, (115, 220), 'G25BT', 116, bold=True)
text(d, (125, 390), 'Behind-the-ear design', 48)
text(d, (125, 495), 'Rechargeable', 42)
text(d, (125, 565), 'Bluetooth connectivity', 42)
text(d, (125, 695), 'Volume wheel', 32, '#526576')
text(d, (125, 750), 'M button + O/N switch', 32, '#526576')
p = ImageOps.contain(product, (780, 920), Image.Resampling.LANCZOS)
detail.paste(p, (1030 + (780 - p.width) // 2, 60))
detail.save(ASSETS / 'product-detail.png')

storyboard = {
    'voice': 'en-US-AndrewNeural', 'rate': '+12%', 'bgm': 'auto',
    'shots': [
        {'video': 'assets/presenter-card.mp4', 'duration': 5.7, 'fit': 'cover',
         'line': 'Meet the Daerdo G twenty five B T. Rechargeable, with Bluetooth.',
         'sub': 'Meet the Daerdo G25BT.|Rechargeable, with Bluetooth.', 'transition': 'fade'},
        {'image': 'assets/product-detail.png', 'duration': 4.3, 'fit': 'cover', 'motion': 'static',
         'line': 'A behind the ear design, with simple physical controls.',
         'sub': 'Behind-the-ear design.|Simple physical controls.'}
    ]
}
(ROOT / 'storyboard.json').write_text(json.dumps(storyboard, indent=2))
print('Prepared two shots; no generative redraw of the product; no added AI overlay.')
