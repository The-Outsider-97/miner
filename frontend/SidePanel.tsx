"use client";

import Image from "next/image";

import harnyxMark from "./assets/harnyx-mark.png";
import { useTao } from "./TaoContext";
import type {
  DashboardSnapshot,
  SectionDefinition,
  TaoCurrency,
} from "./types";

type Props = {
  open: boolean;
  sections: readonly SectionDefinition[];
  activeSection: string;
  data: DashboardSnapshot | null;
  onClose: () => void;
};

function StatusLine({
  label,
  value,
  state,
}: {
  label: string;
  value: string;
  state: string;
}) {
  return (
    <div className="side-status__row">
      <span
        className="status-dot"
        data-state={state}
        aria-hidden="true"
      />

      <span>{label}</span>

      <strong>{value}</strong>
    </div>
  );
}

function quoteValue(
  amount: string,
  price: string,
  currency: TaoCurrency,
): string | null {
  const tao = Number(amount);
  const quote = Number(price);

  if (
    !Number.isFinite(tao) ||
    !Number.isFinite(quote)
  ) {
    return null;
  }

  const value = tao * quote;

  if (currency === "BTC") {
    return `${value.toLocaleString(
      "en-US",
      {
        maximumFractionDigits: 8,
      },
    )} BTC`;
  }

  return new Intl.NumberFormat(
    "en-US",
    {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    },
  ).format(value);
}

export function SidePanel({
  open,
  sections,
  activeSection,
  data,
  onClose,
}: Props) {
  const {
    currency,
    setCurrency,
    snapshot,
    loading,
  } = useTao();

  const artifact =
    data?.artifact?.profile ?? "None";

  const benchmarkState =
    data?.backend.benchmark_store ??
    "loading";

  const slaiState =
    data?.slai.status ?? "loading";

  const harnyxState =
    data?.harnyx.status ??
    "loading";

  const earnings =
    snapshot?.earnings;

  const price =
    snapshot?.market.prices?.[
      currency
    ];

  const converted =
    earnings?.earned_tao && price
      ? quoteValue(
          earnings.earned_tao,
          price,
          currency,
        )
      : null;

  return (
    <>
      {open ? (
        <button
          className="side-panel__backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={onClose}
        />
      ) : null}

      <aside
        id="miner-side-panel"
        className="side-panel"
        data-open={open}
        aria-label="Dashboard navigation"
      >
        <div className="side-panel__top">
          <div className="side-panel__brand">
            <Image
              src={harnyxMark}
              alt=""
            />

            <div>
              <p className="side-panel__kicker">
                Subnet 67
              </p>

              <h2>Harnyx</h2>
            </div>
          </div>

          <p className="side-panel__description">
            Miner state, benchmark evidence, integration status, and explicitly confirmed artifact submission.
          </p>
        </div>

        <nav
          className="side-panel__toc"
          aria-label="On this dashboard"
        >
          <p className="side-panel__label">
            On this dashboard
          </p>

          <ol>
            {sections.map(
              (item, index) => (
                <li key={item.id}>
                  <a
                    href={`#${item.id}`}
                    data-active={
                      activeSection ===
                      item.id
                    }
                    aria-current={
                      activeSection ===
                      item.id
                        ? "location"
                        : undefined
                    }
                    onClick={onClose}
                  >
                    <span>
                      {String(
                        index + 1,
                      ).padStart(
                        2,
                        "0",
                      )}
                    </span>

                    <strong>
                      {item.label}
                    </strong>
                  </a>
                </li>
              ),
            )}
          </ol>
        </nav>

        <div className="side-panel__bottom">
          <p className="side-panel__label">
            Current state
          </p>

          <div className="side-status">
            <StatusLine
              label="Artifact"
              value={artifact}
              state={
                data?.artifact
                  ? "ready"
                  : "empty"
              }
            />

            <StatusLine
              label="Benchmark"
              value={benchmarkState}
              state={benchmarkState}
            />

            <StatusLine
              label="SLAI"
              value={slaiState}
              state={slaiState}
            />

            <StatusLine
              label="Harnyx"
              value={harnyxState}
              state={harnyxState}
            />
          </div>

          <div className="miner-earnings">
            <div className="miner-earnings__head">
              <p className="side-panel__label">
                Miner earnings
              </p>

              <select
                aria-label="Earnings display currency"
                value={currency}
                onChange={(event) =>
                  setCurrency(
                    event.target
                      .value as TaoCurrency,
                  )
                }
              >
                <option value="USD">
                  USD
                </option>

                <option value="EUR">
                  EUR
                </option>

                <option value="GBP">
                  GBP
                </option>

                <option value="BTC">
                  BTC
                </option>
              </select>
            </div>

            {loading ? (
              <p className="miner-earnings__unavailable">
                Loading earnings…
              </p>
            ) : earnings?.status ===
                "available" ||
              earnings?.status ===
                "zero" ? (
              <>
                <strong className="miner-earnings__tao">
                  {earnings.earned_tao} TAO
                </strong>

                <span className="miner-earnings__quote">
                  {converted
                    ? `≈ ${converted}`
                    : "Conversion unavailable"}

                  {snapshot?.market
                    .status ===
                  "stale"
                    ? " · stale rate"
                    : ""}
                </span>
              </>
            ) : (
              <p className="miner-earnings__unavailable">
                Earnings unavailable
              </p>
            )}
          </div>

          <div className="side-panel__foot">
            <span
              className="status-dot"
              data-state="ready"
              aria-hidden="true"
            />

            <span>
              Read-only except confirmed submit
            </span>
          </div>
        </div>
      </aside>
    </>
  );
}
