"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import remyMark from "./assets/remy3design-mark.png";

type Theme = "light" | "dark";

type Props = {
  panelOpen: boolean;
  onTogglePanel: () => void;
  onTop: () => void;
};

const STORAGE_KEY = "slai-miner-theme";

export function Header({ panelOpen, onTogglePanel, onTop }: Props) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const current = document.documentElement.dataset.theme;
    setTheme(current === "light" ? "light" : "dark");
  }, []);

  const toggleTheme = () => {
    const nextTheme: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nextTheme;
    localStorage.setItem(STORAGE_KEY, nextTheme);
    setTheme(nextTheme);
  };

  return (
    <header className="site-header" data-visible="true">
      <div className="site-header__inner">
        <div className="site-header__left">
          <button
            className="menu-toggle"
            type="button"
            aria-expanded={panelOpen}
            aria-controls="miner-side-panel"
            aria-label={panelOpen ? "Close dashboard navigation" : "Open dashboard navigation"}
            onClick={onTogglePanel}
          >
            <span />
            <span />
            <span />
          </button>

          <button className="brand" type="button" aria-label="Return to top" onClick={onTop}>
            <Image src={remyMark} alt="" priority />
            <span className="brand__name">SLAI Miner SN67</span>
            <span className="brand__divider" aria-hidden="true" />
            <span className="brand__sub">Harnyx observability</span>
          </button>
        </div>

        <div className="site-header__actions">
          <button className="top-control" type="button" onClick={onTop} aria-label="Return to top">
            <span aria-hidden="true">↑</span>
            <span>Top</span>
          </button>

          <button
            className="theme-toggle"
            type="button"
            role="switch"
            aria-checked={theme === "dark"}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            onClick={toggleTheme}
          >
            <span aria-hidden="true">☀</span>
            <span className="theme-toggle__track" aria-hidden="true">
              <span className="theme-toggle__thumb" />
            </span>
            <span aria-hidden="true">◐</span>
          </button>
        </div>
      </div>
    </header>
  );
}
