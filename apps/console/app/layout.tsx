import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Memory Console",
  description: "Operational console for the portable memory platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
