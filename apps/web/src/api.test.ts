import { describe, it, expect } from "vitest";
import { readError } from "./api";

function mockResponse(
  status: number,
  statusText: string,
  body: string,
): Response {
  return new Response(body, { status, statusText });
}

describe("readError", () => {
  it("returns statusText when body is empty", async () => {
    const r = new Response(null, { status: 500, statusText: "Server Error" });
    expect(await readError(r)).toBe("Server Error");
  });

  it("returns HTTP status when statusText is empty", async () => {
    const r = new Response(null, { status: 500 });
    expect(await readError(r)).toBe("HTTP 500");
  });

  it("returns FastAPI string detail", async () => {
    const r = mockResponse(
      400,
      "Bad Request",
      JSON.stringify({ detail: "Invalid credentials" }),
    );
    expect(await readError(r)).toBe("Invalid credentials");
  });

  it("formats Pydantic validation errors", async () => {
    const r = mockResponse(
      422,
      "Unprocessable Entity",
      JSON.stringify({
        detail: [
          { loc: ["body", "email"], msg: "field required", type: "missing" },
          {
            loc: ["body", "password"],
            msg: "Value error, too short",
            type: "value_error",
          },
        ],
      }),
    );
    expect(await readError(r)).toBe(
      "email: field required; password: too short",
    );
  });

  it("returns raw text for non-JSON responses", async () => {
    const r = mockResponse(500, "Server Error", "upstream timeout");
    expect(await readError(r)).toBe("upstream timeout");
  });

  it("returns raw text for JSON without detail", async () => {
    const r = mockResponse(400, "Bad Request", JSON.stringify({ foo: "bar" }));
    expect(await readError(r)).toBe(JSON.stringify({ foo: "bar" }));
  });
});
