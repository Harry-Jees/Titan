import type { Env } from "./types";

export type ExperienceMode = "simulation" | "read_only";
export type ExperienceEventType =
  | "observation"
  | "prediction"
  | "action_proposed"
  | "action_validated"
  | "outcome"
  | "diagnosis"
  | "belief_update"
  | "episode_ended";

type RecordValue = string | number | boolean | null;

export interface ExperienceEpisodeInput {
  id?: string;
  environmentId: string;
  goal: string;
  mode: ExperienceMode;
}

export interface ExperienceEventInput {
  type: ExperienceEventType;
  occurredAt: string;
  payload: Record<string, unknown>;
}

type Validation<T> = { ok: true; value: T } | { ok: false; error: string; status?: number };

const EVENT_TYPES = new Set<ExperienceEventType>([
  "observation",
  "prediction",
  "action_proposed",
  "action_validated",
  "outcome",
  "diagnosis",
  "belief_update",
  "episode_ended",
]);

const DIAGNOSIS_CATEGORIES = new Set([
  "perception_error",
  "model_error",
  "planning_error",
  "actuator_failure",
  "external_disturbance",
  "unsafe_action",
  "unknown",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function isShortText(value: unknown, max: number, min = 1): value is string {
  return typeof value === "string" && value.trim().length >= min && value.length <= max;
}

function isFiniteRange(value: unknown, min: number, max: number): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
}

function onlyKeys(value: Record<string, unknown>, allowed: string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key));
}

function isScalarRecord(value: unknown): value is Record<string, RecordValue> {
  if (!isRecord(value) || Object.keys(value).length > 32) return false;
  return Object.entries(value).every(([key, item]) => {
    if (!isShortText(key, 64)) return false;
    if (item === null || typeof item === "boolean") return true;
    if (typeof item === "number") return Number.isFinite(item);
    return typeof item === "string" && item.length <= 1000;
  });
}

function validActionId(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(value);
}

export function validateExperienceEpisode(input: unknown): Validation<ExperienceEpisodeInput> {
  if (!isRecord(input) || !onlyKeys(input, ["id", "environmentId", "goal", "mode"])) {
    return { ok: false, error: "Episode must contain only id, environmentId, goal, and mode." };
  }
  if (input.id !== undefined &&
      (typeof input.id !== "string" || !/^[A-Za-z0-9_-]{8,80}$/.test(input.id))) {
    return { ok: false, error: "Episode id must be 8–80 letters, numbers, underscores, or hyphens." };
  }
  if (typeof input.environmentId !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(input.environmentId)) {
    return { ok: false, error: "environmentId must be a short environment identifier." };
  }
  if (!isShortText(input.goal, 500)) {
    return { ok: false, error: "goal must be 1–500 characters." };
  }
  if (input.mode !== "simulation" && input.mode !== "read_only") {
    return { ok: false, error: "mode must be simulation or read_only; physical control is not enabled." };
  }
  return {
    ok: true,
    value: {
      ...(typeof input.id === "string" ? { id: input.id } : {}),
      environmentId: input.environmentId,
      goal: input.goal.trim(),
      mode: input.mode,
    },
  };
}

export function validateExperienceEvent(
  input: unknown,
  episodeMode: ExperienceMode,
): Validation<ExperienceEventInput> {
  if (!isRecord(input) || !onlyKeys(input, ["type", "occurredAt", "payload"])) {
    return { ok: false, error: "Event must contain only type, occurredAt, and payload." };
  }
  if (typeof input.type !== "string" || !EVENT_TYPES.has(input.type as ExperienceEventType)) {
    return { ok: false, error: "Unsupported experience event type." };
  }
  if (input.occurredAt !== undefined && typeof input.occurredAt !== "string") {
    return { ok: false, error: "occurredAt must be an ISO date-time string." };
  }
  const occurredAt = input.occurredAt === undefined ? new Date().toISOString() : input.occurredAt;
  const parsedDate = new Date(occurredAt);
  if (!Number.isFinite(parsedDate.getTime())) {
    return { ok: false, error: "occurredAt must be a valid date-time." };
  }
  if (!isRecord(input.payload)) {
    return { ok: false, error: "payload must be an object." };
  }

  let serialized: string;
  try {
    serialized = JSON.stringify(input.payload);
  } catch {
    return { ok: false, error: "payload must be valid JSON data." };
  }
  if (serialized.length > 8000) {
    return { ok: false, error: "payload exceeds the 8000-character limit." };
  }

  const payload = input.payload;
  const type = input.type as ExperienceEventType;
  let valid = false;

  switch (type) {
    case "observation":
      valid = onlyKeys(payload, ["state", "source", "confidence", "units"]) &&
        isScalarRecord(payload.state) &&
        isShortText(payload.source, 160) &&
        (payload.confidence === undefined || isFiniteRange(payload.confidence, 0, 1)) &&
        (payload.units === undefined ||
          (isRecord(payload.units) && Object.keys(payload.units).length <= 32 &&
            Object.entries(payload.units).every(([key, value]) =>
              isShortText(key, 64) && isShortText(value, 40))));
      break;
    case "prediction":
      valid = onlyKeys(payload, ["actionId", "expected", "uncertainty"]) &&
        validActionId(payload.actionId) &&
        isScalarRecord(payload.expected) &&
        isFiniteRange(payload.uncertainty, 0, 1);
      break;
    case "action_proposed":
      valid = onlyKeys(payload, ["actionId", "name", "parameters", "mode"]) &&
        validActionId(payload.actionId) &&
        typeof payload.name === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(payload.name) &&
        isScalarRecord(payload.parameters) &&
        payload.mode === episodeMode &&
        (payload.mode === "simulation" || payload.mode === "read_only");
      break;
    case "action_validated":
      valid = onlyKeys(payload, ["actionId", "approved", "reason"]) &&
        validActionId(payload.actionId) &&
        typeof payload.approved === "boolean" &&
        isShortText(payload.reason, 500);
      break;
    case "outcome":
      valid = onlyKeys(payload, ["actionId", "observed", "success", "reward", "error"]) &&
        validActionId(payload.actionId) &&
        isScalarRecord(payload.observed) &&
        (payload.success === undefined || typeof payload.success === "boolean") &&
        (payload.reward === undefined || isFiniteRange(payload.reward, -1000000, 1000000)) &&
        (payload.error === undefined || isFiniteRange(payload.error, 0, 1000000));
      break;
    case "diagnosis":
      valid = onlyKeys(payload, ["category", "explanation", "evidence"]) &&
        typeof payload.category === "string" && DIAGNOSIS_CATEGORIES.has(payload.category) &&
        isShortText(payload.explanation, 1000) &&
        (payload.evidence === undefined ||
          (Array.isArray(payload.evidence) && payload.evidence.length <= 8 &&
            payload.evidence.every((item) => isShortText(item, 300))));
      break;
    case "belief_update":
      valid = onlyKeys(payload, ["target", "summary", "confidence"]) &&
        ["state", "world_model", "skill"].includes(String(payload.target)) &&
        isShortText(payload.summary, 1000) &&
        isFiniteRange(payload.confidence, 0, 1);
      break;
    case "episode_ended":
      valid = onlyKeys(payload, ["summary", "success"]) &&
        (payload.summary === undefined || isShortText(payload.summary, 1000, 0)) &&
        (payload.success === undefined || typeof payload.success === "boolean");
      break;
  }

  if (!valid) {
    return { ok: false, error: "payload does not match the schema for " + type + "." };
  }
  return { ok: true, value: { type, occurredAt: parsedDate.toISOString(), payload } };
}

export async function createExperienceEpisode(
  env: Env,
  userId: string,
  input: unknown,
): Promise<Validation<{ id: string; environmentId: string; goal: string; mode: ExperienceMode; startedAt: string }>> {
  const validated = validateExperienceEpisode(input);
  if (!validated.ok) return validated;

  const episode = validated.value;
  const id = episode.id || crypto.randomUUID();
  const startedAt = new Date().toISOString();
  const result = await env.DB.prepare(
    "INSERT OR IGNORE INTO agent_experience_episodes(id,user_id,environment_id,goal,mode,status,started_at) VALUES(?,?,?,?,?,'open',?)"
  ).bind(id, userId, episode.environmentId, episode.goal, episode.mode, startedAt).run();

  if ((result.meta.changes || 0) !== 1) {
    return { ok: false, error: "An episode with that id already exists for this user." };
  }
  return { ok: true, value: { id, ...episode, startedAt } };
}

export async function listExperienceEpisodes(env: Env, userId: string) {
  const result = await env.DB.prepare(
    "SELECT e.id,e.environment_id,e.goal,e.mode,e.status,e.started_at,e.ended_at," +
    "(SELECT COUNT(*) FROM agent_experience_events v WHERE v.user_id=e.user_id AND v.episode_id=e.id) AS event_count," +
    "(SELECT MAX(sequence) FROM agent_experience_events v WHERE v.user_id=e.user_id AND v.episode_id=e.id) AS last_sequence " +
    "FROM agent_experience_episodes e WHERE e.user_id=? ORDER BY e.started_at DESC LIMIT 50"
  ).bind(userId).all<{
    id: string; environment_id: string; goal: string; mode: ExperienceMode;
    status: "open" | "closed"; started_at: string; ended_at: string | null;
    event_count: number; last_sequence: number | null;
  }>();

  return (result.results || []).map((row) => ({
    id: row.id,
    environmentId: row.environment_id,
    goal: row.goal,
    mode: row.mode,
    status: row.status,
    startedAt: row.started_at,
    endedAt: row.ended_at,
    eventCount: row.event_count,
    lastSequence: row.last_sequence,
  }));
}

export async function appendExperienceEvent(
  env: Env,
  userId: string,
  episodeId: string,
  input: unknown,
): Promise<Validation<{ id: string; sequence: number; type: ExperienceEventType; occurredAt: string }>> {
  if (!/^[A-Za-z0-9_-]{8,80}$/.test(episodeId)) {
    return { ok: false, error: "A valid episode id is required." };
  }
  const episode = await env.DB.prepare(
    "SELECT mode,status FROM agent_experience_episodes WHERE user_id=? AND id=?"
  ).bind(userId, episodeId).first<{ mode: ExperienceMode; status: "open" | "closed" }>();
  if (!episode) return { ok: false, error: "Episode not found.", status: 404 };
  if (episode.status !== "open") return { ok: false, error: "Episode is already closed.", status: 409 };

  const validated = validateExperienceEvent(input, episode.mode);
  if (!validated.ok) return validated;
  const event = validated.value;
  const id = crypto.randomUUID();
  const insert = env.DB.prepare(
    "INSERT INTO agent_experience_events(id,user_id,episode_id,sequence,event_type,schema_version,occurred_at,payload_json) " +
    "SELECT ?,?,?,COALESCE((SELECT MAX(sequence)+1 FROM agent_experience_events WHERE user_id=? AND episode_id=?),1),?,1,?,? " +
    "WHERE EXISTS(SELECT 1 FROM agent_experience_episodes WHERE user_id=? AND id=? AND status='open')"
  ).bind(
    id, userId, episodeId, userId, episodeId, event.type,
    event.occurredAt, JSON.stringify(event.payload), userId, episodeId,
  );

  let inserted = 0;
  if (event.type === "episode_ended") {
    const results = await env.DB.batch([
      insert,
      env.DB.prepare(
        "UPDATE agent_experience_episodes SET status='closed',ended_at=? " +
        "WHERE user_id=? AND id=? AND status='open' AND EXISTS(" +
        "SELECT 1 FROM agent_experience_events WHERE id=? AND user_id=? AND episode_id=?)"
      ).bind(event.occurredAt, userId, episodeId, id, userId, episodeId),
    ]);
    inserted = results[0]?.meta?.changes || 0;
  } else {
    const result = await insert.run();
    inserted = result.meta.changes || 0;
  }

  if (inserted !== 1) {
    return { ok: false, error: "Episode is no longer open.", status: 409 };
  }
  const row = await env.DB.prepare(
    "SELECT sequence FROM agent_experience_events WHERE id=? AND user_id=?"
  ).bind(id, userId).first<{ sequence: number }>();
  if (!row) return { ok: false, error: "The event could not be read after insertion." };
  return { ok: true, value: { id, sequence: row.sequence, type: event.type, occurredAt: event.occurredAt } };
}

export async function listExperienceEvents(env: Env, userId: string, episodeId: string) {
  const episode = await env.DB.prepare(
    "SELECT id FROM agent_experience_episodes WHERE user_id=? AND id=?"
  ).bind(userId, episodeId).first<{ id: string }>();
  if (!episode) return null;

  const result = await env.DB.prepare(
    "SELECT id,sequence,event_type,schema_version,occurred_at,payload_json " +
    "FROM agent_experience_events WHERE user_id=? AND episode_id=? ORDER BY sequence ASC LIMIT 200"
  ).bind(userId, episodeId).all<{
    id: string; sequence: number; event_type: ExperienceEventType;
    schema_version: number; occurred_at: string; payload_json: string;
  }>();

  return (result.results || []).map((row) => ({
    id: row.id,
    sequence: row.sequence,
    type: row.event_type,
    schemaVersion: row.schema_version,
    occurredAt: row.occurred_at,
    payload: JSON.parse(row.payload_json) as Record<string, unknown>,
  }));
}
