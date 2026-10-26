import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  evaluateAdminRequest,
  hostnameFromHostHeader,
  type GuardEnvironment,
} from "./adminGuard.ts";

function headers(values: Record<string, string>) {
  const lower = new Map(
    Object.entries(values).map(([key, value]) => [key.toLowerCase(), value]),
  );

  return { get: (name: string): string | null => lower.get(name.toLowerCase()) ?? null };
}

const ENABLED: GuardEnvironment = { MINER_ENABLE_SUBMISSION: "1" };
const SUBMIT = { requireOptIn: true } as const;
const PREFLIGHT = { requireOptIn: false } as const;

describe("hostnameFromHostHeader", () => {
  it("parses names, ports and bracketed IPv6", () => {
    assert.equal(hostnameFromHostHeader("localhost:3000"), "localhost");
    assert.equal(hostnameFromHostHeader("LOCALHOST"), "localhost");
    assert.equal(hostnameFromHostHeader("127.0.0.1:3000"), "127.0.0.1");
    assert.equal(hostnameFromHostHeader("[::1]:3000"), "::1");
    assert.equal(hostnameFromHostHeader("[::1]"), "::1");
  });

  it("rejects malformed values", () => {
    assert.equal(hostnameFromHostHeader(""), null);
    assert.equal(hostnameFromHostHeader("  "), null);
    assert.equal(hostnameFromHostHeader("::1"), null);
    assert.equal(hostnameFromHostHeader("[::1"), null);
    assert.equal(hostnameFromHostHeader("localhost:abc"), null);
    assert.equal(hostnameFromHostHeader("[::1]x"), null);
    assert.equal(hostnameFromHostHeader(":3000"), null);
  });
});

describe("evaluateAdminRequest - opt-in", () => {
  it("denies submission by default", () => {
    const decision = evaluateAdminRequest(headers({ host: "localhost:3000" }), {}, SUBMIT);
    assert.equal(decision.allowed, false);
    if (!decision.allowed) {
      assert.equal(decision.status, 403);
      assert.match(decision.error, /MINER_ENABLE_SUBMISSION=1/);
    }
  });

  it("requires the flag to be exactly 1", () => {
    for (const value of ["", "0", "true", "yes", " 1"]) {
      const decision = evaluateAdminRequest(
        headers({ host: "localhost:3000" }),
        { MINER_ENABLE_SUBMISSION: value },
        SUBMIT,
      );
      assert.equal(decision.allowed, false, `value ${JSON.stringify(value)}`);
    }
  });

  it("does not require opt-in for preflight", () => {
    const decision = evaluateAdminRequest(headers({ host: "localhost:3000" }), {}, PREFLIGHT);
    assert.equal(decision.allowed, true);
  });
});

describe("evaluateAdminRequest - host allow-list", () => {
  it("allows loopback hosts", () => {
    for (const host of ["localhost:3000", "127.0.0.1:3000", "[::1]:3000", "localhost"]) {
      const decision = evaluateAdminRequest(headers({ host }), ENABLED, SUBMIT);
      assert.equal(decision.allowed, true, host);
    }
  });

  it("denies unknown and missing hosts (DNS rebinding)", () => {
    for (const host of ["evil.example:3000", "192.168.1.20:3000", "localhost.evil.example"]) {
      const decision = evaluateAdminRequest(headers({ host }), ENABLED, SUBMIT);
      assert.equal(decision.allowed, false, host);
    }

    assert.equal(evaluateAdminRequest(headers({}), ENABLED, SUBMIT).allowed, false);
  });

  it("allows operator-listed hosts only", () => {
    const environment: GuardEnvironment = {
      MINER_ENABLE_SUBMISSION: "1",
      MINER_ALLOWED_HOSTS: " miner.internal , other.internal ",
    };

    assert.equal(
      evaluateAdminRequest(headers({ host: "miner.internal:8443" }), environment, SUBMIT).allowed,
      true,
    );
    assert.equal(
      evaluateAdminRequest(headers({ host: "unlisted.internal" }), environment, SUBMIT).allowed,
      false,
    );
  });
});

describe("evaluateAdminRequest - same origin", () => {
  it("allows a matching Origin", () => {
    const decision = evaluateAdminRequest(
      headers({ host: "localhost:3000", origin: "http://localhost:3000" }),
      ENABLED,
      SUBMIT,
    );
    assert.equal(decision.allowed, true);
  });

  it("denies a cross-site Origin even when Host is loopback (CSRF)", () => {
    const decision = evaluateAdminRequest(
      headers({ host: "localhost:3000", origin: "https://evil.example" }),
      ENABLED,
      SUBMIT,
    );
    assert.equal(decision.allowed, false);
  });

  it("denies a different port on the same host", () => {
    const decision = evaluateAdminRequest(
      headers({ host: "localhost:3000", origin: "http://localhost:4000" }),
      ENABLED,
      SUBMIT,
    );
    assert.equal(decision.allowed, false);
  });

  it("denies the opaque null origin and malformed origins", () => {
    for (const origin of ["null", "not a url", ""]) {
      const decision = evaluateAdminRequest(
        headers({ host: "localhost:3000", origin }),
        ENABLED,
        SUBMIT,
      );
      assert.equal(decision.allowed, false, JSON.stringify(origin));
    }
  });

  it("uses Sec-Fetch-Site when no Origin is sent", () => {
    const base = { host: "localhost:3000" };

    assert.equal(
      evaluateAdminRequest(headers({ ...base, "sec-fetch-site": "cross-site" }), ENABLED, SUBMIT)
        .allowed,
      false,
    );
    assert.equal(
      evaluateAdminRequest(headers({ ...base, "sec-fetch-site": "same-site" }), ENABLED, SUBMIT)
        .allowed,
      false,
    );
    assert.equal(
      evaluateAdminRequest(headers({ ...base, "sec-fetch-site": "same-origin" }), ENABLED, SUBMIT)
        .allowed,
      true,
    );
    assert.equal(
      evaluateAdminRequest(headers({ ...base, "sec-fetch-site": "none" }), ENABLED, SUBMIT).allowed,
      true,
    );
  });

  it("allows a header-less local client such as curl", () => {
    assert.equal(
      evaluateAdminRequest(headers({ host: "127.0.0.1:3000" }), ENABLED, SUBMIT).allowed,
      true,
    );
  });
});