/**
 * Request guard for privileged dashboard API routes.
 *
 * Artifact submission signs an upload with the local Bittensor hotkey, so it
 * must never be reachable by an arbitrary caller. The guard layers three
 * independent controls that need no UI changes:
 *
 *  1. Explicit opt-in. Submission stays disabled until the operator sets
 *     MINER_ENABLE_SUBMISSION=1 on the server.
 *  2. Host allow-list. The Host header must be a loopback name or listed in
 *     MINER_ALLOWED_HOSTS. This stops DNS-rebinding from a web page.
 *  3. Same-origin. A browser-supplied Origin must match the Host, and when no
 *     Origin is sent Sec-Fetch-Site must not say the request is cross-site.
 *     This stops cross-site request forgery from any page open in the
 *     operator's browser (a text/plain POST needs no CORS preflight).
 *
 * Limits, stated plainly: a non-browser client on the network can set any Host
 * header it likes, so these checks do not replace network isolation. The
 * dashboard scripts bind to 127.0.0.1; to reach it remotely use an SSH tunnel
 * or an authenticating reverse proxy instead of binding to a public interface.
 */

export type GuardEnvironment = {
  readonly MINER_ENABLE_SUBMISSION?: string | undefined;
  readonly MINER_ALLOWED_HOSTS?: string | undefined;
};

export type GuardOptions = {
  /** Require MINER_ENABLE_SUBMISSION=1 (submission). Preflight leaves it off. */
  readonly requireOptIn: boolean;
};

export type GuardDecision =
  | { readonly allowed: true }
  | { readonly allowed: false; readonly status: 403; readonly error: string };

type HeaderReader = { get(name: string): string | null };

const LOOPBACK_HOSTNAMES: readonly string[] = ["localhost", "127.0.0.1", "::1"];

const DISABLED_MESSAGE =
  "Artifact submission is disabled on this server. " +
  "Set MINER_ENABLE_SUBMISSION=1 in the server environment to enable it.";

const HOST_MESSAGE = "Request host is not allowed.";
const ORIGIN_MESSAGE = "Cross-origin requests are not allowed.";

function deny(error: string): GuardDecision {
  return { allowed: false, status: 403, error };
}

/** Extract the lowercase hostname from a Host header value, or null if malformed. */
export function hostnameFromHostHeader(hostHeader: string): string | null {
  const value = hostHeader.trim().toLowerCase();

  if (!value) {
    return null;
  }

  if (value.startsWith("[")) {
    const end = value.indexOf("]");

    if (end < 0) {
      return null;
    }

    const rest = value.slice(end + 1);

    if (rest !== "" && !/^:\d{1,5}$/.test(rest)) {
      return null;
    }

    return value.slice(1, end) || null;
  }

  if (value.indexOf(":") !== value.lastIndexOf(":")) {
    // An unbracketed value with several colons is not a valid Host header.
    return null;
  }

  const colon = value.lastIndexOf(":");
  const name = colon >= 0 ? value.slice(0, colon) : value;
  const port = colon >= 0 ? value.slice(colon + 1) : "";

  if (port !== "" && !/^\d{1,5}$/.test(port)) {
    return null;
  }

  return name || null;
}

function allowedHostnames(environment: GuardEnvironment): ReadonlySet<string> {
  const extra = (environment.MINER_ALLOWED_HOSTS ?? "")
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter((entry) => entry.length > 0);

  return new Set<string>([...LOOPBACK_HOSTNAMES, ...extra]);
}

export function evaluateAdminRequest(
  headers: HeaderReader,
  environment: GuardEnvironment,
  options: GuardOptions,
): GuardDecision {
  if (options.requireOptIn && environment.MINER_ENABLE_SUBMISSION !== "1") {
    return deny(DISABLED_MESSAGE);
  }

  const hostHeader = headers.get("host");
  const hostname = hostHeader === null ? null : hostnameFromHostHeader(hostHeader);

  if (hostHeader === null || hostname === null || !allowedHostnames(environment).has(hostname)) {
    return deny(HOST_MESSAGE);
  }

  const origin = headers.get("origin");

  if (origin !== null) {
    let originHost: string;

    try {
      originHost = new URL(origin).host.toLowerCase();
    } catch {
      // Covers the opaque "null" origin sent from sandboxed or file contexts.
      return deny(ORIGIN_MESSAGE);
    }

    if (originHost !== hostHeader.trim().toLowerCase()) {
      return deny(ORIGIN_MESSAGE);
    }

    return { allowed: true };
  }

  const fetchSite = headers.get("sec-fetch-site");

  if (fetchSite !== null && fetchSite !== "same-origin" && fetchSite !== "none") {
    return deny(ORIGIN_MESSAGE);
  }

  return { allowed: true };
}