import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Cogitate Excel Rater",
  description: "Excel-based rating engine with admin interface",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <div className="absolute top-4 right-4 z-50">
          <a
            href="/gateway/home"
            className="rounded-md bg-slate-800 px-4 py-2 text-xs font-bold tracking-wider text-white shadow hover:bg-slate-700 transition flex items-center gap-2"
          >
            Switch Rater Engine
          </a>
        </div>
        {children}
      </body>
    </html>
  );
}
