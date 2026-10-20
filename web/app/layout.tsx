import type { Metadata } from "next";
import { Barlow_Condensed, Inter, Noto_Sans_Devanagari, Noto_Sans_Tamil } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin", "latin-ext"] });
const barlow = Barlow_Condensed({ variable: "--font-barlow", subsets: ["latin", "latin-ext"], weight: ["500", "600", "700"] });
// Hindi and Tamil recaps: without these the browser falls back to whatever the system has, often badly shaped.
const devanagari = Noto_Sans_Devanagari({ variable: "--font-devanagari", subsets: ["devanagari"] });
const tamil = Noto_Sans_Tamil({ variable: "--font-tamil", subsets: ["tamil"] });

export const metadata: Metadata = {
  title: "MatchLens",
  description: "Football recaps written by a local model and checked line by line against the match data.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${barlow.variable} ${devanagari.variable} ${tamil.variable}`}>
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
