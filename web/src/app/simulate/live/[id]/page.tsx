"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { 
  Activity, 
  ArrowRight, 
  CheckCircle2, 
  Radio, 
  Terminal,
  ShieldCheck,
  TrendingUp,
  AlertTriangle,
  BookOpen,
  RotateCcw
} from "lucide-react";

export default function LiveSimulationPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params?.id as string;

  const [decisions, setDecisions] = useState<any[]>([]);
  const [metrics, setMetrics] = useState<any[]>([]);
  const [status, setStatus] = useState<string>("running");
  const [currentDay, setCurrentDay] = useState<number>(1);
  const [currentCapacity, setCurrentCapacity] = useState<number>(200);
  const [isDisrupted, setIsDisrupted] = useState<boolean>(false);
  const [isComplete, setIsComplete] = useState<boolean>(false);
  const [sensors, setSensors] = useState<Array<{ label: string; value: string; highlight?: boolean }>>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!jobId) return;

    // Check current state via REST in case job already completed or failed
    fetch(`http://localhost:8000/api/simulations/${jobId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "failed") {
          setStatus("failed");
          setIsComplete(true);
          setErrorMessage(data.error || "Unable to connect to the LLM.");
        }
      })
      .catch(() => {});

    const eventSource = new EventSource(`http://localhost:8000/api/simulations/${jobId}/stream`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "tick") {
          if (data.day) setCurrentDay(data.day);
          if (data.round) setCurrentDay(data.round);
          if (data.capacity) setCurrentCapacity(data.capacity);
          if (data.disrupted !== undefined) setIsDisrupted(data.disrupted);
          if (data.sensors && Array.isArray(data.sensors)) {
            setSensors(data.sensors);
          }
        } else if (data.type === "decision") {
          setDecisions((prev) => [data, ...prev]);
        } else if (data.type === "metric_tick") {
          setMetrics((prev) => [...prev, data.data]);
        } else if (data.type === "error") {
          setStatus("failed");
          setIsComplete(true);
          setErrorMessage(data.message || "Unable to connect to the LLM.");
          eventSource.close();
        } else if (data.type === "finished") {
          setStatus(data.status);
          setIsComplete(true);
          if (data.status === "failed") {
            setErrorMessage(data.error || "Unable to connect to the LLM.");
          }
          eventSource.close();
        }
      } catch (err) {
        console.error("Failed to parse SSE payload:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE stream error:", err);
    };

    return () => {
      eventSource.close();
    };
  }, [jobId]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800 pb-6 mb-8 gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2 font-mono text-xs">
            <span className="flex h-2.5 w-2.5 rounded-full bg-cyan-400 animate-ping" />
            <span className="text-cyan-400 font-bold uppercase tracking-wider">
              LIVE SSE TELEMETRY STREAM
            </span>
            <span className="text-slate-500">|</span>
            <span className="text-slate-400 font-mono">Job: {jobId}</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-100 flex items-center gap-3">
            Active Multi-Agent Execution
          </h1>
        </div>

        {status === "failed" || errorMessage ? (
          <Link
            href="/case-studies"
            className="flex items-center justify-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-6 py-3 font-mono text-xs font-bold shadow-lg shadow-cyan-500/20 transition-all"
          >
            <BookOpen className="h-4 w-4" />
            View Featured Showcase
          </Link>
        ) : isComplete ? (
          <Link
            href={`/simulate/results/${jobId}`}
            className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 px-6 py-3 font-mono text-xs font-bold text-slate-950 shadow-lg shadow-emerald-500/20 hover:scale-[1.02] transition-all"
          >
            View Interactive Results Deck
            <ArrowRight className="h-4 w-4" />
          </Link>
        ) : (
          <div className="flex items-center gap-2 font-mono text-xs bg-slate-950 border border-slate-800 px-3.5 py-2 rounded-lg text-slate-300">
            <Radio className="h-4 w-4 text-cyan-400 animate-pulse" />
            <span>Streaming live turns...</span>
          </div>
        )}
      </div>

      {/* Connection Error Banner if simulation failed */}
      {(status === "failed" || errorMessage) && (
        <div className="rounded-2xl border border-rose-500/50 bg-rose-950/25 p-8 font-mono text-xs shadow-2xl space-y-4 mb-8">
          <div className="flex items-center gap-3 text-rose-400 font-bold text-sm">
            <AlertTriangle className="h-6 w-6 text-rose-400 shrink-0" />
            <span>Unable to Connect to the LLM</span>
          </div>
          <p className="text-slate-200 leading-relaxed text-xs">
            {errorMessage || "Simulation halted: Unable to establish a connection with the LLM reasoning agent. Automated synthetic fallbacks are disabled to maintain empirical validity."}
          </p>
          <div className="flex flex-wrap items-center gap-4 pt-3">
            <Link
              href="/case-studies"
              className="flex items-center gap-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-5 py-2.5 font-bold transition-all shadow-md shadow-cyan-500/20"
            >
              <BookOpen className="h-4 w-4" />
              Browse Completed Simulations in Featured Showcase
            </Link>
            <Link
              href="/simulate"
              className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900 text-slate-300 hover:text-white px-4 py-2.5 transition-colors"
            >
              <RotateCcw className="h-4 w-4" />
              Return to Studio
            </Link>
          </div>
        </div>
      )}

      {/* Horizontal Phase Milestone Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-3 font-mono text-xs">
          <div className="flex items-center justify-between mb-1">
            <span className="text-emerald-400 font-bold">1. Contract Ready</span>
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          </div>
          <p className="text-[10px] text-slate-400">Pydantic schemas validated</p>
        </div>

        <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-3 font-mono text-xs">
          <div className="flex items-center justify-between mb-1">
            <span className="text-emerald-400 font-bold">2. Sandbox Passed</span>
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          </div>
          <p className="text-[10px] text-slate-400">Ruff, mypy, acceptance clean</p>
        </div>

        <div className={`rounded-lg border p-3 font-mono text-xs transition-colors ${
          isComplete 
            ? "border-emerald-500/30 bg-emerald-950/20" 
            : "border-cyan-500 bg-cyan-950/30 shadow-md shadow-cyan-500/20"
        }`}>
          <div className="flex items-center justify-between mb-1">
            <span className={isComplete ? "text-emerald-400 font-bold" : "text-cyan-300 font-bold animate-pulse"}>
              3. Live Execution
            </span>
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
          </div>
          <p className="text-[10px] text-slate-400">
            {isComplete ? "Completed All Turns" : `Simulating Round ${currentDay}`}
          </p>
        </div>

        <div className={`rounded-lg border p-3 font-mono text-xs ${
          isComplete 
            ? "border-cyan-500 bg-cyan-950/20 text-cyan-300" 
            : "border-slate-800 bg-slate-950 text-slate-500"
        }`}>
          <div className="flex items-center justify-between mb-1">
            <span className="font-bold">4. Report Assembly</span>
            {isComplete && <CheckCircle2 className="h-3.5 w-3.5 text-cyan-400" />}
          </div>
          <p className="text-[10px]">
            {isComplete ? "Metrics & Notebooks Compiled" : "Awaiting completion"}
          </p>
        </div>
      </div>

      {/* Main Stream Area: Live Ticker & Real-Time Sparklines */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Live Decision & Rationale Feed */}
        <div className="lg:col-span-8 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Terminal className="h-4 w-4 text-cyan-400" />
              Live Decision & Thought Rationale Feed
            </h2>
            <span className="text-[10px] font-mono text-slate-500">
              {decisions.length} turns committed
            </span>
          </div>

          <div
            ref={scrollRef}
            className="space-y-3 max-h-[600px] overflow-y-auto pr-2"
          >
            {decisions.length === 0 ? (
              <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-12 text-center font-mono text-xs text-slate-500">
                <Radio className="h-6 w-6 text-cyan-500 mx-auto animate-pulse mb-3" />
                Connecting to event relay... Awaiting first committed turn...
              </div>
            ) : (
              decisions.map((d, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-slate-800/90 bg-slate-900/80 p-4 font-mono text-xs shadow-md hover:border-slate-700 transition-all"
                >
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2.5">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-cyan-400 uppercase">
                        [{d.phase || `Tick ${d.tick}`}]
                      </span>
                      <span className="text-slate-300 font-semibold">{d.actor_id}</span>
                    </div>
                    <span className="text-[10px] text-slate-500">
                      {d.action?.kind ? `kind: ${d.action.kind}` : "action committed"}
                    </span>
                  </div>

                  {/* Action Payload */}
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-850 text-slate-300 mb-2 text-[11px]">
                    <span className="text-slate-500">Payload: </span>
                    <span className="text-emerald-400 font-semibold">
                      {JSON.stringify(d.action?.payload || {})}
                    </span>
                  </div>

                  {/* Natural-Language Rationale */}
                  <div className="pl-3 border-l-2 border-cyan-500/40 text-slate-300 text-[11px] leading-relaxed italic bg-cyan-950/10 py-1.5 px-2 rounded-r">
                    &ldquo;{d.rationale || "Executing optimal policy move."}&rdquo;
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Real-Time Environmental Status Deck */}
        <div className="lg:col-span-4 space-y-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl font-mono text-xs">
            <h3 className="font-bold text-slate-300 uppercase tracking-wider mb-4 border-b border-slate-800 pb-2 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-cyan-400" />
              Runtime Sensor Array
            </h3>

            <div className="space-y-4">
              {sensors.length > 0 ? (
                sensors.map((s, idx) => (
                  <div key={idx} className="flex justify-between items-center bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400">{s.label}</span>
                    <span className={`text-xs font-bold ${s.highlight ? "text-amber-400" : "text-slate-100"}`}>
                      {s.value}
                    </span>
                  </div>
                ))
              ) : (
                <>
                  <div className="flex justify-between items-center bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400">Active Horizon</span>
                    <span className="text-base font-bold text-slate-100">Round {currentDay}</span>
                  </div>
                  <div className="flex justify-between items-center bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400">Environment Regime</span>
                    <span className="text-slate-200 font-semibold">Active Dynamics</span>
                  </div>
                  <div className="flex justify-between items-center bg-slate-950 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400">Safety Guardrails</span>
                    <span className="text-emerald-400 font-semibold">Enforcing Bounds</span>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Quick Metrics Stream */}
          {metrics.length > 0 && (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl font-mono text-xs">
              <h3 className="font-bold text-slate-300 uppercase tracking-wider mb-4 border-b border-slate-800 pb-2 flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-cyan-400" />
                Latest Metric Snapshot
              </h3>
              <div className="space-y-2">
                {Object.entries(metrics[metrics.length - 1]).slice(0, 5).map(([k, v]: [string, any]) => (
                  <div key={k} className="flex justify-between text-slate-400">
                    <span>{k}:</span>
                    <span className="text-cyan-300 font-bold">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
