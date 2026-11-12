import { describe, expect, it } from "vitest";
import {
  validateExperienceEpisode,
  validateExperienceEvent,
  replayExperienceEvents,
  validateExperienceAppend,
  listExperienceEvents,
  parseExperienceEventPage,
} from "../src/experiences";
import type { Env } from "../src/types";

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
  const actionEvent = (
    sequence: number,
    type: "action_proposed" | "action_validated" | "outcome",
    payload: Record<string, unknown>,
  ) => ({
    id: `event_${String(sequence).padStart(4, "0")}`,
    sequence,
    type,
    schemaVersion: 1,
    occurredAt: at,
    payload,
  });

  const proposal = actionEvent(1, "action_proposed", {
    actionId: "step_01",
    name: "apply_torque",
    parameters: { amount: 0.05 },
    mode: "simulation",
  });
  const approval = actionEvent(2, "action_validated", {
    actionId: "step_01",
    approved: true,
    reason: "Within simulator bounds",
  });
  const rejection = actionEvent(2, "action_validated", {
    actionId: "step_01",
    approved: false,
    reason: "Rejected by safety check",
  });

  it("accepts a complete proposal, approval, and outcome sequence", () => {
    const proposed = validateExperienceAppend({
      type: "action_proposed",
      occurredAt: at,
      payload: proposal.payload,
    }, "simulation", [], 1);
    expect(proposed.ok).toBe(true);

    const validated = validateExperienceAppend({
      type: "action_validated",
      occurredAt: at,
      payload: approval.payload,
    }, "simulation", [proposal], 2);
    expect(validated.ok).toBe(true);

    const outcome = validateExperienceAppend({
      type: "outcome",
      occurredAt: at,
      payload: { actionId: "step_01", observed: { angle: 0.1 }, success: true },
    }, "simulation", [proposal, approval], 3);
    expect(outcome.ok).toBe(true);
    if (outcome.ok) expect(outcome.value.sequence).toBe(3);
  });

  it("rejects orphan, duplicate, and unapproved action transitions", () => {
    const orphan = validateExperienceAppend({
      type: "action_validated",
      occurredAt: at,
      payload: approval.payload,
    }, "simulation", [], 1);
    expect(orphan.ok).toBe(false);

    const duplicateProposal = validateExperienceAppend({
      type: "action_proposed",
      occurredAt: at,
      payload: proposal.payload,
    }, "simulation", [proposal], 2);
    expect(duplicateProposal.ok).toBe(false);

    const duplicateApproval = validateExperienceAppend({
      type: "action_validated",
      occurredAt: at,
      payload: approval.payload,
    }, "simulation", [proposal, approval], 3);
    expect(duplicateApproval.ok).toBe(false);

    const unapprovedOutcome = validateExperienceAppend({
      type: "outcome",
      occurredAt: at,
      payload: { actionId: "step_01", observed: { angle: 0.1 } },
    }, "simulation", [proposal, rejection], 3);
    expect(unapprovedOutcome.ok).toBe(false);
  });

  it("does not confuse the replay window with the append-storage limit", () => {
    const laterObservation = validateExperienceAppend({
      type: "observation",
      occurredAt: at,
      payload: { source: "sensor", state: { angle: 0.1 } },
    }, "simulation", [], 201);
    expect(laterObservation.ok).toBe(true);
  });
});


describe("experience event pagination", () => {
  const storedEvents = Array.from({ length: 5 }, (_, index) => ({
    id: `event_${index + 1}`,
    sequence: index + 1,
    event_type: "observation" as const,
    schema_version: 1,
    occurred_at: "2026-11-13T00:00:00.000Z",
    payload_json: JSON.stringify({
      source: "sensor",
      state: { angle: (index + 1) / 10 },
    }),
  }));

  function fakeEnv(rows: typeof storedEvents, owner = "user_1") {
    const DB = {
      prepare(sql: string) {
        let bindings: unknown[] = [];
        return {
          bind(...values: unknown[]) {
            bindings = values;
            return this;
          },
          async first() {
            if (!sql.includes("FROM agent_experience_episodes")) return null;
            const [userId, episodeId] = bindings;
            return userId === owner && episodeId === "episode_0001"
              ? { id: "episode_0001" }
              : null;
          },
          async all() {
            if (!sql.includes("FROM agent_experience_events")) return { results: [] };
            const [userId, episodeId, after, limit] = bindings;
            if (userId !== owner || episodeId !== "episode_0001") return { results: [] };
            return {
              results: rows
                .filter((row) => row.sequence > Number(after))
                .slice(0, Number(limit)),
            };
          },
        };
      },
    };
    return { DB } as unknown as Env;
  }

  it("uses safe defaults and rejects malformed or oversized cursors", () => {
    expect(parseExperienceEventPage(null, null)).toEqual({
      ok: true,
      value: { after: 0, limit: 200 },
    });
    expect(parseExperienceEventPage("-1", "20").ok).toBe(false);
    expect(parseExperienceEventPage("1.5", "20").ok).toBe(false);
    expect(parseExperienceEventPage("9007199254740992", "20").ok).toBe(false);
    expect(parseExperienceEventPage("0", "0").ok).toBe(false);
    expect(parseExperienceEventPage("0", "201").ok).toBe(false);
    expect(parseExperienceEventPage("0", "01").ok).toBe(false);
  });

  it("returns stable forward pages without dropping later events", async () => {
    const env = fakeEnv(storedEvents);

    const first = await listExperienceEvents(env, "user_1", "episode_0001", { after: 0, limit: 2 });
    expect(first?.events.map((event) => event.sequence)).toEqual([1, 2]);
    expect(first?.pagination).toEqual({ after: 0, limit: 2, nextAfter: 2, hasMore: true });

    const second = await listExperienceEvents(env, "user_1", "episode_0001", { after: 2, limit: 2 });
    expect(second?.events.map((event) => event.sequence)).toEqual([3, 4]);
    expect(second?.pagination).toEqual({ after: 2, limit: 2, nextAfter: 4, hasMore: true });

    const final = await listExperienceEvents(env, "user_1", "episode_0001", { after: 4, limit: 2 });
    expect(final?.events.map((event) => event.sequence)).toEqual([5]);
    expect(final?.pagination).toEqual({ after: 4, limit: 2, nextAfter: 5, hasMore: false });
  });

  it("keeps an empty-page cursor stable and enforces episode ownership", async () => {
    const env = fakeEnv(storedEvents);

    const empty = await listExperienceEvents(env, "user_1", "episode_0001", { after: 5, limit: 2 });
    expect(empty?.events).toEqual([]);
    expect(empty?.pagination).toEqual({ after: 5, limit: 2, nextAfter: 5, hasMore: false });

    const hidden = await listExperienceEvents(env, "user_2", "episode_0001", { after: 0, limit: 2 });
    expect(hidden).toBeNull();
  });
});
