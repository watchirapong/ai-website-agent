import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Website Agent",
  description: "Generate, test, and deploy websites from a single prompt",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0a0a0a] text-gray-100 antialiased">
        <header className="border-b border-gray-800 bg-[#111]">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <a href="/" className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold">
                AI
              </div>
              <span className="text-lg font-semibold tracking-tight">
                Website Agent
              </span>
            </a>
            <nav className="flex gap-6 text-sm text-gray-400">
              <a href="/" className="transition hover:text-white">
                Generate
              </a>
              <a href="/projects" className="transition hover:text-white">
                Projects
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
