# Factory presenter comparison

Private creative test authorised on 2026-10-22. The user requested a hearing aid,
a factory background and a speaking presenter, and no extra on-screen AI label.
This test uses a fictional generated presenter, a reference factory image and
the complete official G25BT product PNG. It does not document a real employee.

MiniMax Hailuo 2.3 supplies real human motion from task `455058692219309` using
the existing subscription. Edge TTS supplies separate speech. Exact phoneme lip
sync has not been verified. Rendering, media transforms and validation run only
on GitHub Actions. No subscription key or signed media URL is committed.

The pinned `xianyu110/ecommerce-video-skills` native assembler is unchanged.
The small CI preparation step places the unchanged product image on the model
video; the native assembler provides speech, transitions, captions and export.
The ten-second test has a 5.7-second presenter shot and a 4.3-second product view.

Clipcat requires a separate Clipcat login, API key and its own credits. The
current browser presented its sign-in dialog. Its account balance is unknown;
the unauthenticated page's zero must not be treated as a verified balance.
Clipcat generation has not run. A MiniMax subscription is not a Clipcat API key.

Acceptance: current-SHA full decode, encoding/timing checks, voice-fit and audio
presence checks, mouth/hand movement with a frozen negative control, corrupt
file rejection, and actual exported contact sheets. Movement and audio presence
do not constitute proof of exact lip sync or an auditory quality review.
