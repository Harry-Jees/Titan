import { describe, expect, it } from "vitest";
import { containsSensitiveContent, pairConversationRows } from "../src/training-pipeline";

function row(id: string, user: string, conversation: string, role: "user" | "assistant", content: string) {
  return { id, user_id: user, conversation_id: conversation, role, content, created_at: "2026-11-07 12:00:00" };
}

describe("opt-in training curation privacy", () => {
  it("rejects credential, contact and sensitive personal data", () => {
    expect(containsSensitiveContent("My email is harry@example.org")).toBe(true);
    expect(containsSensitiveContent("My diagnosis is a private condition")).toBe(true);
    expect(containsSensitiveContent("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456")).toBe(true);
    expect(containsSensitiveContent("Explain how SQL indexes work")).toBe(false);
  });

  it("pairs only user and assistant messages within the same user conversation", () => {
    const pairs = pairConversationRows([
      row("u1","user-a","conv-a","user","How do SQL indexes work?"),
      row("a1","user-a","conv-a","assistant","They help databases locate rows more efficiently."),
      row("u2","user-b","conv-a","user","Explain recursion."),
      row("a2","user-b","conv-a","assistant","Recursion solves a problem by calling itself on smaller inputs."),
      row("u3","user-a","conv-b","user","What is a hash?"),
    ]);
    expect(pairs).toHaveLength(2);
    expect(pairs[0].user.user_id).toBe("user-a");
    expect(pairs[1].user.user_id).toBe("user-b");
  });
});
