import { describe, expect, it } from "vitest";
import {
  validateExperienceEpisode,
  validateExperienceEvent,
  replayExperienceEvents,
  validateExperienceAppend,
} from "../src/experiences";

describe("experience episode validation", () => {
  it("accepts a scoped simulation episode", () => {
    expect(validateExperienceEpisode({
      id: "episode_0001",
      environmentId: "toy-balance",
      goal: "Keep the pole balanced",
      mode: "simulation",
    })).toMatchObject({
      ok: true,
      value: {
        id: "episode_0001",
        environmentId: "toy-balance",
        mode: "simulation",
      },
    });
  });

  it("allows read-only observation but rejects physical control modes", () => {
    expect(validateExperienceEpisode({
      environmentId: "desktop",
      goal: "Observe the current workspace",
      mode: "read_only",
    }).ok).toBe(true);

    const result = validateExperienceEpisode({
      environmentId: "robot",
      goal: "Move forward",
      mode: "physical",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("physical control is not enabled");
  });

  it("rejects unknown episode fields and invalid identifiers", () => {
    expect(validateExperienceEpisode({
      environmentId: "toy",
      goal: "Learn",
      mode: "simulation",
      execute: true,
    }).ok).toBe(false);
    expect(validateExperienceEpisode({
      id: "bad id",
      environmentId: "toy",
      goal: "Learn",
      mode: "simulation",
    }).ok).toBe(false);
  });
});

describe("experience event validation", () => {
  it("accepts observations with bounded typed state", () => {
    const result = validateExperienceEvent({
      type: "observation",
      occurredAt: "2026-11-11T00:00:00.000Z",
      payload: {
        source: "toy-balance",
        state: { angle: 0.12, velocity: -0.04, contact: true },
        confidence: 0.95,
        units: { angle: "radians" },
      },
    }, "simulation");
    expect(result.ok).toBe(true);
  });

  it("accepts prediction, outcome, and diagnosis records", () => {
    expect(validateExperienceEvent({
      type: "prediction",
      payload: { actionId: "step_01", expected: { angle: 0.1 }, uncertainty: 0.2 },
    }, "simulation").ok).toBe(true);

    expect(validateExperienceEvent({
      type: "outcome",
      payload: { actionId: "step_01", observed: { angle: 0.13 }, success: true, reward: 0.8 },
    }, "simulation").ok).toBe(true);

    expect(validateExperienceEvent({
      type: "diagnosis",
      payload: {
        category: "model_error",
        explanation: "The predicted angle differed from the observed angle.",
        evidence: ["prediction event", "outcome event"],
      },
    }, "simulation").ok).toBe(true);
  });

  it("records proposed actions but rejects physical action modes", () => {
    const valid = validateExperienceEvent({
      type: "action_proposed",
      payload: {
        actionId: "step_01",
        name: "apply_torque",
        parameters: { amount: 0.05 },
        mode: "simulation",
      },
    }, "simulation");
    expect(valid.ok).toBe(true);

    const invalid = validateExperienceEvent({
      type: "action_proposed",
      payload: {
        actionId: "step_02",
        name: "move_robot",
        parameters: { distance: 1 },
        mode: "physical",
      },
    }, "simulation");
    expect(invalid.ok).toBe(false);
  });

  it("requires event action modes to match the episode", () => {
    expect(validateExperienceEvent({
      type: "action_proposed",
      payload: {
        actionId: "step_01",
        name: "observe",
        parameters: {},
        mode: "simulation",
      },
    }, "read_only").ok).toBe(false);
  });

  it("rejects malformed, oversized, and unknown payload fields", () => {
    expect(validateExperienceEvent({
      type: "observation",
      payload: { source: "sensor", state: { angle: Number.NaN } },
    }, "simulation").ok).toBe(false);

    expect(validateExperienceEvent({
      type: "observation",
      payload: { source: "sensor", state: {}, instructions: "run this" },
    }, "simulation").ok).toBe(false);

    expect(validateExperienceEvent({
      type: "observation",
      payload: { source: "sensor", state: { note: "x".repeat(8100) } },
    }, "simulation").ok).toBe(false);
  });

  it("accepts a bounded episode end and rejects unknown event types", () => {
    expect(validateExperienceEvent({
      type: "episode_ended",
      payload: { summary: "Trial completed", success: true },
    }, "simulation").ok).toBe(true);

    expect(validateExperienceEvent({
      type: "execute",
      payload: {},
    }, "simulation").ok).toBe(false);
  });
});


describe("experience event replay", () => {
  const at = "2026-11-11T00:00:00.000Z";
  const event = (sequence: number, type: string, payload: Record<string, unknown>) => ({
    id: `event_${String(sequence).padStart(4, "0")}`,
    sequence,
    type,
    schemaVersion: 1,
    occurredAt: at,
    payload,
  });

  it("reconstructs a deterministic read-only episode projection", () => {
    const result = replayExperienceEvents([
      event(1, "observation", { source: "toy-balance", state: { angle: 0.12 } }),
      event(2, "prediction", { actionId: "step_01", expected: { angle: 0.1 }, uncertainty: 0.2 }),
      event(3, "action_proposed", {
        actionId: "step_01", name: "apply_torque", parameters: { amount: 0.05 }, mode: "simulation",
      }),
      event(4, "action_validated", { actionId: "step_01", approved: true, reason: "Simulation action is bounded" }),
      event(5, "outcome", { actionId: "step_01", observed: { angle: 0.11 }, success: true, reward: 0.9 }),
      event(6, "belief_update", { target: "world_model", summary: "Small positive torque reduces angle", confidence: 0.8 }),
      event(7, "episode_ended", { summary: "Trial completed", success: true }),
    ], "simulation");

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.value).toMatchObject({
      eventCount: 7,
      lastSequence: 7,
      ended: true,
      summary: "Trial completed",
      success: true,
      latestObservation: { angle: 0.12 },
      proposedActions: [{ actionId: "step_01" }],
      validations: [{ actionId: "step_01", approved: true }],
      outcomes: [{ actionId: "step_01", success: true }],
      beliefs: { world_model: { confidence: 0.8 } },
      readOnly: true,
      executedActions: 0,
    });
    expect(result.value.timeline.map(item => item.sequence)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it("rejects gaps, unsupported schemas, and records after episode closure", () => {
    const gap = replayExperienceEvents([
      event(1, "observation", { source: "sensor", state: { angle: 0.1 } }),
      event(3, "episode_ended", { success: true }),
    ], "simulation");
    expect(gap.ok).toBe(false);

    const unsupported = replayExperienceEvents([
      { ...event(1, "episode_ended", {}), schemaVersion: 2 },
    ], "simulation");
    expect(unsupported.ok).toBe(false);

    const afterEnd = replayExperienceEvents([
      event(1, "episode_ended", { success: true }),
      event(2, "observation", { source: "sensor", state: { angle: 0.1 } }),
    ], "simulation");
    expect(afterEnd.ok).toBe(false);
  });

  it("refuses to replay more than the bounded event window", () => {
    const events = Array.from({ length: 201 }, (_, index) =>
      event(index + 1, "observation", { source: "sensor", state: { angle: 0.1 } }),
    );
    expect(replayExperienceEvents(events, "simulation").ok).toBe(false);
  });

  it("rejects outcomes without a preceding approved action", () => {
    const result = replayExperienceEvents([
      event(1, "action_proposed", {
        actionId: "step_01", name: "apply_torque", parameters: { amount: 0.05 }, mode: "simulation",
      }),
      event(2, "outcome", { actionId: "step_01", observed: { angle: 0.1 } }),
    ], "simulation");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toContain("approved proposal");
  });
});


describe("experience append integrity", () => {
  const at = "2026-11-11T00:00:00.000Z";

  it("accepts a complete proposal, approval, and outcome sequence", () => {
    let history: unknown[] = [];
    const proposal = validateExperienceAppend(history, {
      id: "event_0001",
      type: "action_proposed",
      occurredAt: at,
      payload: {
        actionId: "step_01",
        name: "apply_torque",
        parameters: { amount: 0.05 },
        mode: "simulation",
      },
    }, "simulation");
    expect(proposal.ok).toBe(true);
    if (!proposal.ok) return;
    history = [...history, proposal.value];

    const approval = validateExperienceAppend(history, {
      id: "event_0002",
      type: "action_validated",
      occurredAt: at,
      payload: { actionId: "step_01", approved: true, reason: "Within simulator bounds" },
    }, "simulation");
    expect(approval.ok).toBe(true);
    if (!approval.ok) return;
    history = [...history, approval.value];

    const outcome = validateExperienceAppend(history, {
      id: "event_0003",
      type: "outcome",
      occurredAt: at,
      payload: { actionId: "step_01", observed: { angle: 0.1 }, success: true },
    }, "simulation");
    expect(outcome.ok).toBe(true);
    if (outcome.ok) expect(outcome.value.sequence).toBe(3);
  });

  it("rejects orphan approvals and outcomes after a rejected proposal", () => {
    const orphan = validateExperienceAppend([], {
      id: "event_0001",
      type: "action_validated",
      occurredAt: at,
      payload: { actionId: "step_01", approved: true, reason: "Approved" },
    }, "simulation");
    expect(orphan.ok).toBe(false);

    const history = [
      event(1, "action_proposed", {
        actionId: "step_01", name: "apply_torque", parameters: { amount: 0.05 }, mode: "simulation",
      }),
      event(2, "action_validated", {
        actionId: "step_01", approved: false, reason: "Rejected by safety check",
      }),
    ];
    const outcome = validateExperienceAppend(history, {
      id: "event_0003",
      type: "outcome",
      occurredAt: at,
      payload: { actionId: "step_01", observed: { angle: 0.1 } },
    }, "simulation");
    expect(outcome.ok).toBe(false);
  });

  it("rejects events after closure and refuses to exceed the replay window", () => {
    const closed = validateExperienceAppend([
      event(1, "episode_ended", { summary: "Done", success: true }),
    ], {
      id: "event_0002",
      type: "observation",
      occurredAt: at,
      payload: { source: "sensor", state: { angle: 0.1 } },
    }, "simulation");
    expect(closed.ok).toBe(false);

    const full = Array.from({ length: 200 }, (_, index) =>
      event(index + 1, "observation", { source: "sensor", state: { angle: 0.1 } }),
    );
    const capped = validateExperienceAppend(full, {
      id: "event_0201",
      type: "observation",
      occurredAt: at,
      payload: { source: "sensor", state: { angle: 0.1 } },
    }, "simulation");
    expect(capped.ok).toBe(false);
    if (!capped.ok) expect(capped.status).toBe(409);
  });
});
