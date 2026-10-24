"""CI-only deterministic sync evidence; called after lipsync.py.

Depends on pinned MuseTalk SyncNet/config and ByteDance's own checkpoint.
Never uses Wav2Lip weights. Scores are cosine similarities, not LSE-C.
Failed checks and exceptions are saved before the process fails.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path('factory-presenter')
OUT = ROOT / 'out'
WORK = ROOT / 'build/lipsync'
UPSTREAM = Path('musetalk-upstream')
MUSE_SHA = '0a89dec45a0192b824e3cf4daf96c239440c5ed8'
LATENT_SHA = 'a229c3948406bc2cf6eaf4873e662e70c6a04746'
WEIGHT_REV = '405eda8eab9f65c1a6e0c292a5dee5a08089e2ae'
WEIGHT_HASH = '38fa63bad3ed2332f647c40a5dc616cb0e233db8579f698f62af4c41965c4da5'
FACE = (740, 150, 1190, 670)
FINAL_FACE = tuple(round(v) for v in ((740-192)*1.25, 150*1.25,
                                     (1190-192)*1.25, 670*1.25))
STARTS = [0.5, 1, 1.5, 2, 2.5, 3, 3.5]
REPORT = OUT / 'sync-scores.json'


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def run(args, timeout=180):
    return subprocess.run(args, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout).stdout


def save(report):
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, allow_nan=False))


def check(report, name, passed, detail=None):
    report['checks'][name] = {'pass': bool(passed), 'detail': detail}
    save(report)


def official_file(relative, target):
    url = f'https://raw.githubusercontent.com/bytedance/LatentSync/{LATENT_SHA}/{relative}'
    with urllib.request.urlopen(url, timeout=60) as response:
        target.write_bytes(response.read())
    return {'url': url, 'sha256': digest(target)}


def media_checks(report, paths):
    aac = {}
    for name, path in paths.items():
        data = json.loads(run(['ffprobe', '-v', 'error', '-count_frames',
                              '-show_streams', '-show_format', '-of', 'json', str(path)]))
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'])
        frames = int(video['nb_read_frames'])
        duration = float(video.get('duration', data['format']['duration']))
        container_duration = float(data['format']['duration'])
        expected_frames = 176 if name == 'native' else 180
        expected_video_duration = 176/30 if name == 'native' else 6
        check(report, f'{name}_media', frames == expected_frames
              and abs(duration-expected_video_duration) <= 0.001
              and abs(container_duration-6) <= 0.001
              and video['width'] == 1920 and video['height'] == 1080,
              {'frames': frames, 'video_duration': duration,
               'container_duration': container_duration, 'fps': video['avg_frame_rate']})
        payload = run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0',
                       '-c:a', 'copy', '-f', 'adts', '-'])
        aac[name] = hashlib.sha256(payload).hexdigest()
    report['aac_adts_sha256'] = aac
    check(report, 'native_aac_preserved', len(set(aac.values())) == 1, aac)


def product_check(report):
    # Re-evaluation works from the uploaded encoded videos, without PNGs.
    # Generation-stage exact preservation is provenance, not this gate's proof.
    import numpy as np
    receipt_path = OUT / 'lipsync-receipt.json'
    receipt = json.loads(receipt_path.read_text())
    report['generation_protection_provenance'] = {
        'receipt_sha256': digest(receipt_path), 'generation_sha': receipt.get('test_sha'),
        'protected_source_frames': receipt.get('protected_source_frames'),
        'non_face_exact_pixel_preservation': receipt.get('non_face_exact_pixel_preservation'),
        'scope': 'generation-stage assertion only; no PNGs in evaluation artifact'}
    assert receipt.get('master_sha256') == report['input_sha256']['master'], 'Receipt/master mismatch'
    assert receipt.get('final_sha256') == report['input_sha256']['final'], 'Receipt/final mismatch'

    def decoded_roi(path):
        raw = run(['ffmpeg', '-v', 'error', '-i', str(path), '-an', '-vf',
                   'fps=30,tpad=stop_mode=clone:stop_duration=0.2,trim=duration=6,'
                   'crop=410:540:350:400:exact=1', '-pix_fmt', 'rgb24',
                   '-f', 'rawvideo', '-'])
        frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 540, 410, 3)
        assert len(frames) == 180, f'{path}: expected 180 padded ROI frames'
        return frames

    native = decoded_roi(OUT / 'factory-presenter.mp4')
    master = decoded_roi(OUT / 'lipsync-master.mp4')
    errors = [float(np.abs(a.astype('int16')-b.astype('int16')).mean())
              for a, b in zip(native, master)]
    check(report, 'product_roi_decoded_mae', max(errors) < 4,
          {'roi': [350, 400, 760, 940], 'frames': 180,
           'per_frame_mean_abs_error': errors, 'max_frame_mae': max(errors),
           'threshold': 'every frame mean_abs_error < 4 (8-bit RGB)',
           'scope': 'actual encoded native versus fullframe master; native tail cloned to 6s; '
                    'compression-tolerant retention, not exact pixels or restored detail; '
                    'final cropped/sharpened appearance requires visual review'})


def faces(path, bbox):
    import numpy as np
    import torch
    import torch.nn.functional as F
    x1, y1, x2, y2 = bbox
    width, height = x2-x1, y2-y1
    raw = run(['ffmpeg', '-v', 'error', '-i', str(path), '-an', '-vf',
               'tpad=stop_mode=clone:stop_duration=0.2,trim=duration=6,fps=25,'
               f'crop={width}:{height}:{x1}:{y1}:exact=1', '-pix_fmt',
               'rgb24', '-f', 'rawvideo', '-'])
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, height, width, 3)
    if len(frames) != 150:
        raise RuntimeError(f'{path}: expected 150 evaluation frames, got {len(frames)}')
    windows = []
    for seconds in STARTS:
        start = round(seconds*25)
        block = torch.from_numpy(frames[start:start+16].copy()).permute(0, 3, 1, 2).float()
        # Matches official ImageProcessor.process_images: bicubic/antialias,
        # RGB normalization, then flatten time into channels and lower-half crop.
        block = F.interpolate(block, (256, 256), mode='bicubic', align_corners=False,
                              antialias=True).round().clamp(0, 255) / 127.5 - 1
        windows.append(block.reshape(1, 48, 256, 256)[:, :, 128:, :])
    return windows


def main(report):
    assert os.environ.get('GITHUB_ACTIONS') == 'true', 'GitHub Actions execution required'
    import numpy as np
    import torch
    import librosa
    from scipy import signal
    from scipy.io import wavfile
    from omegaconf import OmegaConf
    from huggingface_hub import hf_hub_download

    torch.set_num_threads(min(4, os.cpu_count() or 1))
    torch.manual_seed(24024)
    torch.use_deterministic_algorithms(True)
    paths = {'native': OUT / 'factory-presenter.mp4',
             'master': OUT / 'lipsync-master.mp4',
             'final': OUT / 'factory-presenter-fixed.mp4'}
    report['input_sha256'] = {k: digest(p) for k, p in paths.items()}
    report['evaluation_audio_sha256'] = digest(WORK / 'evaluation.wav')
    report['evaluation_audio_scope'] = 'decoded delivered AAC mix including original BGM; same audio in all compared videos'
    save(report)
    media_checks(report, paths)
    product_check(report)

    actual_sha = run(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD']).decode().strip()
    assert actual_sha == MUSE_SHA, f'Unexpected MuseTalk revision {actual_sha}'
    sys.path.insert(0, str(UPSTREAM.resolve()))
    from musetalk.models.syncnet import SyncNet
    cfg_path = UPSTREAM / 'configs/training/syncnet.yaml'
    cfg = OmegaConf.load(cfg_path)
    # Model has no attention blocks, therefore no xformers/CUDA requirement.
    assert not any(cfg.model.audio_encoder.attn_blocks)
    assert not any(cfg.model.visual_encoder.attn_blocks)
    report['sync_config_sha256'] = digest(cfg_path)
    weight = hf_hub_download('ByteDance/LatentSync', 'latentsync_syncnet.pt',
                             revision=WEIGHT_REV, local_dir=str(WORK / 'syncnet'))
    assert digest(weight) == WEIGHT_HASH, 'SyncNet checkpoint hash mismatch'
    report['model'] = {'repo': 'ByteDance/LatentSync', 'revision': WEIGHT_REV,
                       'file': 'latentsync_syncnet.pt', 'sha256': WEIGHT_HASH,
                       'license': 'OpenRAIL++ (use restrictions apply)', 'dtype': 'float32'}
    model = SyncNet(OmegaConf.to_container(cfg.model)).float().cpu().eval()
    checkpoint = torch.load(weight, map_location='cpu', weights_only=True)
    model.load_state_dict(checkpoint['state_dict'], strict=True)
    del checkpoint

    # Read pinned official preprocessing config/source as evidence. Implement
    # its standard DSP equations here; do not execute upstream downloaded code.
    audio_cfg_path = WORK / 'sync-audio.yaml'
    report['preprocessing_sources'] = [
        official_file('configs/audio.yaml', audio_cfg_path),
        official_file('latentsync/utils/audio.py', WORK / 'sync-audio-upstream.py')]
    ac = OmegaConf.load(audio_cfg_path).audio
    assert ac.sample_rate == 16000 and ac.hop_size == 200 and not ac.use_lws

    def mel(wave):
        if ac.preemphasize:
            wave = signal.lfilter([1, -ac.preemphasis], [1], wave)
        spectrum = np.abs(librosa.stft(y=wave, n_fft=ac.n_fft,
                                      hop_length=ac.hop_size, win_length=ac.win_size))
        basis = librosa.filters.mel(sr=ac.sample_rate, n_fft=ac.n_fft,
                                    n_mels=ac.num_mels, fmin=ac.fmin, fmax=ac.fmax)
        db = 20*np.log10(np.maximum(np.exp(ac.min_level_db/20*np.log(10)), basis@spectrum))
        db -= ac.ref_level_db
        assert ac.signal_normalization and ac.symmetric_mels and ac.allow_clipping_in_normalization
        normalized = 2*ac.max_abs_value*((db-ac.min_level_db)/(-ac.min_level_db))-ac.max_abs_value
        return np.clip(normalized, -ac.max_abs_value, ac.max_abs_value).astype('float32')

    voice, sr = librosa.load(str(WORK / 'evaluation.wav'), sr=16000, mono=True)
    assert sr == 16000 and len(voice) == 96000
    controls = {'zero': voice}
    for offset, label in [(6400, 'delay_400ms'), (-6400, 'advance_400ms')]:
        shifted = np.zeros_like(voice)
        if offset > 0:
            shifted[offset:] = voice[:-offset]
        else:
            shifted[:offset] = voice[-offset:]
        control_path = WORK / f'{label}.wav'
        # Persist real shifted waveforms, rather than relabeling a zero-lag score.
        wavfile.write(control_path, sr, shifted.astype('float32'))
        controls[label] = shifted
        report.setdefault('negative_control_sha256', {})[label] = digest(control_path)
    mels = {k: mel(v) for k, v in controls.items()}
    save(report)

    with torch.inference_mode():
        audio_cache = {}

        def audio_embedding(label, frame_start):
            key = (label, frame_start)
            if key not in audio_cache:
                idx = int(80.0*frame_start/25)
                block = mels[label][:, idx:idx+52]
                assert block.shape == (80, 52)
                audio_cache[key] = model.get_audio_embed(torch.from_numpy(block)[None, None])
            return audio_cache[key]

        for name, path in paths.items():
            windows = faces(path, FINAL_FACE if name == 'final' else FACE)
            image_embeddings = [model.get_image_embed(window) for window in windows]

            def score(label, offset_frames=0):
                values = []
                for seconds, image in zip(STARTS, image_embeddings):
                    # Positive offset means audio delayed with respect to video.
                    frame_start = round(seconds*25)-offset_frames
                    audio = audio_embedding(label, frame_start)
                    values.append(float((image*audio).sum()))
                return {'mean': float(np.mean(values)), 'windows': values}

            row = {label: score(label) for label in controls}
            row['offset_scan'] = {str(k*40): score('zero', k)
                                  for k in range(-10, 11)}
            row['peak_offset_ms'] = int(max(row['offset_scan'],
                                           key=lambda k: row['offset_scan'][k]['mean']))
            report.setdefault('scores', {})[name] = row
            save(report)
            print(json.dumps({'video': name, 'scores': row}), flush=True)

    baseline = report['scores']['native']['zero']['mean']
    for name in ('master', 'final'):
        row = report['scores'][name]
        check(report, name+'_zero_beats_controls', row['zero']['mean'] >
              max(row['delay_400ms']['mean'], row['advance_400ms']['mean']))
        check(report, name+'_zero_improves_native', row['zero']['mean'] > baseline)
        check(report, name+'_peak_within_80ms', abs(row['peak_offset_ms']) <= 80,
              {'peak_offset_ms': row['peak_offset_ms'], 'fixed_limit_ms': 80})
    passed = all(item['pass'] for item in report['checks'].values())
    report['status'] = 'PASS' if passed else 'FAIL'
    save(report)
    assert passed, f'Sync/media gate failed; evidence saved to {REPORT}'


if __name__ == '__main__':
    report = {'status': 'RUNNING', 'test_sha': os.environ.get('GITHUB_SHA'),
              'run_id': os.environ.get('GITHUB_RUN_ID'), 'script_sha256': digest(__file__),
              'musetalk_sha': MUSE_SHA, 'latentsync_source_sha': LATENT_SHA,
              'window_starts_seconds': STARTS, 'evaluation_fps': 25,
              'actual_window_start_frames': [round(s*25) for s in STARTS],
              'face_bbox': FACE, 'final_face_bbox': FINAL_FACE, 'checks': {},
              'metric': 'mean normalized embedding cosine; NOT LSE-C; no legacy threshold',
              'acceptance': 'master/final zero score beats both real +/-400ms controls and native zero; '
                            'absolute peak offset <=80ms; every decoded product ROI frame MAE<4',
              'limitations': 'fixed face boxes; relative clip comparison, not phoneme-level certification'}
    try:
        main(report)
    except Exception as exc:
        report['status'] = 'FAIL'
        report['exception'] = f'{type(exc).__name__}: {exc}'
        save(report)
        raise
