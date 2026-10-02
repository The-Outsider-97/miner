"use client";

import {
  useEffect,
  useState,
} from "react";

import { MinerMark } from "./MinerMark";
import { useTao } from "./TaoContext";
import type { TaoCurrency } from "./types";

type Theme = "light" | "dark";

type Props = {
  panelOpen: boolean;
  onTogglePanel: () => void;
  onTop: () => void;
  isMining: boolean;
};

const STORAGE_KEY =
  "slai-miner-theme";

const CURRENCIES: readonly TaoCurrency[] =
  ["USD", "EUR", "GBP"];

const PROVIDERS: Record<
  string,
  { label: string; href: string }
> = {
  cryptoapis: {
    label: "Crypto APIs",
    href: "https://cryptoapis.io/",
  },
  freecryptoapi: {
    label: "FreeCryptoAPI",
    href: "https://freecryptoapi.com/",
  },
  coinapi: {
    label: "CoinAPI",
    href: "https://www.apibricks.io/products/coin-api",
  },
};

function displayPrice(
  raw: string,
  currency: TaoCurrency,
): string {
  const value = Number(raw);

  if (!Number.isFinite(value)) {
    return "Unavailable";
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

export function Header({
  panelOpen,
  onTogglePanel,
  onTop,
  isMining,
}: Props) {
  const [theme, setTheme] =
    useState<Theme>("dark");

  const {
    currency,
    setCurrency,
    snapshot,
    loading,
  } = useTao();

  useEffect(() => {
    const current =
      document.documentElement.dataset
        .theme;

    setTheme(
      current === "light"
        ? "light"
        : "dark",
    );
  }, []);

  const toggleTheme = () => {
    const nextTheme: Theme =
      theme === "dark"
        ? "light"
        : "dark";

    document.documentElement.dataset.theme =
      nextTheme;

    localStorage.setItem(
      STORAGE_KEY,
      nextTheme,
    );

    setTheme(nextTheme);
  };

  const market = snapshot?.market;

  const rawPrice =
    market?.prices?.[currency];

  const priceText = loading
    ? "Loading…"
    : market?.status === "unavailable" ||
        !rawPrice
      ? "TAO price unavailable"
      : displayPrice(
          rawPrice,
          currency,
        );

  const provider = market?.provider
    ? PROVIDERS[market.provider]
    : undefined;

  return (
    <header
      className="site-header"
      data-visible="true"
    >
      <div className="site-header__inner">
        <div className="site-header__left">
          <button
            className="menu-toggle"
            type="button"
            aria-expanded={panelOpen}
            aria-controls="miner-side-panel"
            aria-label={
              panelOpen
                ? "Close dashboard navigation"
                : "Open dashboard navigation"
            }
            onClick={onTogglePanel}
          >
            <span />
            <span />
            <span />
          </button>

          <button
            className="brand"
            type="button"
            aria-label="Return to top"
            onClick={onTop}
          >
            <MinerMark
              isMining={isMining}
              priority
            />

            <span className="brand__name">
              SLAI Miner SN67
            </span>

            <span
              className="brand__divider"
              aria-hidden="true"
            />

            <span className="brand__sub">
              Harnyx observability
            </span>
          </button>
        </div>

        <div className="site-header__actions">
          <div
            className="tao-price"
            data-state={
              market?.status ??
              (loading
                ? "loading"
                : "unavailable")
            }
          >
            <div className="tao-price__value">
              <span className="tao-price__unit">
                1 TAO
              </span>

              <strong>
                {priceText}
              </strong>
            </div>

            <label className="tao-price__selector">
              <span className="sr-only">
                TAO display currency
              </span>

              <select
                aria-label="TAO display currency"
                value={currency}
                onChange={(event) =>
                  setCurrency(
                    event.target
                      .value as TaoCurrency,
                  )
                }
              >
                {CURRENCIES.map(
                  (item) => (
                    <option
                      key={item}
                      value={item}
                    >
                      {item}
                    </option>
                  ),
                )}
              </select>
            </label>

            {provider ? (
              <a
                className="tao-price__source"
                href={provider.href}
                target="_blank"
                rel="noreferrer"
              >
                {provider.label}
              </a>
            ) : (
              <span className="tao-price__source">
                Price provider
              </span>
            )}

            {market?.status ===
            "stale" ? (
              <span className="tao-price__stale">
                stale
              </span>
            ) : null}

            {market?.updated_at ? (
              <span className="sr-only">
                Price timestamp{" "}
                {market.updated_at}
              </span>
            ) : null}
          </div>

          <button
            className="top-control"
            type="button"
            onClick={onTop}
            aria-label="Return to top"
          >
            <span aria-hidden="true">
              ↑
            </span>

            <span>Top</span>
          </button>

          <button
            className="theme-toggle"
            type="button"
            role="switch"
            aria-checked={
              theme === "dark"
            }
            aria-label={`Switch to ${
              theme === "dark"
                ? "light"
                : "dark"
            } theme`}
            onClick={toggleTheme}
          >
            <span aria-hidden="true">
              ☀
            </span>

            <span
              className="theme-toggle__track"
              aria-hidden="true"
            >
              <span className="theme-toggle__thumb" />
            </span>

            <span aria-hidden="true">
              ◐
            </span>
          </button>
        </div>
      </div>
    </header>
  );
}
