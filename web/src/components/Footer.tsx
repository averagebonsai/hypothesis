import Link from "next/link";
import { Terminal } from "lucide-react";

export function Footer() {
  return (
    <footer className="w-full border-t border-slate-900 bg-slate-950 py-8 px-4 sm:px-6 lg:px-8 mt-auto">
      <div className="mx-auto max-w-7xl flex flex-col sm:flex-row items-center justify-between gap-4 text-xs font-mono text-slate-500">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-cyan-500" />
          <span>HYPOTHESIS v1.0.0 — Autonomous Microeconomic Simulator</span>
        </div>
        <div className="flex items-center gap-6">
          <Link href="/simulate" className="hover:text-cyan-400 transition-colors">Studio</Link>
          <Link href="/case-studies" className="hover:text-cyan-400 transition-colors">Case Studies</Link>
          <span>FastAPI + Docker + Next.js</span>
        </div>
      </div>
    </footer>
  );
}
