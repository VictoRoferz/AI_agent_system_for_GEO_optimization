import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Image from "next/image";
import Link from "next/link";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Syte · GEO",
  description: "Syte — Generative Engine Optimization analysis & recommendations",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <header className="no-print bg-navy-900 text-white">
          <div className="mx-auto max-w-6xl px-6 py-4 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3">
              <span className="inline-flex items-center rounded-md bg-white px-2 py-1 shadow-sm">
                <Image
                  src="/syte-logo.png"
                  alt="Syte"
                  width={72}
                  height={30}
                  priority
                  className="h-6 w-auto"
                />
              </span>
              <div>
                <div className="font-semibold leading-tight">Syte · GEO</div>
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
