import type { Env } from "./types";
const DAILY_NEURON_LIMIT = 9000;
const INPUT_NEURONS_PER_TOKEN = 18182 / 1_000_000;
const OUTPUT_NEURONS_PER_TOKEN = 27273 / 1_000_000;
const EMBEDDING_NEURONS_PER_TOKEN = INPUT_NEURONS_PER_TOKEN; // conservative ceiling

/** Reserve against Cloudflare's 10,000-neuron free daily allocation before inference. */
export async function reserveAiNeurons(env: Env, inputCharacters: number, outputTokens: number,
  bucket = "chat", bucketLimit = 2000, embedding = false): Promise<boolean> {
  const estimatedInputTokens = Math.ceil(Math.max(0, inputCharacters) / 2);
  const neurons = Math.max(1, Math.ceil(
    estimatedInputTokens * (embedding ? EMBEDDING_NEURONS_PER_TOKEN : INPUT_NEURONS_PER_TOKEN) +
    (embedding ? 0 : Math.max(0, outputTokens) * OUTPUT_NEURONS_PER_TOKEN),
  ));
  const day = new Date().toISOString().slice(0, 10);
  const result = await env.DB.prepare(`
    INSERT INTO ai_daily_usage(day_utc,bucket,reserved_neurons)
    SELECT ?,?,?
    WHERE COALESCE((SELECT SUM(reserved_neurons) FROM ai_daily_usage WHERE day_utc=?),0)+? <= ?
      AND COALESCE((SELECT reserved_neurons FROM ai_daily_usage WHERE day_utc=? AND bucket=?),0)+? <= ?
    ON CONFLICT(day_utc,bucket)
    DO UPDATE SET reserved_neurons=reserved_neurons+excluded.reserved_neurons
    RETURNING reserved_neurons
  `).bind(day,bucket,neurons,day,neurons,DAILY_NEURON_LIMIT,day,bucket,neurons,bucketLimit)
    .first<{reserved_neurons:number}>();
  return !!result;
}
export const AI_BUDGETS = { dailyNeurons:9000, researchRunNeurons:3500, chatNeurons:2000, safetyMarginNeurons:1000 };
