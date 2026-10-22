"""Pass the continuous handheld source to the pinned native video assembler.

Called only by factory-presenter.yml. This module verifies source identity and
writes the storyboard; it never adds product cards or replaces the hand shot.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path('factory-presenter')
ASSETS = ROOT / 'assets'
(ROOT / 'out').mkdir(exist_ok=True)
manifest = json.loads((ROOT / 'evidence/handheld-input-manifest.json').read_text())
assert str(manifest['task_id']) == '455063786779061'
assert manifest['duration'] == 10 and manifest['resolution'] == '768P'
assert hashlib.sha256((ASSETS / 'presenter-handheld.mp4').read_bytes()).hexdigest() == manifest['raw_sha256']
assert hashlib.sha256((ASSETS / 'presenter-handheld-anchor.png').read_bytes()).hexdigest() == manifest['anchor_sha256']

storyboard = {
    'voice': 'en-US-AndrewNeural', 'rate': '+0%', 'bgm': 'auto',
    'shots': [{
        'video': 'assets/presenter-handheld.mp4', 'start': 0,
        'duration': 10, 'fit': 'cover',
        'line': 'Meet the Daerdo G twenty five B T, a rechargeable Bluetooth hearing aid. A behind the ear design, with simple physical controls.',
        'sub': 'Meet the Daerdo G25BT.|Rechargeable, with Bluetooth.|Behind-the-ear design.|Simple physical controls.'
    }]
}
(ROOT / 'storyboard.json').write_text(json.dumps(storyboard, indent=2))
print('One continuous handheld video; no separate product card or static end shot.')
