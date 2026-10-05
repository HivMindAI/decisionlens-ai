import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "DecisionLens AI | Financial Decision Intelligence",
  description:
    "Evidence-backed financial analysis, forecasting, and decision support for monthly business data.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
