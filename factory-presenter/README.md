# Factory presenter: audio-driven handheld revision

The presenter holds the G25BT in a continuous fictional factory scene. The
hearing aid remains in the hand; a separate product card cannot replace it.
The creative test is not a record of a real employee or verified factory event.
No extra on-screen disclosure overlay was requested.

The source is MiniMax Hailuo 2.3 task `455070782542247`, native 1080P. Its hand
lifts slightly while maintaining pinch contact. Fixed grip was a generation
instruction, not proof that the hand stays completely still.

The unchanged ecommerce assembler at
`xianyu110/ecommerce-video-skills@96c49b349b7d975bda8f05ce6669c1d33500c269`
generates the narration, its 150ms lead, music and subtitle timing. The new CI
adapter drives MuseTalk with that same narration padded at the same lead. It
composites only an elliptical lower-face area into the existing moving footage;
it does not synthesize the hand or product. Source frames outside the face box
must remain pixel-identical before encoding. Four missing tail frames from the
176-frame source are extended to finish the six-second audio timeline.

Delivery uses a 1536x864 crop scaled to 1920x1080, making the held product 25%
larger, with restrained unsharp filtering. This increases displayed size and
edge contrast; it does not recover missing button lettering or establish new
product facts. The same crop without sharpening is exported for comparison.
The blue shell, wheel, separate controls, tube and ear tip must remain visible.

MuseTalk code is pinned at `0a89dec45a0192b824e3cf4daf96c239440c5ed8`.
Its model repository is pinned at `2bcb936e2fddb4d86db4c62fd45b387d0c061571`.
The adapter uses MuseTalk, SD VAE and Whisper; each model revision, downloaded
file hash and license source is retained in the CI evidence. All inference,
media processing and checks execute on GitHub, never on the author's machine.
No new paid API, provider account, live credential or deployment is involved.

Acceptance requires the actual exported file, not a successful model call:
full decode, six-second/180-frame export, unchanged delivered narration, exact
source pixel protection outside the face, product review before and after the
closer framing, and deterministic audio/visual synchronization comparisons
against the original and deliberately shifted audio. A moving mouth alone does
not satisfy synchronization. Numerical synchronization checks and actual-frame
visual review are distinct; normal-speed viewing/listening must only be claimed
when directly performed. Every receipt identifies the tested SHA and media hash.
Independent review is required before merging the repair.

Clipcat generation remains a separate unexecuted route requiring its own
credentials. It is not counted as successful because the ecommerce route works.
