"use client";

import Image from "next/image";

import harnyxMark from "./assets/harnyx-mark.png";
import type { DashboardSnapshot, SectionDefinition } from "./types";

type Props = {
  open: boolean;
  sections: readonly SectionDefinition[];
  activeSection: string;
  data: DashboardSnapshot | null;
  onClose: () => void;
};

function StatusLine({ label, value, state }: { label: string; value: string; state: string }) {
  return (
    <div className="side-status__row">
      <span className="status-dot" data-state={state} aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function SidePanel({ open, sections, activeSection, data, onClose }: Props) {
  const artifact = data?.artifact?.profile ?? "None";
  const benchmarkState = data?.backend.benchmark_store ?? "loading";
  const slaiState = data?.slai.status ?? "loading";
  const harnyxState = data?.harnyx.status ?? "loading";

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

      <aside id="miner-side-panel" className="side-panel" data-open={open} aria-label="Dashboard navigation">
        <div className="side-panel__top">
          <div className="side-panel__brand">
            <Image src={harnyxMark} alt="" />
            <div>
              <p className="side-panel__kicker">Subnet 67</p>
              <h2>Harnyx</h2>
            </div>
          </div>
          <p className="side-panel__description">
            Read-only Miner state, benchmark evidence, and integration status.
          </p>
        </div>

        <nav className="side-panel__toc" aria-label="On this dashboard">
          <p className="side-panel__label">On this dashboard</p>
          <ol>
            {sections.map((item, index) => (
              <li key={item.id}>
                <a
                  href={`#${item.id}`}
                  data-active={activeSection === item.id}
                  aria-current={activeSection === item.id ? "location" : undefined}
                  onClick={onClose}
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <strong>{item.label}</strong>
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="side-panel__bottom">
          <p className="side-panel__label">Current state</p>
          <div className="side-status">
            <StatusLine label="Artifact" value={artifact} state={data?.artifact ? "ready" : "empty"} />
            <StatusLine label="Benchmark" value={benchmarkState} state={benchmarkState} />
            <StatusLine label="SLAI" value={slaiState} state={slaiState} />
            <StatusLine label="Harnyx" value={harnyxState} state={harnyxState} />
          </div>
          <div className="side-panel__foot">
            <span className="status-dot" data-state="ready" aria-hidden="true" />
            <span>Observability only</span>
          </div>
        </div>
      </aside>
    </>
  );
}
