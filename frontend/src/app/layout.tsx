import type { Metadata } from "next";
import Link from "next/link";
import { DemoClock } from "@/components/DemoClock";
import "./globals.css";

export const metadata: Metadata = {
  title: "Staffing",
  description: "Staffing workflow",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <nav
          aria-label="Main navigation"
          className="flex flex-wrap gap-4 border-b border-slate-300 px-6 py-4"
        >
          <Link href="/" className="text-blue-700 underline">
            Home
          </Link>
          <Link href="/demo/control" className="text-blue-700 underline">
            Demo control
          </Link>
          <Link href="/approvals" className="text-blue-700 underline">
            Approvals
          </Link>
          <Link href="/handoff" className="text-blue-700 underline">
            Handoff
          </Link>
          <Link href="/demo/line-sim" className="text-blue-700 underline">
            LINE simulator
          </Link>
          <Link href="/roster" className="text-blue-700 underline">
            Roster
          </Link>
          <Link href="/me/offers" className="text-blue-700 underline">
            My offers
          </Link>
          <DemoClock />
        </nav>
        {children}
      </body>
    </html>
  );
}
