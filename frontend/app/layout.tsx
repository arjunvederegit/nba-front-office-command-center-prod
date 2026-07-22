import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { AppNav } from "@/components/shell";
import { ToastProvider } from "@/components/toast";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "RosterLab — NBA Front Office Simulator",
  description:
    "Build trades, explore rosters, and stress-test front-office decisions with real NBA data, honest rules checks, and explainable analytics.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Providers>
          <ToastProvider>
            <AppNav />
            <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
            <footer className="border-t border-line py-4">
              <div className="mx-auto max-w-7xl px-4 text-[11px] leading-relaxed text-muted">
                RosterLab is an independent analytical simulator — not affiliated with or endorsed
                by the NBA, and not an official cap-management product. Basketball data comes from
                NBA.com via{" "}
                <a
                  className="underline hover:text-foreground"
                  href="https://github.com/swar/nba_api"
                  target="_blank"
                  rel="noreferrer"
                >
                  nba_api
                </a>{" "}
                and user-imported sources, each labeled with provenance in{" "}
                <a className="underline hover:text-foreground" href="/data-status">
                  Data Status
                </a>
                . Team names, logos and player images belong to their owners and are used locally
                for identification. Missing data is always shown as unavailable — never estimated.
              </div>
            </footer>
          </ToastProvider>
        </Providers>
      </body>
    </html>
  );
}
