"use client";

import { useEffect, useState, useMemo } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { 
  Download, 
  RotateCcw, 
  Award, 
  FileCode2, 
  Terminal, 
  Filter,
  Search,
  Check,
  Copy,
  Layers,
  Sparkles,
  AlertTriangle,
  BookOpen,
  ImageIcon,
  RefreshCw
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  BarChart,
  Bar
} from "recharts";

const COLOR_PALETTE = [
  "#06b6d4", // Cyan
  "#6366f1", // Indigo
  "#10b981", // Emerald
  "#f59e0b", // Amber
  "#ec4899", // Pink
  "#8b5cf6", // Purple
  "#14b8a6", // Teal
  "#f43f5e", // Rose
];

export default function ResultsDashboardPage() {
  const params = useParams();
  const jobId = params?.id as string;

  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedActorFilter, setSelectedActorFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [expandedDecisionIdx, setExpandedDecisionIdx] = useState<number | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  // Muse Image schematic state
  const [visualImageUrl, setVisualImageUrl] = useState<string | null>(null);
  const [generatingImage, setGeneratingImage] = useState<boolean>(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const [hasTriggeredGen, setHasTriggeredGen] = useState<boolean>(false);

  useEffect(() => {
    if (!jobId) return;

    fetch(`http://localhost:8000/api/simulations/${jobId}/results`)
      .then((res) => res.json())
      .then((data) => {
        setResults(data);
        setLoading(false);
        if (data?.parameters?.visual_image_url) {
          setVisualImageUrl(data.parameters.visual_image_url);
        }
      })
      .catch((err) => {
        console.error("Failed to load results:", err);
        setLoading(false);
      });
  }, [jobId]);

  const handleGenerateImage = async (customPrompt?: string) => {
    setGeneratingImage(true);
    setImageError(null);
    try {
      const bp = results?.parameters?.blueprint;
      const title = results?.parameters?.hypothesis || results?.scenario_id || "Simulation Scenario";
      const promptToUse =
        customPrompt ||
        bp?.schematic_image_prompt ||
        `Clear, informative architectural diagram for a multi-agent simulation of '${title}'. ` +
        `Featuring autonomous participant actors in an intuitive interaction layout, ` +
        `clearly displaying protocol steps, participant actions, and evaluation rationales. ` +
        `Clean, professional visual infographic aesthetic accurately communicating user scenario details with high readability.`;

      const res = await fetch("http://localhost:8000/api/simulations/generate-image", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: promptToUse }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Muse Image generation failed.");
      }
      const data = await res.json();
      if (data.image_url) {
        setVisualImageUrl(data.image_url);
      }
    } catch (err: any) {
      console.error("Image generation error:", err);
      setImageError(err.message || "Failed to generate visual schematic with Muse Image.");
    } finally {
      setGeneratingImage(false);
    }
  };

  const handleDownloadImage = () => {
    if (!visualImageUrl) return;
    const a = document.createElement("a");
    a.href = visualImageUrl;
    a.download = `simulation_${jobId}_schematic.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Auto-generate schematic on results load if not already provided
  useEffect(() => {
    if (!results || results.status === "failed" || results.error) return;
    if (results?.parameters?.visual_image_url) {
      setVisualImageUrl(results.parameters.visual_image_url);
    } else if (!visualImageUrl && !generatingImage && !hasTriggeredGen) {
      setHasTriggeredGen(true);
      handleGenerateImage();
    }
  }, [results, visualImageUrl, generatingImage, hasTriggeredGen]);

  const blueprint = results?.parameters?.blueprint || {};
  const domainArchetype = 
    blueprint.domain_archetype || 
    (results?.scenario_id === "bertrand" ? "differentiated_pricing" : results?.scenario_id === "supply_chain" ? "supply_chain" : "multi_agent_game");

  const primaryField = blueprint.action_schema?.primary_field || "price";
  const primaryUnit = blueprint.action_schema?.unit || "$";
  const actionKind = blueprint.action_schema?.action_kind || "action";

  const isEconomic = useMemo(() => {
    if (primaryUnit === "$") return true;
    const text = `${domainArchetype} ${results?.scenario_id || ""} ${results?.parameters?.hypothesis || ""}`.toLowerCase();
    const nonEcon = ["feedback", "review", "story", "reader", "reading", "critique", "writing", "evaluation", "score", "deliberation", "voting", "consensus"];
    if (nonEcon.some((t) => text.includes(t))) return false;
    const econ = ["pricing", "price", "duopoly", "supply_chain", "auction", "market", "bertrand", "cost", "trade"];
    return econ.some((t) => text.includes(t));
  }, [primaryUnit, domainArchetype, results]);

  // Derive actors
  const actors: string[] = useMemo(() => {
    if (!results) return [];
    const fromPayoffs = Object.keys(results.payoffs || {});
    const fromDecisions = (results.decisions || []).map((d: any) => d.actor_id);
    const set = new Set([...fromPayoffs, ...fromDecisions]);
    return Array.from(set).filter(Boolean);
  }, [results]);

  // Normalize chart data across domain archetypes
  const chartData = useMemo(() => {
    if (!results || !results.events) return [];
    return results.events.map((ev: any, idx: number) => {
      const row: Record<string, any> = {
        ...ev,
        round: ev.round !== undefined ? ev.round : ev.day !== undefined ? ev.day : idx + 1,
      };

      actors.forEach((aid: string) => {
        // Normalize action value
        if (row[`action_${aid}`] !== undefined) {
          row[`action_${aid}`] = row[`action_${aid}`];
        } else if (aid === "firm_alpha" && row.price_alpha !== undefined) {
          row[`action_${aid}`] = row.price_alpha;
        } else if (aid === "firm_beta" && row.price_beta !== undefined) {
          row[`action_${aid}`] = row.price_beta;
        } else if (aid === "firm_gamma" && row.price_gamma !== undefined) {
          row[`action_${aid}`] = row.price_gamma;
        } else if (row[aid] !== undefined && typeof row[aid] === "number") {
          row[`action_${aid}`] = row[aid];
        }

        // Normalize cumulative profit
        if (row[`cum_profit_${aid}`] !== undefined) {
          row[`cum_profit_${aid}`] = row[`cum_profit_${aid}`];
        } else if (aid === "firm_alpha" && row.cum_profit_alpha !== undefined) {
          row[`cum_profit_${aid}`] = row.cum_profit_alpha;
        } else if (aid === "firm_beta" && row.cum_profit_beta !== undefined) {
          row[`cum_profit_${aid}`] = row.cum_profit_beta;
        } else if (aid === "firm_gamma" && row.cum_profit_gamma !== undefined) {
          row[`cum_profit_${aid}`] = row.cum_profit_gamma;
        }
      });

      return row;
    });
  }, [results, actors]);

  // Filter decisions
  const filteredDecisions = useMemo(() => {
    if (!results || !results.decisions) return [];
    return results.decisions.filter((d: any) => {
      if (selectedActorFilter !== "all" && d.actor_id !== selectedActorFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const inRationale = (d.rationale || "").toLowerCase().includes(q);
        const inActor = (d.actor_id || "").toLowerCase().includes(q);
        const inPhase = (d.phase || "").toLowerCase().includes(q);
        const inKind = (d.action?.kind || "").toLowerCase().includes(q);
        if (!inRationale && !inActor && !inPhase && !inKind) return false;
      }
      return true;
    });
  }, [results, selectedActorFilter, searchQuery]);

  const handleCopyRationale = (text: string, idx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 1800);
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-24 text-center font-mono">
        <Sparkles className="h-8 w-8 text-cyan-400 mx-auto animate-pulse mb-3" />
        <p className="text-cyan-400 text-sm">Compiling simulation analytics & payoff matrices...</p>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-20 text-center font-mono text-sm text-rose-400">
        Simulation result record not found for {jobId}.
      </div>
    );
  }

  if (results.status === "failed" || results.error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-20 font-mono text-center space-y-6">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-950/40 border border-rose-500/30 text-rose-400 shadow-xl">
          <AlertTriangle className="h-8 w-8" />
        </div>
        <div>
          <span className="text-xs font-bold text-rose-400 uppercase tracking-widest block mb-2">
            SIMULATION TERMINATED // CONNECTION ERROR
          </span>
          <h1 className="text-2xl font-extrabold text-slate-100">
            Unable to Connect to the LLM
          </h1>
          <p className="mt-3 text-xs text-slate-300 max-w-lg mx-auto leading-relaxed">
            {results.error || "The simulation was terminated because it was unable to establish a live connection to the LLM. Automated synthetic fallbacks are disabled to ensure all recorded data is authentic."}
          </p>
        </div>
        <div className="pt-4 flex flex-wrap justify-center gap-4">
          <Link
            href="/case-studies"
            className="flex items-center gap-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-6 py-3 text-xs font-bold font-mono transition-all shadow-md shadow-cyan-500/20"
          >
            <BookOpen className="h-4 w-4" />
            Explore Completed Simulations in Featured Showcase
          </Link>
          <Link
            href="/simulate"
            className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900 text-slate-300 hover:text-white px-5 py-3 text-xs font-mono transition-colors"
          >
            <RotateCcw className="h-4 w-4" />
            Back to Studio
          </Link>
        </div>
      </div>
    );
  }

  const isSupplyChain = results.scenario_id === "supply_chain";
  const hasActorActions = actors.some((aid) => chartData.some((r: Record<string, any>) => r[`action_${aid}`] !== undefined));
  const hasActorProfits = actors.some((aid) => chartData.some((r: Record<string, any>) => r[`cum_profit_${aid}`] !== undefined));

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8 space-y-10">
      {/* Page Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between border-b border-slate-800 pb-8 gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-2 font-mono text-xs">
            <span className="text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              SIMULATION CONVERGED
            </span>
            <span className="text-slate-500">|</span>
            <span className="text-slate-400">ID: {jobId}</span>
            <span className="text-slate-500">|</span>
            <span className="text-cyan-400 font-semibold uppercase">
              {domainArchetype.replace(/_/g, " ")}
            </span>
          </div>
          <h1 className="text-3xl font-extrabold text-slate-100">
            Interactive Results Dashboard
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Empirical telemetry, autonomous actor thought rationales, and comparative equilibrium metrics.
          </p>
        </div>

        {/* Export Suite Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          <a
            href={`http://localhost:8000/api/simulations/${jobId}/download/notebook`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-4 py-2.5 text-xs font-mono font-bold transition-all shadow-md shadow-cyan-500/20"
          >
            <Download className="h-3.5 w-3.5" />
            Download .ipynb
          </a>
          <a
            href={`http://localhost:8000/api/simulations/${jobId}/download/events`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900 text-slate-300 px-4 py-2.5 text-xs font-mono transition-all"
          >
            <FileCode2 className="h-3.5 w-3.5" />
            Export events.jsonl
          </a>
          <Link
            href="/simulate"
            className="flex items-center gap-2 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900 text-slate-400 hover:text-slate-200 px-4 py-2.5 text-xs font-mono transition-all"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            New Simulation
          </Link>
        </div>
      </div>

      {/* 1. Scorecard: KPIs & Outcomes */}
      <section className="space-y-4">
        <h2 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
          <Award className="h-4 w-4 text-cyan-400" />
          {isEconomic ? "Executive Scorecard & Payoffs" : "Evaluation Scorecard & Feedback Ratings"}
        </h2>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {Object.entries(results.payoffs || {}).map(([aid, payoff]: [string, any], idx) => (
            <div
              key={aid}
              className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 font-mono shadow-md relative overflow-hidden"
            >
              <div 
                className="absolute top-0 left-0 right-0 h-1" 
                style={{ backgroundColor: COLOR_PALETTE[idx % COLOR_PALETTE.length] }} 
              />
              <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                <span className="font-bold uppercase truncate">{aid.replace(/_/g, " ")}</span>
                <span className="text-[10px] text-slate-500">{isEconomic ? `Actor #${idx + 1}` : `Evaluator #${idx + 1}`}</span>
              </div>
              <p className="text-xl font-extrabold text-cyan-300">
                {isEconomic ? (
                  `$${typeof payoff === "number" ? payoff.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 }) : payoff}`
                ) : (
                  `${typeof payoff === "number" ? payoff.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) : payoff} ${primaryUnit === "$" ? "" : primaryUnit}`
                )}
              </p>
              <p className="text-[10px] text-slate-500 mt-1">
                {isEconomic ? "Final Accumulated Payoff" : `Assigned ${primaryField.replace(/_/g, " ")}`}
              </p>
            </div>
          ))}

          {Object.entries(results.metrics || {}).map(([key, val]: [string, any]) => (
            <div
              key={key}
              className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 font-mono shadow-md"
            >
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1 truncate">
                {key.replace(/_/g, " ")}
              </span>
              <p className="text-lg font-bold text-slate-200 truncate">
                {typeof val === "number" ? val.toLocaleString() : String(val)}
              </p>
              <p className="text-[10px] text-slate-500 mt-1">{isEconomic ? "System Metric" : "Cohort Metric"}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 2. Visual Simulation Schematic (Muse Image) */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
            <ImageIcon className="h-4 w-4 text-cyan-400" />
            Visual Simulation Schematic (Muse Image)
          </h2>

          <div className="flex items-center gap-2 font-mono text-xs">
            <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[10px] font-semibold border ${
              visualImageUrl
                ? "bg-emerald-950/80 text-emerald-400 border-emerald-800"
                : generatingImage
                ? "bg-cyan-950/80 text-cyan-400 border-cyan-800"
                : "bg-slate-800 text-slate-400 border-slate-700"
            }`}>
              {visualImageUrl ? (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  muse-image-1.0 (1024x1024)
                </>
              ) : generatingImage ? (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                  Generating Schematic...
                </>
              ) : (
                "Muse Image Standby"
              )}
            </span>

            <button
              onClick={() => handleGenerateImage()}
              disabled={generatingImage}
              className="flex items-center gap-1.5 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900 text-slate-300 hover:text-white px-3 py-1 text-xs transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`h-3 w-3 ${generatingImage ? "animate-spin" : ""}`} />
              {visualImageUrl ? "Regenerate" : "Synthesize Schematic"}
            </button>

            {visualImageUrl && (
              <button
                onClick={handleDownloadImage}
                className="flex items-center gap-1.5 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900 text-slate-300 hover:text-white px-3 py-1 text-xs transition-colors"
                title="Download 1024x1024 schematic image"
              >
                <Download className="h-3 w-3" />
                PNG
              </button>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-cyan-500/20 bg-slate-900/60 p-6 shadow-xl relative overflow-hidden">
          {generatingImage ? (
            <div className="rounded-xl border border-dashed border-cyan-500/40 bg-slate-950 p-12 text-center space-y-3 font-mono">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan-950/50 border border-cyan-500/30 text-cyan-400">
                <Sparkles className="h-7 w-7 animate-pulse text-cyan-300" />
              </div>
              <p className="text-xs font-bold text-cyan-300">
                Invoking Muse Image (<span className="text-white">muse-image-1.0</span>)...
              </p>
              <p className="text-[11px] text-slate-400 max-w-md mx-auto">
                Synthesizing clear, high-resolution simulation architecture diagram illustrating participant interactions, protocol flow, and evaluation feedback loops.
              </p>
            </div>
          ) : visualImageUrl ? (
            <div className="space-y-4">
              <div className="relative rounded-xl border border-slate-800 overflow-hidden bg-slate-950 shadow-2xl flex items-center justify-center">
                <img
                  src={visualImageUrl}
                  alt="Synthesized Simulation Blueprint"
                  className="w-full max-h-[560px] object-contain rounded-xl"
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 text-[11px] font-mono text-slate-400 bg-slate-950 p-3 rounded-xl border border-slate-800">
                <div className="flex items-center gap-3">
                  <span className="text-cyan-400 font-semibold flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-cyan-400" />
                    Model: muse-image-1.0
                  </span>
                  <span className="text-slate-600">|</span>
                  <span>1024x1024 Isometric Blueprint</span>
                  <span className="text-slate-600">|</span>
                  <span className="text-slate-400">Diffusion Latent Synthesis</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDownloadImage}
                    className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 hover:underline"
                  >
                    <Download className="h-3 w-3" />
                    Save Full Resolution
                  </button>
                </div>
              </div>
            </div>
          ) : imageError ? (
            <div className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-6 text-center space-y-3 font-mono">
              <p className="text-xs font-bold text-rose-300">Muse Image Generation Notice</p>
              <p className="text-[11px] text-rose-400 max-w-md mx-auto">{imageError}</p>
              <button
                onClick={() => handleGenerateImage()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-rose-500/20 border border-rose-500/40 text-rose-300 hover:bg-rose-500/30 px-3 py-1.5 text-xs transition-colors"
              >
                <RefreshCw className="h-3 w-3" />
                Retry Generation
              </button>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/80 p-8 text-center space-y-3 font-mono">
              <ImageIcon className="h-8 w-8 text-slate-600 mx-auto" />
              <p className="text-xs text-slate-400">Visual simulation schematic not yet generated.</p>
              <button
                onClick={() => handleGenerateImage()}
                className="inline-flex items-center gap-2 rounded-lg bg-cyan-500 text-slate-950 hover:bg-cyan-400 px-4 py-2 text-xs font-bold transition-all shadow-md shadow-cyan-500/20"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Synthesize Visual with Muse Image
              </button>
            </div>
          )}
        </div>
      </section>

      {/* 3. Interactive Charts Deck */}
      <section className="space-y-4">
        <h2 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
          <Layers className="h-4 w-4 text-cyan-400" />
          System Dynamics & Trajectories
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Chart 1: Action / Trajectory Dynamics */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl">
            <h3 className="text-xs font-mono font-semibold text-slate-300 mb-4 flex items-center justify-between">
              <span>
                {isSupplyChain
                  ? "Supply Chain Flow Quantities"
                  : isEconomic
                  ? `${primaryField.toUpperCase()} Trajectories across Rounds (${primaryUnit})`
                  : `Evaluator ${primaryField.replace(/_/g, " ").toUpperCase()} Dynamics (${primaryUnit})`}
              </span>
              <span className="text-[10px] text-slate-500 font-normal">Recharts Interactive</span>
            </h3>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                {isSupplyChain ? (
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis 
                      dataKey="round" 
                      stroke="#64748b" 
                      fontSize={11} 
                      tickFormatter={(v) => `R${v}`} 
                    />
                    <YAxis stroke="#64748b" fontSize={11} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#334155", fontSize: "12px", fontFamily: "monospace" }} 
                    />
                    <Legend wrapperStyle={{ fontSize: "11px", fontFamily: "monospace" }} />
                    <Bar dataKey="sold" name="Units Fulfilled" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="capacity" name="Transport Capacity" fill="#334155" radius={[4, 4, 0, 0]} />
                  </BarChart>
                ) : hasActorActions ? (
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis 
                      dataKey="round" 
                      stroke="#64748b" 
                      fontSize={11} 
                      tickFormatter={(v) => `R${v}`} 
                    />
                    <YAxis stroke="#64748b" fontSize={11} domain={['auto', 'auto']} />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#334155", fontSize: "12px", fontFamily: "monospace" }} 
                    />
                    <Legend wrapperStyle={{ fontSize: "11px", fontFamily: "monospace" }} />
                    {actors.map((aid, idx) => (
                      <Line
                        key={aid}
                        type="monotone"
                        dataKey={`action_${aid}`}
                        name={`${aid.replace(/_/g, " ").toUpperCase()} (${primaryUnit})`}
                        stroke={COLOR_PALETTE[idx % COLOR_PALETTE.length]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                      />
                    ))}
                  </LineChart>
                ) : (
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="round" stroke="#64748b" fontSize={11} tickFormatter={(v) => `R${v}`} />
                    <YAxis stroke="#64748b" fontSize={11} />
                    <Tooltip contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#334155", fontSize: "12px" }} />
                    <Legend wrapperStyle={{ fontSize: "11px" }} />
                    <Line type="monotone" dataKey="cum_profit" name={isEconomic ? "Surplus ($)" : `Score (${primaryUnit})`} stroke="#06b6d4" strokeWidth={2} />
                  </LineChart>
                )}
              </ResponsiveContainer>
            </div>
          </div>

          {/* Chart 2: Cumulative Payoff / Cohort Trajectory */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl">
            <h3 className="text-xs font-mono font-semibold text-slate-300 mb-4 flex items-center justify-between">
              <span>{isEconomic ? "Cumulative Profit / Payoff Trajectory ($)" : `Cohort Assessment & Consensus (${primaryUnit})`}</span>
              <span className="text-[10px] text-slate-500 font-normal">Recharts Interactive</span>
            </h3>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis 
                    dataKey="round" 
                    stroke="#64748b" 
                    fontSize={11} 
                    tickFormatter={(v) => `R${v}`} 
                  />
                  <YAxis stroke="#64748b" fontSize={11} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: "#0b0f19", borderColor: "#334155", fontSize: "12px", fontFamily: "monospace" }} 
                  />
                  <Legend wrapperStyle={{ fontSize: "11px", fontFamily: "monospace" }} />
                  {hasActorProfits ? (
                    actors.map((aid, idx) => (
                      <Line
                        key={aid}
                        type="monotone"
                        dataKey={`cum_profit_${aid}`}
                        name={`${aid.replace(/_/g, " ").toUpperCase()} ${isEconomic ? "Payoff ($)" : `Score (${primaryUnit})`}`}
                        stroke={COLOR_PALETTE[idx % COLOR_PALETTE.length]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                      />
                    ))
                  ) : (
                    <Line 
                      type="monotone" 
                      dataKey="cum_profit" 
                      name={isEconomic ? "Consolidated Surplus ($)" : `Cohort Mean (${primaryUnit})`} 
                      stroke="#10b981" 
                      strokeWidth={2}
                      dot={{ fill: "#10b981", r: 3 }}
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </section>

      {/* 4. Turn-by-Turn Decision & Rationale Inspector */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <h2 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
            <Terminal className="h-4 w-4 text-cyan-400" />
            Decision & Thought Rationale Inspector ({filteredDecisions.length} turns)
          </h2>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative">
              <Search className="h-3.5 w-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search rationales..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-900 border border-slate-800 rounded-md pl-8 pr-3 py-1 text-slate-200 text-xs font-mono focus:border-cyan-500 focus:outline-none w-44 sm:w-56"
              />
            </div>

            {/* Actor Filter */}
            <div className="flex items-center gap-2 font-mono text-xs">
              <Filter className="h-3.5 w-3.5 text-slate-500" />
              <span className="text-slate-400">Actor:</span>
              <select
                value={selectedActorFilter}
                onChange={(e) => setSelectedActorFilter(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded-md px-2.5 py-1 text-slate-200 text-xs focus:outline-none"
              >
                <option value="all">ALL ACTORS</option>
                {actors.map((aid: any) => (
                  <option key={aid} value={aid}>{aid.replace(/_/g, " ").toUpperCase()}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950 overflow-hidden shadow-xl font-mono text-xs">
          <div className="grid grid-cols-12 bg-slate-900/80 px-4 py-3 text-[11px] font-bold text-slate-400 border-b border-slate-800">
            <div className="col-span-2">Phase / Round</div>
            <div className="col-span-2">Actor ID</div>
            <div className="col-span-3">Action Kind & Payload</div>
            <div className="col-span-5">Decision Thought Rationale</div>
          </div>

          <div className="divide-y divide-slate-850">
            {filteredDecisions.length === 0 ? (
              <div className="p-8 text-center text-slate-500">
                No decisions match your active filter.
              </div>
            ) : (
              filteredDecisions.map((d: any, idx: number) => {
                const isExpanded = expandedDecisionIdx === idx;
                return (
                  <div
                    key={idx}
                    onClick={() => setExpandedDecisionIdx(isExpanded ? null : idx)}
                    className="grid grid-cols-12 px-4 py-3 hover:bg-slate-900/40 cursor-pointer transition-colors items-center gap-2"
                  >
                    <div className="col-span-2 text-cyan-400 font-semibold truncate">
                      {d.phase || `Tick ${d.tick}`}
                    </div>
                    <div className="col-span-2 text-slate-200 font-medium truncate">
                      {d.actor_id}
                    </div>
                    <div className="col-span-3 text-emerald-400 font-mono truncate">
                      <span className="text-slate-500 mr-1">{d.action?.kind}:</span>
                      {JSON.stringify(d.action?.payload || {})}
                    </div>
                    <div className="col-span-5 text-slate-400 truncate italic">
                      &ldquo;{d.rationale}&rdquo;
                    </div>

                    {isExpanded && (
                      <div 
                        onClick={(e) => e.stopPropagation()}
                        className="col-span-12 mt-2 p-4 bg-slate-900/90 rounded-xl border border-slate-800 text-slate-300 space-y-3"
                      >
                        <div className="flex items-center justify-between">
                          <p className="text-[10px] text-cyan-400 uppercase font-bold tracking-wider flex items-center gap-2">
                            <Terminal className="h-3.5 w-3.5" />
                            Full Uncensored Thought Rationale:
                          </p>
                          <button
                            onClick={(e) => handleCopyRationale(d.rationale || "", idx, e)}
                            className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-slate-200 bg-slate-800 px-2 py-1 rounded"
                          >
                            {copiedIdx === idx ? (
                              <>
                                <Check className="h-3 w-3 text-emerald-400" />
                                Copied
                              </>
                            ) : (
                              <>
                                <Copy className="h-3 w-3" />
                                Copy Rationale
                              </>
                            )}
                          </button>
                        </div>
                        <p className="italic leading-relaxed text-xs bg-slate-950 p-3 rounded-lg border border-slate-850 text-slate-200">
                          &ldquo;{d.rationale}&rdquo;
                        </p>
                        <div className="text-[10px] text-slate-500 pt-2 border-t border-slate-800 flex justify-between">
                          <span>Action Type: <strong className="text-emerald-400">{d.action?.kind}</strong></span>
                          <span>Committed at Tick {d.tick} (Round {d.round || d.day})</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
