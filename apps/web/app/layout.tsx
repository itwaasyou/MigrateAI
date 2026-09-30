import type { Metadata } from "next";
import "./styles.css";
import "./overrides.css";

export const metadata: Metadata = { title: "MigrateAI | Migration intelligence", description: "Evidence-based software modernization planning" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
