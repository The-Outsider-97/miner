"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  ArtifactCandidate,
  ArtifactPreflight,
  ArtifactState,
  SubmissionResult,
  SubmissionStatus,
} from "./types";

type Props = {
  currentArtifact: ArtifactState | null;
};

type ArtifactListResponse = {
  ok: boolean;
  artifacts?: ArtifactCandidate[];
  error?: string;
};

type PreflightResponse = {
  ok: boolean;
  preflight?: ArtifactPreflight;
  error?: string;
};

type SubmitResponse = {
  ok: boolean;
  state?: SubmissionStatus;
  result?: SubmissionResult;
  error?: string;
};

const shortHash = (value: string) =>
  `${value.slice(0, 12)}…`;

const formatBytes = (
  value: number | null,
) => {
  if (value === null) {
    return "Not available";
  }

  if (value < 1024) {
    return `${value} B`;
  }

  return `${(
    value / 1024
  ).toFixed(1)} KB`;
};

export function ArtifactSubmission({
  currentArtifact,
}: Props) {
  const [artifacts, setArtifacts] =
    useState<ArtifactCandidate[]>([]);

  const [selectedHash, setSelectedHash] =
    useState("");

  const [state, setState] =
    useState<SubmissionStatus>("idle");

  const [preflight, setPreflight] =
    useState<ArtifactPreflight | null>(
      null,
    );

  const [result, setResult] =
    useState<SubmissionResult | null>(
      null,
    );

  const [error, setError] =
    useState<string | null>(null);

  const [
    allowResubmit,
    setAllowResubmit,
  ] = useState(false);

  const dialogRef =
    useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const controller =
      new AbortController();

    fetch("/api/artifacts", {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(
        async (
          response,
        ): Promise<ArtifactListResponse> => {
          const body =
            (await response.json()) as ArtifactListResponse;

          if (
            !response.ok ||
            !body.ok
          ) {
            throw new Error(
              body.error ??
                "Artifact list unavailable.",
            );
          }

          return body;
        },
      )
      .then((body) => {
        const next =
          body.artifacts ?? [];

        setArtifacts(next);

        const current =
          currentArtifact?.hash
            ? next.find(
                (item) =>
                  item.sha256 ===
                  currentArtifact.hash,
              )
            : undefined;

        setSelectedHash(
          current?.sha256 ??
            next[0]?.sha256 ??
            "",
        );
      })
      .catch((reason: unknown) => {
        if (
          reason instanceof DOMException &&
          reason.name === "AbortError"
        ) {
          return;
        }

        setError(
          reason instanceof Error
            ? reason.message
            : "Artifact list unavailable.",
        );
      });

    return () =>
      controller.abort();
  }, [currentArtifact?.hash]);

  const selected = useMemo(
    () =>
      artifacts.find(
        (artifact) =>
          artifact.sha256 ===
          selectedHash,
      ) ?? null,
    [
      artifacts,
      selectedHash,
    ],
  );

  const startSubmission =
    async () => {
      if (!selectedHash) {
        return;
      }

      setState("validating");
      setError(null);
      setResult(null);
      setAllowResubmit(false);

      try {
        const response = await fetch(
          "/api/artifacts/preflight",
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              artifact_sha256:
                selectedHash,
            }),
          },
        );

        const body =
          (await response.json()) as PreflightResponse;

        if (
          !response.ok ||
          !body.ok ||
          !body.preflight
        ) {
          throw new Error(
            body.error ??
              "Artifact preflight failed.",
          );
        }

        setPreflight(body.preflight);

        if (!body.preflight.eligible) {
          setState("failed");
          return;
        }

        setState("ready");

        dialogRef.current?.showModal();
      } catch (reason: unknown) {
        setState("failed");

        setError(
          reason instanceof Error
            ? reason.message
            : "Artifact preflight failed.",
        );
      }
    };

  const confirmSubmission =
    async () => {
      if (
        !preflight ||
        !preflight.eligible
      ) {
        return;
      }

      if (
        preflight.duplicate_upload &&
        !allowResubmit
      ) {
        return;
      }

      dialogRef.current?.close();

      setState("submitting");
      setError(null);

      try {
        const response = await fetch(
          "/api/artifacts/submit",
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              artifact_sha256:
                preflight.sha256,
              confirm: true,
              allow_resubmit:
                allowResubmit,
            }),
          },
        );

        const body =
          (await response.json()) as SubmitResponse;

        if (
          !response.ok ||
          !body.ok ||
          !body.result
        ) {
          setState(
            body.state === "rejected"
              ? "rejected"
              : "failed",
          );

          setError(
            body.error ??
              "Artifact submission failed.",
          );

          return;
        }

        setResult(body.result);

        setState(
          body.result.status,
        );
      } catch {
        setState("failed");

        setError(
          "Artifact submission failed.",
        );
      }
    };

  return (
    <div className="artifact-submission">
      <div className="subsection__heading">
        <div>
          <h3>Submission</h3>

          <p>
            Explicit, server-side Harnyx artifact upload. No wallet material is exposed to the browser.
          </p>
        </div>
      </div>

      {artifacts.length === 0 ? (
        <div className="empty-state">
          No generated artifact manifests are available for submission.
        </div>
      ) : (
        <div className="submission-layout">
          <label className="submission-select">
            <span>
              Artifact candidate
            </span>

            <select
              value={selectedHash}
              disabled={
                state ===
                  "validating" ||
                state ===
                  "submitting"
              }
              onChange={(event) => {
                setSelectedHash(
                  event.target.value,
                );

                setPreflight(null);
                setResult(null);
                setState("idle");
                setError(null);
              }}
            >
              {artifacts.map(
                (artifact) => (
                  <option
                    key={
                      artifact.sha256
                    }
                    value={
                      artifact.sha256
                    }
                  >
                    {artifact.profile ??
                      "Unknown"}{" "}
                    ·{" "}
                    {shortHash(
                      artifact.sha256,
                    )}
                  </option>
                ),
              )}
            </select>
          </label>

          {selected ? (
            <dl className="submission-details">
              <div>
                <dt>Profile</dt>
                <dd>
                  {selected.profile ??
                    "Unavailable"}
                </dd>
              </div>

              <div>
                <dt>SHA-256</dt>
                <dd>
                  <code>
                    {selected.sha256}
                  </code>
                </dd>
              </div>

              <div>
                <dt>Size</dt>
                <dd>
                  {formatBytes(
                    selected.size_bytes,
                  )}
                </dd>
              </div>

              <div>
                <dt>
                  Manifest validation
                </dt>
                <dd>
                  {selected.manifest_validated
                    ? "Recorded"
                    : "Not recorded"}
                </dd>
              </div>
            </dl>
          ) : null}

          <button
            className="submission-button"
            type="button"
            disabled={
              !selected ||
              state ===
                "validating" ||
              state ===
                "submitting"
            }
            onClick={
              startSubmission
            }
          >
            {state === "validating"
              ? "Validating artifact…"
              : state ===
                  "submitting"
                ? "Submitting…"
                : "Submit artifact"}
          </button>
        </div>
      )}

      {preflight ? (
        <div className="preflight-results">
          <h4>
            Preflight validation
          </h4>

          <ul>
            {preflight.checks.map(
              (check) => (
                <li
                  key={check.name}
                  data-passed={
                    check.passed
                  }
                >
                  <strong>
                    {check.passed
                      ? "Passed"
                      : "Failed"}
                  </strong>

                  <span>
                    {check.detail}
                  </span>
                </li>
              ),
            )}
          </ul>
        </div>
      ) : null}

      {state ===
      "uploaded_unconfirmed" ? (
        <div
          className="submission-result"
          aria-live="polite"
        >
          <strong>
            Upload acknowledged
          </strong>

          <p>
            {result?.message}
          </p>

          {result?.artifact_id ? (
            <p>
              Artifact ID:{" "}
              <code>
                {
                  result.artifact_id
                }
              </code>
            </p>
          ) : null}

          {result?.content_hash ? (
            <p>
              SHA-256:{" "}
              <code>
                {
                  result.content_hash
                }
              </code>
            </p>
          ) : null}

          <p>
            Acceptance and batch
            participation remain
            unverified.
          </p>
        </div>
      ) : null}

      {state === "rejected" ? (
        <div
          className="submission-result"
          data-state="error"
          aria-live="polite"
        >
          <strong>
            Harnyx rejected the upload
          </strong>

          <p>
            {error ??
              "Submission rejected."}
          </p>
        </div>
      ) : null}

      {state === "failed" &&
      error ? (
        <div
          className="submission-result"
          data-state="error"
          aria-live="polite"
        >
          <strong>
            Submission failed
          </strong>

          <p>{error}</p>
        </div>
      ) : null}

      <dialog
        ref={dialogRef}
        className="submission-dialog"
        aria-labelledby="submission-dialog-title"
        aria-describedby="submission-dialog-description"
        onClose={() =>
          setAllowResubmit(false)
        }
      >
        <h3 id="submission-dialog-title">
          Submit{" "}
          {preflight?.profile ??
            "artifact"}{" "}
          to Harnyx SN67?
        </h3>

        <p id="submission-dialog-description">
          This performs a real external artifact upload using the server-side configured Bittensor hotkey.
        </p>

        <dl>
          <div>
            <dt>SHA-256</dt>
            <dd>
              <code>
                {preflight?.sha256}
              </code>
            </dd>
          </div>

          <div>
            <dt>Size</dt>
            <dd>
              {formatBytes(
                preflight?.size_bytes ??
                  null,
              )}
            </dd>
          </div>

          <div>
            <dt>
              Harnyx validation
            </dt>
            <dd>
              {preflight?.eligible
                ? "Passed"
                : "Failed"}
            </dd>
          </div>
        </dl>

        {preflight?.duplicate_upload ? (
          <label className="submission-resubmit">
            <input
              type="checkbox"
              checked={allowResubmit}
              onChange={(event) =>
                setAllowResubmit(
                  event.target
                    .checked,
                )
              }
            />

            <span>
              This exact immutable artifact hash was already uploaded. I explicitly want to resubmit it.
            </span>
          </label>
        ) : null}

        <div className="submission-dialog__actions">
          <button
            type="button"
            autoFocus
            onClick={() =>
              dialogRef.current?.close()
            }
          >
            Cancel
          </button>

          <button
            className="submission-button"
            type="button"
            disabled={
              !preflight?.eligible ||
              (preflight.duplicate_upload &&
                !allowResubmit)
            }
            onClick={
              confirmSubmission
            }
          >
            Confirm submission
          </button>
        </div>
      </dialog>
    </div>
  );
}