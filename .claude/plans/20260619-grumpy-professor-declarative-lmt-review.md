# Grumpy Professor's Review: the `declarative-lmt` branch

> Verbatim report from the grumpy-professor review, 2026-06-19. Reviewed
> `declarative-lmt` vs `master` (~4000 added lines) through a YAGNI lens.

## Opening verdict

Right. I expected to hate this. A "declarative DSL", a "compiler", a "population walk" implemented _three times_ — that's the kind of phrase that makes me reach for the red pen before I've even opened the file. And there is genuine over-engineering in here that I'll come to.

But I read the code, not your summary, and I have to be fair: **the spine of this is doing real physics work, and most of the complexity is load-bearing.** The thing it's actually buying you — automatically generating model-predicted resonance frequencies and pulse durations for an arbitrary LMT ladder, _and_ predicting where every cloud lands so the camera ROIs follow them — is exactly the sort of bookkeeping a human gets wrong by hand at pulse number nine. This is not a student building a cathedral for a garden shed. It's closer to a student building a slightly-too-elaborate workbench for a job that genuinely needs a workbench.

So: not a rewrite. A trim. Let me separate the muscle from the fat.

## What's actually good here

Credit where it's due, because there's more than I expected:

1. **The declarative sequence earns its keep.** `lmt_sequence.py` is not abstraction for its own sake. Look at what `_compile_pulse` (lines 549–683) produces from `pi(Beam.DOWN, m=13)`: the resolved transition, the `m_term_hz` resonance offset, a duration default `area / (2*rabi)`, and the population update. A student writing an N=12 launch by hand would be hand-typing 12 resonance frequencies and 12 durations and getting the recoil sign wrong somewhere. The `ladder()` helper (line 273) collapses that to one line. **That is the DSL paying for itself.** The experiments in `lmt_declarative.py` and `red_mot_dynamic_roi.py` read like the physics: slice, set point, clearout, ladder, Mach-Zehnder. I can read those sequences in ten seconds and so can your successor.

2. **The validation in the compiler is genuinely useful physics-checking,** not ceremony. "Clearout would remove all remaining population" (line 471), "both internal states populated at this m, disambiguate" (line 591), "pulse on a beam with no declared Rabi" (line 564). These are the exact mistakes you make at 2am during commissioning. Catching them at build time instead of on the atoms is worth real money in beam time.

3. **The intent stream is a sound architectural decision.** Recording _what each pulse was meant to do_ alongside the pulse facts, in the same `register_*` call so they can't misalign (`pulse_recorder_and_tracker.py:385`), is the right call. The alternative — re-deriving flip/split from a Bordé Rabi-probability heuristic on the recorded frequencies — is explicitly what the desk-side simulator does, and the docstring at `trajectory.py:9–11` is honest that you keep that branch-explosion mess _out_ of the experiment path on purpose. Good instinct. That's a physicist's judgement, not an engineer's.

4. **The `SetPoint`-costs-time warnings.** Every docstring that touches `SetPoint` screams that it advances the timeline and will break interferometer symmetry (`lmt_sequence.py:51`, `:179`, the experiment comment at `lmt_declarative.py:115`). That's the single most subtle bug in this whole design and you've flagged it everywhere it matters. The next student _will_ thank you for that.

5. **The tests exist and are substantial** (1355 lines across five files). For code that decides where to point a camera and what frequency to hit an atom with, that's appropriate, not gold-plating.

## Where you're playing software engineer

Ranked by how hard I'll lean on you.

### 1. (MUST FIX) The `FIXME` on `Callback` — `lmt_sequence.py:247`

```python
# FIXME This needs to be more expressive
```

Your own `AGENTS.md` says FIXME markers are not allowed on master and fail CI. This is a self-inflicted wound. Either the Callback is fine as it is — in which case delete the comment or downgrade it to a `TODO` with a sentence saying _what_ expressiveness is missing — or it isn't, in which case fix it before merge. A bare "this needs to be more expressive" with no specifics is a note-to-self, not a code comment. It will block your own merge. **Cut it or qualify it. Five minutes.**

### 2. (SHOULD FIX, but smaller than I first thought) The triple population walk

You flagged this yourself, and on first read it's the most damning thing in the branch: the flip/superpose/clearout/addressing semantics appear in three places —

- `lmt_sequence._compile_pulse` / `_apply_callback` (compile time, on `(state, m)` tuples)
- `trajectory._branch_is_addressed` / `_apply_callback` (ROI prediction, on `_Branch` with displacement vectors)
- `lmt_spacetime._addresses` / `_apply_callback` (drawing, on `Cloud` with full per-event history)

Three copies of "which branch does a pulse address" (`lmt_sequence.py:604–629`, `trajectory.py:138–167`, `lmt_spacetime.py:136–162`) that must be hand-synced. The addressed-pair arithmetic — `m_g = addressed_m - delta_m` for an excited-addressed pulse — is _byte-for-byte identical_ in `trajectory.py:159–167` and `lmt_spacetime.py:156–162`. That is a refactor screaming to happen, and "they operate on different data structures" only half-excuses it.

**But** I'll temper my grumpiness: the _addressing predicate_ genuinely is the same in all three, whereas the _application_ differs for real reasons (the compiler tracks a set of tuples; the predictor tracks displacement vectors and advances them ballistically; the diagram appends to per-event history lists and forks colours). So this is not "extract one function and delete two." It's "extract the **addressing predicate** — the `_branch_is_addressed` / `_addresses` logic — into one pure function in `pulse_intent.py` that takes `(is_ground, m, IntentEvent)` and returns a bool, and call it from both physics modules." That kills the duplication that's actually dangerous (the pair arithmetic, where a sign error would silently put a cloud in the wrong place) while leaving the structurally-different walks alone.

Don't try to unify all three walks into one grand abstraction — _that_ would be the over-engineering. Just pull out the one predicate that's literally copy-pasted. **One function, ~15 lines, deletes two copies.**

### 3. (NICE TO HAVE — and weaker than you implied) The `Callback` escape hatch

You asked whether `Callback` and the `STATE_AUTO`/`M_AUTO` branches are speculative. Let me split them, because they have _opposite_ answers.

**`STATE_AUTO`/`M_AUTO` are NOT speculative — leave them alone.** I checked. The legacy `register_pulse` (`pulse_recorder_and_tracker.py:311`) emits `STATE_AUTO`/`M_AUTO`, and it has _dozens_ of live callers: `clock_spectroscopy`, `clock_interferometry`, `clock_spec_pulse_ratio`, `clock_shelving`, and all of `LMT_launch_mixins`. Those are real, running, present-day experiments. The auto-resolve branches in `trajectory.py:150–157` and `lmt_spacetime.py:149–154` are what lets every one of those _existing_ experiments get a spacetime diagram and ROI prediction without being ported to the new DSL. That's not generality-for-the-future; that's compatibility-with-the-present. Keep it.

**`Callback`, on the other hand, is currently dead weight.** Grep says: it has _no_ call site anywhere in the repo. The only appearance in an actual experiment is a commented-out example (`lmt_declarative.py:133`). It's tested (`test_lmt_sequence.py:288`), it's threaded through the compiler, the kernel engine (`declarative_lmt.py:543–552`), the intent recorder, _and_ both physics walks — a full vertical slice of machinery for a feature nobody fires yet. And it carries a `# FIXME This needs to be more expressive`, which tells me even _you_ aren't sure it's the right shape.

I won't tell you to rip it out — a shaped/Jesse-pulse escape hatch is a foreseeable near-term need, the hooks are cheap, and the intent-bookkeeping argument (keep later pulses' resonance correct) is legitimate. But understand that **right now it's the least-earning part of the branch**: maximum surface area, zero present users. If you want to be honest with your successor, either (a) wire up the one real shaped pulse you actually intend to fire and delete the commented example, or (b) leave a one-line note saying "no live caller yet; first real use will tell us what `state_effect`/`delta_m` need to become." Don't leave it half-committed with a vague FIXME — that's the worst of both worlds.

### 4. (NICE TO HAVE) The padding-parameter / homogeneous-array dance — `declarative_lmt.py:222–310`

The `lmt_unused_pad` handle padding out the offset/duration/setpoint handle lists so they stay "homogeneous and non-sparse" for the kernel is ugly, and the comment at line 232 admits it's fighting the ARTIQ compiler. This is _not_ your fault — it's the kernel/host boundary being its usual miserable self, and parallel arrays indexed by event number is honestly the least-bad way to feed a variable sequence to a `@kernel` that can't hold a list of objects. I'm noting it so the next student knows it's a workaround for ARTIQ, not a design they should imitate elsewhere. **Leave it, but the comment could say "ARTIQ kernels can't iterate heterogeneous objects, hence parallel arrays" so nobody tries to 'clean it up' into a list of dataclasses and waste a day discovering why that can't work.**

### 5. (LEAVE IT) The docstrings

Some of these docstrings are longer than the functions. The `red_mot_dynamic_roi.py` "HOOK-COLLISION AUDIT" blocks (lines 55–80, 128–139, and again in the factory) are repeated three times with minor variations. My instinct is to grumble about prose bloat. But MRO hook-collisions in this mixin stack are a genuine footgun — a silently-wrong `get_andor_camera_config_hook` would install the wrong camera config and you'd chase it for a week — and writing down _which parent owns which hook_ is exactly the documentation that saves the next student. I'll allow it. If anything, the _repetition_ across the three experiments is the only waste; one shared note referenced from all three would do. Minor.

## What happens when the next student inherits this

Survival prognosis: **better than most of what crosses my desk, with two specific traps.**

The good news: a new student can write a new interferometer by copying `lmt_declarative.py`, editing a list of `pi`/`pi2`/`ladder` calls, and running it. The compiler will yell at them if they get the population bookkeeping wrong. The ROIs will follow the clouds. They do not need to understand the three population walks to _use_ the system — and that's the real test of whether an abstraction earns its keep. This passes it.

The traps:

- **The three-way sync.** The day someone changes the addressing semantics — say they add a new `state_effect` — they must change it in three files or the live ROI predictor and the diagnostic spacetime diagram will _silently disagree_ with each other and with the compiler. Nobody will notice until a cloud lands outside its ROI and the data looks like noise. Fixing finding #2 (extract the one shared predicate) is the single highest-value thing you can do for your successor's sanity. It's not about elegance; it's that _silent_ divergence between "where I think the atom is" and "where I told the camera to look" is the worst failure mode this whole stack has.

- **The `Callback` half-feature.** A student who sees `Callback` in the language, fully tested and fully plumbed, will reasonably assume it's a finished, used feature and build on it — then discover the FIXME and that no one has ever fired one. Resolve its status now while you still remember what you intended.

Everything else — the padding arrays, the verbose hook audits, the SetPoint warnings — is either honest workaround or honest warning, and reads fine.

## Prioritised punch-list

**Must fix before merge:**

1. Delete or qualify the `# FIXME` at `lmt_sequence.py:247` — it violates your own CI convention and will block you.

**Should fix (cheap, high value):** 2. Extract the addressing predicate (`_branch_is_addressed` / `_addresses`, the identical pair-arithmetic at `trajectory.py:159–167` and `lmt_spacetime.py:156–162`) into one pure function in `pulse_intent.py`. Kills the _dangerous_ duplication; leaves the structurally-different walks alone. Do **not** over-unify the three walks themselves. 3. Resolve `Callback`'s status: either wire up the one real shaped pulse you mean to fire, or leave an honest one-line "no live caller yet" note. Stop leaving it in limbo.

**Nice to have:** 4. Add one comment at `declarative_lmt.py:232` explaining the parallel-array padding is an ARTIQ kernel constraint, not a pattern to copy. 5. De-duplicate the three near-identical HOOK-COLLISION AUDIT blocks in `red_mot_dynamic_roi.py` into one shared note.

**Leave it alone:** 6. `STATE_AUTO`/`M_AUTO` — real present consumers (all the legacy clock mixins), not speculative. 7. The declarative DSL and compiler themselves — they earn their complexity. 8. The intent-stream architecture and keeping the Bordé simulation off the experiment path — correct physicist's judgement.

Net: this is a workbench that's about 15% too elaborate, not a cathedral. Trim those three things and it'll outlive your PhD. That's more than I can say for most branches.
