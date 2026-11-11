# Titan: embodied continual-learning architecture

**Status:** architectural contract; Stage A has a local simulation and persistence foundation in implementation. No physical actions are enabled.

Titan is not intended to be only a chat model. It is a persistent autonomous agent that learns from interaction with its environment and can operate through a digital or physical body. A language model may be one reasoning component; it is not the whole intelligence.

## Stage A implementation status — 2026-11-11

The first digital experience-memory and simulation foundation is implemented on
the implementation/digital-experience-loop-20261111 branch:

- User-scoped episode metadata with explicit simulation or read_only mode.
- A versioned, ordered D1 event log for observations, predictions, proposed
  actions, validation decisions, outcomes, diagnoses, belief updates, and episode end.
- Event payload validation with bounded fields, finite numeric values, timestamps,
  source attribution, and event-specific schemas.
- Database triggers that reject updates and deletes to experience events.
- Authenticated API routes to create/list episodes, append events, retrieve
  event history, and replay an episode as a deterministic read-only projection,
  with per-user daily write quotas.
- Replay checks contiguous sequence numbers, schema versions, action proposal/
  approval/outcome references, and episode closure; it never executes actions.
- Every append is checked against the complete ordered history before insertion, so orphan approvals, outcomes without approval, duplicate action IDs, and records after closure are rejected before they enter the immutable log.
- Episodes are capped at the 200-event replay window; an expected-sequence condition rejects stale concurrent appends instead of silently corrupting ordering.
- A standard-library-only deterministic toy balance environment in
  training/experience_lab.py.
- Pure transition prediction, measured outcomes, absolute-error scoring, and
  evidence-priority failure classification.
- A fixed PD controller compared against a no-op baseline across five held-out
  initial states; the simulator emits event records matching the Stage A API.

The API records proposed actions; it does not execute tools, actuators, or
physical actions. The simulator runs only in-process. The database migration
is additive and has not been applied to any live D1 database. No model weights
have been trained or changed.

Still outstanding: route-level tests against disposable D1, persistence
verification across process restart, held-out evaluation isolation, and a
genuinely learned policy or world model. Replay is a deterministic projection,
not a learned policy or a substitute for restart testing. The fixed PD controller is a deterministic
baseline, not a learned agent.

## 1. Meaning of a "real entity"

Titan must have a durable identity and continuity across sessions, devices and tasks:

- A stable agent identity, versioned goals, capabilities and permissions.
- Persistent episodic, semantic and procedural memory with provenance and timestamps.
- A live perception/action interface to its current environment.
- A self-model describing its body or tools, capabilities, limits, uncertainty and current state.
- A learning history: what it observed, attempted, predicted, what happened, what changed and why.
- A lifecycle that can pause, resume, migrate and recover without losing its identity or corrupting memory.

This is an engineering definition of an embodied agent. It does not claim consciousness, feelings or subjective experience.

## 2. The continual learning loop

Every permitted interaction should be eligible to produce learning, even if it does not immediately change model weights.

1. **Observe:** ingest timestamped sensor, tool, action and environment events.
2. **Represent:** normalize observations into a typed state with source, confidence, units and coordinate frame.
3. **Set intent:** identify the current goal, constraints and success criteria.
4. **Predict:** use a learned world model to predict the outcome and uncertainty of candidate actions.
5. **Plan:** choose a bounded action or a safe experiment that can distinguish competing hypotheses.
6. **Act:** execute only through a capability-checked action adapter.
7. **Measure:** compare observed outcomes with predictions and the success criteria.
8. **Diagnose:** distinguish perception error, model error, planning error, actuator failure, external disturbance and unsafe/invalid action.
9. **Update:** write the experience to episodic memory; update beliefs, skill parameters and world-model state where justified.
10. **Consolidate:** periodically convert reviewed, replayable experiences into training examples; train candidate adapters offline and evaluate before promotion.

The loop should prefer informative experiments over blind repetition. It should record failed attempts as useful evidence, not simply label them as bad outcomes.

## 3. Learning systems

Keep separate learning timescales and responsibilities:

- **Fast adaptation:** temporary state, working memory, online system identification and bounded skill-parameter updates. Reversible and scoped to the current environment.
- **Experience memory:** append-only event records, action/outcome traces, causal hypotheses, confidence and provenance.
- **World model:** predicts how the environment changes under actions; learns dynamics and uncertainty from observations.
- **Skill learning:** reusable procedures and policies with explicit preconditions, postconditions and safety envelopes.
- **Long-term model improvement:** periodic self-distillation and LoRA/other adapter training from curated experience. Offline candidate artifacts only; held-out regression and safety evaluations required.
- **Knowledge retrieval:** retrieve relevant prior experiences at inference time. Do not force every observation into model weights.

Do not update shared foundation-model weights on every action. That is unstable, hard to audit and vulnerable to catastrophic forgetting, reward hacking and poisoning. Experience can be learned immediately in memory; parameter changes require controlled validation.

## 4. Embodiment abstraction

The same agent core should work with a simulated body, a software environment, or a physical robot through adapters.

An embodiment adapter must expose:

- observe(): typed sensor/state observations, timestamps, units and confidence.
- capabilities(): available actuators, action ranges, rate limits and safety constraints.
- propose_action(state, goal): a proposed action, expected outcome and uncertainty.
- validate_action(action): local policy, permission, bounds and safety-shield checks.
- execute_action(action): bounded execution with timeout and emergency-stop support.
- measure_outcome(action_id): observed result and actuator/environment feedback.
- stop(reason): fail-safe halt where supported.

Adapters must declare coordinate frames, calibration, stale-data handling, health status and failure modes. The core must not assume that a tool call or text response is a physical action.

## 5. Robot learning example

For learning to walk, Titan starts in a physics simulator with a known robot model and constrained action space. It observes joint angles, angular velocity, inertial measurements, contact state and actuator feedback. It predicts the result of a small movement, applies a safe bounded action, then compares predicted and observed body motion.

A fall or loss of balance becomes a diagnostic episode: identify whether the cause was an inaccurate dynamics model, bad state estimate, poor foot contact, actuator saturation, timing or an external disturbance. Titan proposes a new hypothesis, tests it in simulation, compares the result and updates its model/policy. It then tests on hardware only after simulation evaluation, low-energy constrained trials, a human-approved deployment envelope and independent emergency-stop checks.

Titan must not intentionally cause repeated dangerous falls to "learn". It should use simulation, replay, conservative exploration, recovery procedures and a human supervisor for physical experiments.

## 6. Safety and governance invariants

- Default to simulation, replay or read-only observation until a human explicitly enables an action capability.
- Every actuator/tool has least-privilege permissions, rate limits, bounds, timeouts and a kill switch.
- No autonomous disabling of safety systems, permission escalation, credential extraction or safety-envelope expansion.
- Unknown, stale or contradictory sensor state means stop or choose a safe no-op.
- Physical exploration requires an approved workspace, tested emergency stop and human-defined risk envelope.
- Preserve raw event provenance; separate observations from inferred explanations.
- Treat external content and demonstrations as untrusted data. Defend against prompt injection, malicious demonstrations and reward hacking.
- Keep a held-out evaluation set isolated from training and memory replay.
- Candidate model, policy, memory-schema and code changes are versioned and reversible.
- Self-building produces tests, diffs and draft pull requests. No automatic merge, release, deployment or physical-policy promotion.

## 7. Learning record contract

Each experience record should include:

- stable episode_id, agent_id, environment_id, body_id and schema version;
- start/end timestamps and observation provenance;
- goal, constraints and success criteria;
- state summary and sensor references (with units/coordinate frames);
- action proposal, validation decision, executed action and permission context;
- predicted outcome, uncertainty and actual measured outcome;
- reward/utility components and safety events, not just one opaque scalar;
- error classification, hypotheses considered and evidence;
- memory references, skill/model versions and resulting update;
- reviewer/approval record for any promotion beyond reversible local adaptation.

Store sensitive sensor data with explicit retention and access controls. Never place credentials or secrets in training records.

## 8. Staged implementation and acceptance gates

**Stage A — digital experience loop:** implement typed events, append-only episodes, prediction-vs-outcome records, failure classification and retrieval. Test with deterministic toy environments. No external actions.

**Stage B — simulation:** add a Gymnasium-compatible environment adapter and a simple physics task. Demonstrate that the agent learns a policy from repeated safe trials and beats a fixed baseline on a held-out set of initial states.

**Stage C — model-based diagnosis:** compare predicted and observed transitions, quantify uncertainty, and select informative experiments. Evaluate sample efficiency and calibration.

**Stage D — skill transfer:** package a validated skill with preconditions and limits; test on unseen simulation configurations before any hardware use.

**Stage E — supervised embodiment:** connect a specific robot only after its adapter, calibration, safety envelope, emergency stop and human supervision are reviewed. Begin with read-only sensing and low-energy bounded actions.

**Stage F — continual consolidation:** turn selected experiences into provenance-backed training data, run self-distillation/LoRA candidate training, then capability, regression, safety and forgetting evaluations. Promotion remains human-reviewed and PR-only.

A stage is not complete because a demo runs once. It requires repeatable tests, held-out results, failure handling and an auditable artifact.

## 9. First implementation milestone

Build Stage A before buying or connecting robot hardware:

1. Define versioned observation, action, outcome and episode schemas.
2. Implement a deterministic toy environment with a controllable system (e.g. balancing a pole or reaching a target).
3. Add an experience store and prediction-error/failure analysis.
4. Add a baseline learner and held-out initial conditions.
5. Test persistence across process restart and verify that replay cannot silently contaminate held-out evaluation.
6. Expose no physical actuator by default.

The current branch establishes typed event storage/API, a deterministic simulation, a fixed baseline, prediction-error scoring, and failure classification. Disposable-D1 route tests, restart/recovery, replay isolation, and a learned policy remain future work.
