"""CI-only media checks for native skill outputs; called by the evaluation workflow.

Uses ffmpeg/ffprobe and upstream timing; never imports or changes upstream code.
Checks encoded output, not a renderer's success message. No model/network calls.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def check(video, width, height, duration, audio):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    data = json.loads(result.stdout)
    visual = next(s for s in data["streams"] if s["codec_type"] == "video")
    assert (visual["width"], visual["height"]) == (width, height), "wrong resolution"
    assert visual["codec_name"] == "h264" and visual["pix_fmt"] == "yuv420p"
    assert visual["r_frame_rate"] == "30/1", "wrong frame rate"
    assert abs(float(data["format"]["duration"]) - duration) <= 0.15, "wrong duration"
    if audio:
        sound = next(s for s in data["streams"] if s["codec_type"] == "audio")
        assert sound["codec_name"] == "aac" and sound["channels"] == 2
        assert sound["sample_rate"] == "48000"
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"],
                   check=True, timeout=180)
    return data


def main():
    mode = sys.argv[1]
    video = Path("out") / ("iart-kenburns.mp4" if mode == "iart" else "aura-" + mode + ".mp4")
    width, height, duration, audio = 1920, 1080, 5.0, False
    if mode != "iart":
        width, height, audio = 1080, 1920, True
        timing = json.loads(Path("build/timing.json").read_text())
        duration = timing["total"]
        assert len(timing["durations"]) == 6 and duration > 10
        assert "-->" in video.with_suffix(".srt").read_text()
    data = check(video, width, height, duration, audio)
    # Mutation: the same gate must reject an actual truncated MP4, then accept the real output.
    broken = Path("out/truncated.mp4")
    broken.write_bytes(video.read_bytes()[:64])
    try:
        check(broken, width, height, duration, audio)
    except (subprocess.CalledProcessError, AssertionError, KeyError, StopIteration):
        mutation = "RED: truncated MP4 rejected; GREEN: original decoded and passed"
    else:
        raise AssertionError("gate accepted a corrupt MP4")
    finally:
        broken.unlink()
    data = check(video, width, height, duration, audio)
    # Compare two actual frames within the first native still shot, away from the transition.
    hashes = []
    for stamp in (0.7, 1.7):
        raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", str(stamp), "-i", str(video),
                                       "-frames:v", "1", "-vf", "scale=96:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        hashes.append(hashlib.sha256(raw).hexdigest())
    assert hashes[0] != hashes[1], "first shot has no frame change"
    receipt = {"mode": mode, "source_sha": os.environ["SOURCE_SHA"],
               "test_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
               "video": str(video), "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
               "bytes": video.stat().st_size, "probe": data, "mutation": mutation,
               "frame_hashes": hashes, "generated_video_model_calls": 0,
               "scope": "native photo-motion render; does not generate human actions"}
    Path("out/verification.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps({k: v for k, v in receipt.items() if k != "probe"}, indent=2))


if __name__ == "__main__":
    main()
