"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type {
  TaoCurrency,
  TaoSnapshot,
} from "./types";

const STORAGE_KEY =
  "slai-miner-tao-currency";

const REFRESH_MS = 300_000;

const SUPPORTED: readonly TaoCurrency[] = [
  "USD",
  "EUR",
  "GBP",
  "BTC",
];

type TaoContextValue = {
  currency: TaoCurrency;
  setCurrency: (
    currency: TaoCurrency,
  ) => void;
  snapshot: TaoSnapshot | null;
  loading: boolean;
  refresh: () => void;
};

const TaoContext =
  createContext<TaoContextValue | null>(
    null,
  );

function isCurrency(
  value: string | null,
): value is TaoCurrency {
  return SUPPORTED.includes(
    value as TaoCurrency,
  );
}

export function TaoProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [currency, setCurrencyState] =
    useState<TaoCurrency>("USD");

  const [snapshot, setSnapshot] =
    useState<TaoSnapshot | null>(null);

  const [loading, setLoading] =
    useState(true);

  const controllerRef =
    useRef<AbortController | null>(null);

  const lastFetchRef = useRef(0);

  useEffect(() => {
    const stored =
      localStorage.getItem(STORAGE_KEY);

    if (isCurrency(stored)) {
      setCurrencyState(stored);
    }
  }, []);

  const setCurrency = useCallback(
    (next: TaoCurrency) => {
      setCurrencyState(next);

      localStorage.setItem(
        STORAGE_KEY,
        next,
      );
    },
    [],
  );

  const load = useCallback(() => {
    controllerRef.current?.abort();

    const controller =
      new AbortController();

    controllerRef.current = controller;
    lastFetchRef.current = Date.now();

    fetch("/api/tao", {
      cache: "no-store",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            "TAO state unavailable.",
          );
        }

        return response.json() as Promise<TaoSnapshot>;
      })
      .then((value) => {
        if (
          value.schema !==
          "slai-miner-tao-v1"
        ) {
          throw new Error(
            "Unsupported TAO schema.",
          );
        }

        setSnapshot(value);
      })
      .catch((error: unknown) => {
        if (
          error instanceof DOMException &&
          error.name === "AbortError"
        ) {
          return;
        }

        setSnapshot(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    load();

    const interval = window.setInterval(
      load,
      REFRESH_MS,
    );

    const visibility = () => {
      if (
        document.visibilityState ===
          "visible" &&
        Date.now() -
          lastFetchRef.current >=
          REFRESH_MS
      ) {
        load();
      }
    };

    document.addEventListener(
      "visibilitychange",
      visibility,
    );

    return () => {
      controllerRef.current?.abort();

      window.clearInterval(interval);

      document.removeEventListener(
        "visibilitychange",
        visibility,
      );
    };
  }, [load]);

  return (
    <TaoContext.Provider
      value={{
        currency,
        setCurrency,
        snapshot,
        loading,
        refresh: load,
      }}
    >
      {children}
    </TaoContext.Provider>
  );
}

export function useTao(): TaoContextValue {
  const value = useContext(TaoContext);

  if (value === null) {
    throw new Error(
      "useTao must be used inside TaoProvider.",
    );
  }

  return value;
}