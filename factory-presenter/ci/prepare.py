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
manifest = json.loads((ROOT / 'evidence/fixed-input-manifest.json').read_text())
assert str(manifest['task_id']) == '455070782542247'
assert manifest['duration'] == 6 and manifest['resolution'] == '1080P'
assert hashlib.sha256((ASSETS / 'presenter-fixed.mp4').read_bytes()).hexdigest() == manifest['raw_sha256']
assert hashlib.sha256((ASSETS / 'presenter-handheld-anchor.png').read_bytes()).hexdigest() == manifest['anchor_sha256']

storyboard = {
    'voice': 'en-US-AndrewNeural', 'rate': '+10%', 'bgm': 'auto',
    'shots': [{
        'video': 'assets/presenter-fixed.mp4', 'start': 0,
        'duration': 6, 'fit': 'cover',
        'line': 'Rechargeable Bluetooth hearing aid. Behind the ear design. Simple physical controls.',
        'sub': 'Daerdo G25BT · Rechargeable Bluetooth|Behind-the-ear design|Simple physical controls'
    }]
}
(ROOT / 'storyboard.json').write_text(json.dumps(storyboard, indent=2))
print('One continuous handheld video; no separate product card or static end shot.')
