import type { Metadata } from "next";
import { Archivo, Barlow_Condensed, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { AppNav, AppFooter } from "@/components/shell";
import { ToastProvider } from "@/components/toast";

/** Three typographic roles: condensed athletic display (jersey/scoreboard),
 *  a grotesque for interface text, and tabular mono for box-score data. */
const display = Barlow_Condensed({
  variable: "--font-barlow-condensed",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
});
const sans = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});
const mono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Pivot — Basketball Intelligence for Better Decisions",
  description:
    "Understand a roster, find what it is missing, test a move, and read why — on real NBA data, with every number traced to how it was produced and what it cannot support.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${display.variable} ${sans.variable} ${mono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col">
        <Providers>
          <ToastProvider>
            <a
              href="#main"
              className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-[100] focus:rounded-md focus:bg-signal focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-court"
            >
              Skip to content
            </a>
            <AppNav />
            <main id="main" className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 lg:px-8">
              {children}
            </main>
            <AppFooter />
          </ToastProvider>
        </Providers>
      </body>
    </html>
  );
}
