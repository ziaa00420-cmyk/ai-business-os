import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Business OS",
  description: "Export assistant for manufacturers",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
