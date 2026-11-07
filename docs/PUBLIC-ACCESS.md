# Public access

**Live public preview:** https://titan-ai-core.harryjees.workers.dev/

Titan's API supports anonymous public visitors without requiring account registration or a manually supplied token.

## Session bootstrap

The browser calls:

```http
POST /public/session
```

No request body or authorization header is required. Cloudflare supplies the visitor IP address. A successful response returns a random bearer capability:

```json
{
  "ok": true,
  "accessToken": "pub_...",
  "tokenType": "Bearer",
  "expiresAt": "..."
}
```

The client stores this token locally and sends it as `Authorization: Bearer <accessToken>` on chat and private-session endpoints. The token is a capability: do not place it in URLs, logs, analytics, or shared links. A visitor's memory and conversation history are scoped to the random session identity and are not shared with other visitors.

## Anonymous-use limits

- Maximum 8 new public sessions per client IP per UTC day.
- Maximum 60 chat requests per client IP per UTC day, across rotated sessions.
- Maximum 30 chat requests per anonymous session per UTC day (or the lower configured global limit).
- Sessions expire after 30 days.
- Session tokens are stored as SHA-256 hashes; raw tokens are returned only once.
- Existing bearer-token and admin-token paths remain available and unchanged.
- Public access does not expose admin knowledge-ingestion or evaluation routes.

The session tables are created additively with `CREATE TABLE IF NOT EXISTS` when public access is first used. No existing rows, credentials, or auth-map entries are modified.

## Frontend integration

The Worker now serves a self-contained responsive chat interface at `/`; opening the Worker root automatically bootstraps a session and sends chat requests to the same origin. The UI keeps the capability in browser-local storage, never puts it in a URL, and uses text-only rendering for model output. Do not ship a shared bearer token in frontend source code. The interface and API still need a staged deployment and live end-to-end check before sharing the public URL.
