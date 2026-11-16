import { describe, expect, it } from "vitest";
import { publicHome } from "../src/public";

describe("public Titan interface", () => {
  it("serves a self-contained no-store chat page", async () => {
    const response = publicHome();
    const html = await response.text();
    expect(response.headers.get("content-type")).toContain("text/html");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("content-security-policy")).toContain("frame-ancestors 'none'");
    expect(html).toContain("POST");
    expect(html).toContain("/public/session");
    expect(html).toContain("/chat");
    expect(html).toContain("Titan");
    expect(html).not.toContain("cdn.");
  });
});
