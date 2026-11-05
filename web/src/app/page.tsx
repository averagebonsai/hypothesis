import Link from "next/link";
import { 
  ArrowRight, 
  Cpu, 
  ShieldCheck, 
  Sparkles, 
  Layers, 
  FileCode2, 
  CheckCircle2 
} from "lucide-react";

export default function HomePage() {
  return (
    <div className="relative isolate overflow-hidden">
      {/* Background radial glow */}
      <div 
        className="absolute top-0 left-1/2 -translate-x-1/2 -z-10 h-[500px] w-[900px] opacity-25 blur-3xl"
        style={{
          background: "radial-gradient(circle, rgba(6,182,212,0.4) 0%, rgba(99,102,241,0.2) 50%, transparent 100%)"
        }}
      />

      {/* 1. Hero Section */}
      <section className="mx-auto max-w-7xl px-4 pt-16 pb-20 sm:px-6 lg:px-8 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono text-cyan-400 mb-6">
          <Sparkles className="h-3.5 w-3.5" />
          <span>Autonomous Multi-Agent Feedback & Interaction Simulator</span>
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-slate-100 max-w-4xl mx-auto leading-tight sm:leading-none">
          Simulate Your Market With{" "}
          <span className="bg-gradient-to-r from-cyan-400 via-sky-300 to-indigo-400 bg-clip-text text-transparent">
            Reasoning Agents
          </span>
        </h1>

        <p className="mt-6 text-base sm:text-lg text-slate-400 max-w-4xl mx-auto leading-relaxed md:whitespace-nowrap">
          Model feedback loops, supply shocks, and game equilibria using frontier reasoning models.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link
            href="/simulate"
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-indigo-600 px-6 py-3.5 text-sm font-mono font-semibold text-white shadow-lg shadow-cyan-500/25 hover:from-cyan-400 hover:to-indigo-500 transition-all hover:scale-[1.02]"
          >
            Launch Studio
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="/case-studies"
            className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 hover:bg-slate-800/80 px-6 py-3.5 text-sm font-mono text-slate-300 transition-all"
          >
            Explore Featured Showcase
          </Link>
        </div>

        {/* Live Lab Terminal Graphic */}
        <div className="mt-14 max-w-4xl mx-auto rounded-xl border border-slate-800/80 bg-slate-950/90 shadow-2xl p-4 sm:p-6 text-left font-mono text-xs overflow-hidden relative">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
            <div className="flex items-center gap-2">
              <div className="h-2.5 w-2.5 rounded-full bg-rose-500/80" />
              <div className="h-2.5 w-2.5 rounded-full bg-amber-500/80" />
              <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/80" />
              <span className="text-slate-500 ml-2">runtime.stream // live_trace</span>
            </div>
            <span className="text-[10px] text-emerald-400 bg-emerald-950/50 border border-emerald-800/50 px-2 py-0.5 rounded">
              ● SSE BROADCAST ONLINE
            </span>
          </div>
          <div className="space-y-2 text-slate-300">
            <p className="text-slate-500">
              # Phase: d4_make | Actor: manufacturer | Model: muse-spark-1.3-contributor
            </p>
            <p className="text-cyan-400">
              &gt; ACTION: MakeAction(produce=80)
            </p>
            <p className="text-slate-400 pl-4 border-l-2 border-cyan-500/30 italic">
              &ldquo;Rationale: Today demand is 80 with 0 finished goods. On-hand Component A is 96, Component B is 80. Producing 80 meets full demand, maximizes profit and avoids holding penalties.&rdquo;
            </p>
            <div className="flex items-center gap-4 text-slate-500 pt-2 border-t border-slate-900 text-[11px]">
              <span>Conservation: 100% Exact</span>
              <span>Disruption: Active (Transport Cap: 80/day)</span>
              <span>Runtime Trapping: 0 Errors</span>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Value Proposition Grid */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8 border-t border-slate-900">
        <div className="text-center mb-12">
          <h2 className="text-xs font-mono font-bold tracking-widest text-cyan-400 uppercase">
            Platform Capabilities
          </h2>
          <p className="mt-2 text-2xl sm:text-3xl font-bold text-slate-100">
            Engineered for Mathematical Rigor and Agent Independence
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-6 hover:border-cyan-500/40 transition-colors">
            <div className="p-3 rounded-lg bg-cyan-500/10 text-cyan-400 w-fit mb-4">
              <Cpu className="h-6 w-6" />
            </div>
            <h3 className="text-base font-bold text-slate-100 mb-2">Autonomous Coding Agent</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              Headless Muse Code synthesizes discrete-event mechanisms, typed Pydantic contracts, and acceptance tests in an isolated Docker sandbox.
            </p>
          </div>

          <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-6 hover:border-indigo-500/40 transition-colors">
            <div className="p-3 rounded-lg bg-indigo-500/10 text-indigo-400 w-fit mb-4">
              <Layers className="h-6 w-6" />
            </div>
            <h3 className="text-base font-bold text-slate-100 mb-2">Computational Primitives</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              Built-in high-performance tools: ResourceLedger conservation, Highs LP rationing, Dijkstra network topology, and demographic choice share models.
            </p>
          </div>

          <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-6 hover:border-emerald-500/40 transition-colors">
            <div className="p-3 rounded-lg bg-emerald-500/10 text-emerald-400 w-fit mb-4">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <h3 className="text-base font-bold text-slate-100 mb-2">Runtime Fallback Trapping</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              Physical boundary clamping and defensive fallback trapping ensure that illegal agent proposals never crash the multi-day simulation loop.
            </p>
          </div>
        </div>
      </section>

      {/* 3. Featured Showcase: Flood Disruption */}
      <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8 border-t border-slate-900">
        <div className="rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900/80 to-slate-950 p-6 sm:p-10">
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-8">
            <div className="max-w-2xl">
              <span className="text-xs font-mono font-semibold text-cyan-400 uppercase tracking-widest">
                Featured Case Study
              </span>
              <h3 className="mt-2 text-2xl sm:text-3xl font-bold text-slate-100">
                Decentralized Supply Chain Flood Disruption
              </h3>
              <p className="mt-4 text-sm text-slate-300 leading-relaxed">
                4 autonomous organizations (manufacturer, two competing suppliers, logistics carrier) 
                facing a 60% transportation cut across 9 days. Without central visibility, the bullwhip 
                effect causes supplier stockpiling and manufacturer component starvation.
              </p>
              <div className="mt-6 flex flex-wrap gap-4 text-xs font-mono">
                <div className="flex items-center gap-1.5 text-slate-400">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span>9 Days & 36 Phase Decisions</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-400">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span>Verified Fallback Trapping</span>
                </div>
                <div className="flex items-center gap-1.5 text-slate-400">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                  <span>Jupyter Notebook Included</span>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3 w-full sm:w-auto">
              <Link
                href="/simulate?preset=supplychain"
                className="flex items-center justify-center gap-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-5 py-3 text-xs font-mono font-bold transition-all"
              >
                Launch This Preset (30s)
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/case-studies/cs_supplychain_flood"
                className="flex items-center justify-center gap-2 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900 text-slate-300 px-5 py-3 text-xs font-mono transition-all"
              >
                <FileCode2 className="h-4 w-4" />
                Inspect Full Analysis
              </Link>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
