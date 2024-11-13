# 2024-11-13 - Charles Notes

*To be copied into the Onenote once I have an internet connection*

I am trying to do two things:

1. Compensate Doppler shifts from falling clouds.
2. Shape pulses for optimal control.

In terms of software, it's possible to use a single AD9910 to modulate both frequency, phase and amplitude simultaneously. The AD9910 supports five modes:

* Static output
* Digital ramp generation
* RAM playback (1024 words, configurable time-steps)
* Parallel port modulation (not implemented on Urukul)
* Amplitude keying

With the exception of the amplitude keying (which always does amplitude), you can wire those modulation sources up to either:

* Phase
* Frequency
* Amplitude
* Phasors (i.e. phase + amplitude)

Critically, you can have multiple modulation modes running simultaneously as long as their targets (amplitude/phase/frequency) do not clash. If they do clash, this is resolved according to "Table 5" in the datasheet.

So the best option for us is simultaneous:

* Phasor modulation via RAM playback for phase / amplitude control with 1024 bins
* Linear frequency ramps for Doppler shift compensation

There are a few ways to do this.

## Method A

The most obvious would be to use the switch AOM to shape pulses while we continue to use the delivery AOM for SUServoing. This would require swapping to an AD9910 instead of an AD9912 for the switch AOMs.

**Pros:**

* Simplicity of concept
* High-bandwidth intensity servo throughout pulses

**Cons:**

* Requires switching ARTIQ hardware in the master crate. Breaks compatibility
  with old code, results in downtime for the experiment, consumes an AD9910 that
  we wanted for USOC.

* Limits resolution to ~1Hz for the clock beam. This is of the same order as our
  laser noise, so would be noticeable for running an optical clock. We don't
  have the EEM slots to have both, so would have to physically remove the
  existing AD9912.

## Method B

Use the delivery SUServo to apply both phase, amplitude and frequency
modulation. This works because we can write to SUServo AD9910s individually by
using the NU_MASK feature in the Urukul CPLD code (although this isn't
implemented in ARTIQ yet). We can't read back, but that's OK, we don't need to.
The AD9912 remains as a dump switch.

**Pros:**

* No hardware changes required
* Continues to support uHz resolution clock pulses for when we do a clock
  sequence

**Cons:**

* We can't SUServo the clock beam during the pulses

* We could work around the lack of servoing by running the SUServo at the start
  of the sequence, reading out the `y` value after it settles then using this as
  the amplitude. This is annoying however because:
  * We don't get servoing during the pulse => vulnerable to noise at the ~1s
    timescale. Probably fine
  * Our amplitudes of the pulse shaping modulation change each shot =>
    * No caching = slow writing
    * potential change in behaviour if bit-depth is an issue: this would be a
      problem if the SUServo setpoint is low which we might well want sometimes
      for slow pulses

## Method C

Use a SUServo channel to drive the switch AOM, leaving the delivery AOM alone.
This is a bodge version of Method A which results in an AD9910 driving the
switch AOM, except is doesn't require us to change the ARTIQ hardware. It has
mostly the same pros / cons as method A.

**Pros:**

* Servoing throughout shot
* No hardware changes needed

**Cons:**

* Sacrifices clock resolution
* Requires rewriting all code that switches the clock AOM on/off since now it's
  a SUServo instead
* Wastes a SUServo channel - this would consume the last channel, and we're
  probably about to need it for the perturbing 689 beam == too many beams!

## Decision

I don't think we can afford to consume an extra SUServo channel since this will
stop us when we want to do perturbed interferometry. So option C is ruled out.

Method B is less conceptually simple and will need more code. It also is worse
for interferometry - we don't have servoing during pulses, which might be a
problem. It also might couple beam pointing weirdly as our pulses change
duration which is a problem I don't want to think about. Method A is much
simpler and isn't vulnerable to these things, at the cost of uHz resolution
which we don't currently need. So let's optimize for the problems we have today,
not the ones we might have later.

**Choosing method A.**
