import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "GEO Optimization Assistant",
  description: "Generative Engine Optimization analysis & recommendations",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <header className="no-print bg-navy-900 text-white">
          <div className="mx-auto max-w-6xl px-6 py-4 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-accent font-bold">
                G
              </span>
              <div>
                <div className="font-semibold leading-tight">GEO Assistant</div>
                <div className="text-xs text-slate-300">Generative Engine Optimization</div>
              </div>
            </Link>
            <nav className="flex gap-6 text-sm">
              <Link href="/" className="hover:text-accent">New Analysis</Link>
              <Link href="/history" className="hover:text-accent">History</Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
