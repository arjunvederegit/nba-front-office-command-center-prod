import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { Providers } from "./providers";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TradeLab — NBA Trade Deadline Decision Room",
  description:
    "Decision-support system for exploratory NBA trade analysis: real provider-backed data, CBA-aware legality, explainable multi-component evaluation.",
};

const NAV = [
  { href: "/decision-room", label: "Decision Room" },
  { href: "/trade-builder", label: "Trade Builder" },
  { href: "/compare", label: "Compare" },
  { href: "/methodology", label: "Methodology" },
  { href: "/data-health", label: "Data Health" },
  { href: "/about", label: "About" },
];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Providers>
          <header className="sticky top-0 z-40 border-b border-line bg-background/90 backdrop-blur">
            <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
              <Link href="/" className="flex items-baseline gap-2">
                <span className="text-lg font-bold tracking-tight text-foreground">
                  Trade<span className="text-accent">Lab</span>
                </span>
                <span className="hidden text-[11px] text-muted sm:inline">
                  NBA Trade Deadline Decision Room
                </span>
              </Link>
              <nav className="ml-auto flex flex-wrap items-center gap-1" aria-label="Primary">
                {NAV.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="rounded-md px-3 py-1.5 text-sm text-muted transition-colors hover:bg-panel hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
                  >
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>
          </header>
          <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
          <footer className="border-t border-line py-4">
            <div className="mx-auto max-w-7xl px-4 text-[11px] leading-relaxed text-muted">
              TradeLab is an independent analytical portfolio project — not an official NBA
              cap-management product and not affiliated with the NBA. Basketball data: NBA.com via{" "}
              <a
                className="underline hover:text-foreground"
                href="https://github.com/swar/nba_api"
                target="_blank"
                rel="noreferrer"
              >
                nba_api
              </a>
              . Team names and trademarks belong to their owners. Contract data requires a
              separately configured provider; when absent, salary features are shown as
              unavailable — never estimated.
            </div>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
