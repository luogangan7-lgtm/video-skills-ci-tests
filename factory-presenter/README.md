# Factory presenter comparison

Private creative test authorised on 2026-10-22. The user corrected the brief:
the presenter must physically hold the hearing aid; a separate product card
cannot substitute for hand contact. No additional on-screen AI label is wanted.
This revision uses a generated fictional presenter holding a G25BT referenced
from the complete official product PNG. It does not document a real employee.

MiniMax Hailuo 2.3 supplies a continuous six-second handheld shot from task
`455070782542247`, using the existing subscription. The source is native 1080P.
The hand and product are held still to preserve their shape while the presenter
speaks. Edge TTS supplies separate speech; phoneme-level
lip sync has not been verified. Rendering, media transforms and validation run
only on GitHub Actions. No subscription key or signed media URL is committed.

The pinned `xianyu110/ecommerce-video-skills` native assembler is unchanged.
Its storyboard consumes the actual six-second video directly. No side product
card, image substitution, static end shot, loop or frozen padding is added.
Native speech, captions, BGM and export remain in that skill's own pipeline.

Clipcat's hosted API requires its own login and API key. No documented MiniMax
subscription BYOK route was found. The browser presented sign-in; balance is
unknown. Clipcat generation remains NOT_RUN and is not represented as success.

Acceptance: exact-SHA full decode, duration/encoding and voice-fit checks,
source/final mouth motion with a frozen negative control, measured grip regions, corrupt
file rejection, and source-pixel fidelity with an encoded sidecard negative
control. Actual exported full, face and grip review sheets support independent
visual checks of hand contact, device scale, identity and continuity. Motion
and source fidelity alone do not establish product anatomy or exact lip sync.
Normal-speed complete viewing and listening remain NOT_RUN unless actually
performed and documented separately. The earlier sidecard version and the
ten-second handheld candidate with product deformation are superseded.
