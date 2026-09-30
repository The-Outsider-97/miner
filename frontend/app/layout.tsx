import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import "../style.css";

export const metadata: Metadata = {
  title: "SLAI Miner SN67 | Harnyx Observability",
  description:
    "Read-only observability for SLAI-powered Harnyx SN67 artifacts, benchmarks, runtime cost, latency, and pinned integration state.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
    { media: "(prefers-color-scheme: light)", color: "#EAECEC" },
  ],
};

const themeBootScript = `
(() => {
  try {
    const stored = localStorage.getItem("slai-miner-theme");
    const preferred = window.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
    document.documentElement.dataset.theme =
      stored === "light" || stored === "dark" ? stored : preferred;
  } catch (_) {
    document.documentElement.dataset.theme = "dark";
  }
})();
`;

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
