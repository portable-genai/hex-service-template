import type { ReactNode } from "react";

export const metadata = {
  title: "GRC Agent UI",
  description: "Embeddable micro-frontend base for a catalog agent.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
