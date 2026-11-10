import { describe, expect, it } from "vitest";
import {
  validateExperienceEpisode,
  validateExperienceEvent,
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
