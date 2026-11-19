# Red-team (adversary-side) ideas, 7 Oct 2026. Scope rule: simulation and our own test link only. No design or operating guidance for real jammers; jamming other people's links is illegal.
Each idea ends with the defensive lesson it produces. "Quick test" = already run.

## Attacks on the learning and the control logic
1. Bandit poisoning: the jammer fakes interference on good channels so the learner (AFH/Thompson) abandons them and concentrates on channels the jammer then owns. Lesson: keep a uniform floor; detect inconsistent feedback.
2. Mode-forcing (defence exhaustion): cheap bursts push the ladder into slow modes. QUICK TEST: 7.5% airtime bursts cost the ladder almost nothing (bulk 0.863 vs 0.875 for plain ADAPT), so the hysteresis holds up. Next: search for burst patterns that do hurt.
3. Classifier evasion by generative adversary: a small network trained to produce jamming patterns the classifier labels "none", GAN-style (generator = jammer, discriminator = our classifier). Lesson: adversarial training loop for L3.
4. Learning-rate attack: change tactics at exactly the learner's forgetting time so its memory is always stale. Lesson: adapt the discount factor from detected switching.

## Attacks on timing and protocol structure
5. Timing leak: critical messages every 10 slots let a jammer burn only 10% airtime and kill them. QUICK TEST: periodic schedule 0.06 delivery with one attempt vs 0.89 with a randomised start; three attempts hold against a 1-slot burst, five against a 3-slot burst. Lesson: randomise message timing, pad, add dummy traffic.
6. Selective jamming of the control plane: jam only beacons, ACKs, rekey messages or the rendezvous channel. The re-acquisition mode depends on the beacon, so this is the protocol's soft spot. Lesson: multiple rendezvous channels, beacon randomisation.
7. Time-pushing attack: nudge timestamps a few ppm at a time so the clock filter drifts without raising alarms. Lesson: outlier and consistency checks, a hardware oscillator reference.
8. Wormhole / delayed relay: replay our packets later or elsewhere so nodes think they are close, or desynchronise slots. Lesson: distance bounding, authenticated slot counters.

## Attacks on the schedule and keys
9. PRNG graveyard: attack hop schedules from LFSR (done, 8 to 9 hops, mean 8.375), then LCG, xorshift, Mersenne Twister (predictable from 624 outputs when the full 32 bits leak), and truncated or biased outputs; a neural-net predictor on weak generators. Lesson: why HMAC/ChaCha, with a measured cost table.
10. Channel-manipulation attack on key-from-the-air: an attacker who holds the environment still (or floods one channel) lowers fade variance and drains the key's entropy. Lesson: monitor entropy online, abort if low.
11. Partial-knowledge (myopic) jammer: sees only part of each packet, or sees the channel with a delay; how much knowledge turns hopping into a coin flip? Quantify the knowledge-vs-damage curve.

## Attacks on the physical situation
12. Optimal jammer placement: given a patrol path and a power budget, where is the worst spot (minimax over position)? And the optimal relay placement against it (Stackelberg game). Lesson: where to put the relay and how much margin to leave.
13. Jammer swarm: many weak coordinated jammers vs one strong one; coverage and energy efficiency; the defender's best response (spatial diversity). Lesson: when cooperative relaying beats raw power.
14. Energy-optimal jammer: minimise the jammer's own battery for a target damage; the defender prices every jammed slot. Lesson: make attacks expensive.
15. Capture-effect and near-far abuse: a weak signal at the right time and place wins the receiver. Lesson: receiver design margins.

## Deception on the defender side (counter-attacks, still our own link)
16. Honeypot channels: decoy traffic on bait channels lures learning jammers into wasting energy. Test with the EXP3 and frequency jammers already in the code.
17. Moving-target link: change not only channel but modulation, packet length and timing, so a jammer cannot lock onto any feature. Lesson: diversity metric for links.
18. Adversarial co-training: defender and jammer neural networks trained against each other (self-play); watch whether the equilibrium matches the 0.9177 game value.

## Meta
19. Red-team report generator: run the whole attack list automatically and produce a scorecard (which attacks work against which configuration). This is the resilience benchmark with attack tiers.
