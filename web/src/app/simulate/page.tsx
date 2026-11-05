"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { 
  Play, 
  Sliders, 
  Terminal, 
  ArrowRight, 
  Info,
  Cpu,
  UploadCloud,
  FileText,
  Image as ImageIcon,
  Trash2,
  AlertCircle,
  AlertTriangle,
  Upload
} from "lucide-react";

function SimulateContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedPreset = searchParams.get("preset");

  const [mode, setMode] = useState<"preset" | "custom">("preset");
  const [presets, setPresets] = useState<any[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>("supplychain");
  const [presetParams, setPresetParams] = useState<Record<string, any>>({});
  const [loadingPresets, setLoadingPresets] = useState(true);

  // Custom scenario form state
  const [customForm, setCustomForm] = useState({
    hypothesis: "Evaluate price war dynamics when a third entrant undercuts established duopoly margins",
    num_turns: 6,
    num_agents: 3,
    turn_description: "All firms simultaneously post retail price. Market demand distributes via logit choice shares. Profits are settled.",
    constraints: "Prices must be positive. Non-negative inventory balance.",
    agent_prompts: "Firm 1: Aggressive incumbent. Firm 2: Defensive follower. Firm 3: Low-cost entrant.",
  });

  const [submitting, setSubmitting] = useState(false);
  const [sandboxStatus, setSandboxStatus] = useState<"warming" | "ready" | "warning" | "error">("warming");
  const [sandboxInfo, setSandboxInfo] = useState<any>(null);

  // Supporting documents state (PDF, JPEG, PNG only)
  const [uploadedDocs, setUploadedDocs] = useState<{ name: string; type: string; size: number; data_base64: string }[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFilesSelected = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploadError(null);
    const validTypes = ["application/pdf", "image/png", "image/jpeg", "image/jpg"];
    const validExts = [".pdf", ".png", ".jpg", ".jpeg"];

    Array.from(files).forEach((file) => {
      const lowerName = file.name.toLowerCase();
      const isValidExt = validExts.some((ext) => lowerName.endsWith(ext));
      const isValidType = validTypes.includes(file.type);

      if (!isValidExt && !isValidType) {
        setUploadError(`File "${file.name}" rejected: Only PDF, JPEG, and PNG files are supported.`);
        return;
      }

      if (file.size > 15 * 1024 * 1024) {
        setUploadError(`File "${file.name}" exceeds 15MB size limit.`);
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        const base64Str = reader.result as string;
        setUploadedDocs((prev) => [
          ...prev.filter((d) => d.name !== file.name),
          {
            name: file.name,
            type: file.type || (lowerName.endsWith(".pdf") ? "application/pdf" : "image/png"),
            size: file.size,
            data_base64: base64Str,
          },
        ]);
      };
      reader.readAsDataURL(file);
    });
  };

  const handleRemoveDoc = (name: string) => {
    setUploadedDocs((prev) => prev.filter((d) => d.name !== name));
  };

  useEffect(() => {
    // Background sandbox preparation while user configures or chooses simulation
    fetch("http://localhost:8000/api/sandbox/prepare", { method: "POST" })
      .then((res) => res.json())
      .then((data) => {
        setSandboxStatus(data.status || "ready");
        setSandboxInfo(data);
      })
      .catch((err) => {
        console.error("Sandbox warmup error:", err);
        setSandboxStatus("error");
      });

    fetch("http://localhost:8000/api/presets")
      .then((res) => res.json())
      .then((data) => {
        setPresets(data);
        if (data.length > 0) {
          const initialId = requestedPreset && data.some((p: any) => p.id === requestedPreset) 
            ? requestedPreset 
            : data[0].id;
          setSelectedPresetId(initialId);
          const found = data.find((p: any) => p.id === initialId);
          if (found) setPresetParams(found.default_parameters || {});
        }
        setLoadingPresets(false);
      })
      .catch((err) => {
        console.error("Failed to fetch presets:", err);
        setLoadingPresets(false);
      });
  }, [requestedPreset]);

  const [presetError, setPresetError] = useState<string | null>(null);

  const handleSelectPreset = (id: string) => {
    setSelectedPresetId(id);
    setPresetError(null);
    const found = presets.find((p) => p.id === id);
    if (found) setPresetParams(found.default_parameters || {});
  };

  const handleParamChange = (name: string, value: any) => {
    setPresetParams((prev) => ({ ...prev, [name]: value }));
  };

  const handlePresetPdfUpload = (files: FileList | null, fieldName: string) => {
    if (!files || files.length === 0) return;
    setPresetError(null);
    const file = files[0];
    const lowerName = file.name.toLowerCase();

    if (!lowerName.endsWith(".pdf") && file.type !== "application/pdf") {
      setPresetError(`PDF parsing is faulty: '${file.name}' is not a valid PDF file. Only .pdf files are accepted.`);
      return;
    }

    if (file.size === 0) {
      setPresetError(`PDF parsing is faulty: '${file.name}' is empty (0 bytes).`);
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const b64 = e.target?.result as string;
      handleParamChange(fieldName, {
        name: file.name,
        type: "application/pdf",
        size: file.size,
        data_base64: b64,
      });
    };
    reader.onerror = () => {
      setPresetError(`PDF parsing is faulty: Failed to read file '${file.name}'.`);
    };
    reader.readAsDataURL(file);
  };

  // Launch Instant Preset
  const handleLaunchPreset = async () => {
    setPresetError(null);
    setSubmitting(true);
    try {
      const res = await fetch("http://localhost:8000/api/simulations/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "preset",
          scenario_id: selectedPresetId,
          parameters: presetParams,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const errorDetail = data.detail || "Failed to start simulation.";
        setPresetError(errorDetail);
        setSubmitting(false);
        return;
      }
      if (data.job_id) {
        router.push(`/simulate/live/${data.job_id}`);
      }
    } catch (err: any) {
      console.error("Failed to run preset:", err);
      setPresetError("Failed to start simulation. Ensure FastAPI backend is running on :8000.");
      setSubmitting(false);
    }
  };

  // Proceed to Alignment & Verification (Custom Pathway)
  const handleProceedToVerify = () => {
    // Store in session storage and navigate
    sessionStorage.setItem("hypothesis_custom_spec", JSON.stringify({
      ...customForm,
      supporting_documents: uploadedDocs,
    }));
    router.push("/simulate/verify");
  };

  const currentPreset = presets.find((p) => p.id === selectedPresetId);

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      {/* Page Header */}
      <div className="border-b border-slate-800 pb-8 mb-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-extrabold text-slate-100 flex items-center gap-3">
                <Terminal className="h-7 w-7 text-cyan-400" />
                Simulation Studio
              </h1>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-mono font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Live API Active
              </span>
            </div>
            <p className="mt-2 text-sm text-slate-400">
              Autonomous multi-agent feedback and interaction studio powered by live reasoning LLMs and domain-adaptive mechanisms. Looking for pre-computed archives? Explore the{" "}
              <a href="/case-studies" className="text-cyan-400 hover:underline font-semibold">Featured Showcase</a>.
            </p>
          </div>

          {/* Mode Toggle Tabs */}
          <div className="flex rounded-lg border border-slate-800 bg-slate-950 p-1 w-fit font-mono text-xs">
            <button
              onClick={() => setMode("preset")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-md font-semibold transition-all ${
                mode === "preset"
                  ? "bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Sliders className="h-3.5 w-3.5" />
              Instant Presets
            </button>
            <button
              onClick={() => setMode("custom")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-md font-semibold transition-all ${
                mode === "custom"
                  ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Cpu className="h-3.5 w-3.5" />
              Autonomous Lab
            </button>
          </div>
        </div>

        {/* Real-time Muse Code Agent Sandbox Preparation Banner */}
        <div className="mt-5">
          {sandboxStatus === "ready" && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-500/30 bg-emerald-950/20 px-4 py-2.5 font-mono text-xs text-emerald-300">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
                </span>
                <span className="font-bold text-emerald-400">Muse Code Agent Online</span>
                <span className="text-slate-400">{"// Isolated Sandbox Armed & Awaiting Input"}</span>
              </div>
              {sandboxInfo?.model && (
                <span className="text-[11px] font-semibold bg-emerald-900/40 text-emerald-200 px-2.5 py-0.5 rounded border border-emerald-700/50">
                  Model: {sandboxInfo.model}
                </span>
              )}
            </div>
          )}
          {sandboxStatus === "warming" && (
            <div className="flex items-center gap-2.5 rounded-xl border border-cyan-500/30 bg-cyan-950/20 px-4 py-2.5 font-mono text-xs text-cyan-300">
              <span className="h-2.5 w-2.5 rounded-full bg-cyan-400 animate-pulse" />
              <span>Arming Muse Code Agent Sandbox & Verifying Gateway Relay...</span>
            </div>
          )}
          {(sandboxStatus === "warning" || sandboxStatus === "error") && (
            <div className="flex items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-950/20 px-4 py-2.5 font-mono text-xs text-amber-300">
              <span>⚠️ {sandboxInfo?.message || "Sandbox Notice: Gateway relay checking credentials."}</span>
              <a href="/case-studies" className="text-cyan-400 underline hover:text-cyan-300">View Showcase Archives</a>
            </div>
          )}
        </div>
      </div>

      {/* Pathway A: Instant Presets */}
      {mode === "preset" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Preset Selector Sidebar */}
          <div className="lg:col-span-5 space-y-3">
            <h2 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider mb-2">
              Select Verified Benchmark
            </h2>
            {loadingPresets ? (
              <p className="text-xs font-mono text-cyan-400">Loading presets...</p>
            ) : (
              presets.map((preset) => (
                <div
                  key={preset.id}
                  onClick={() => handleSelectPreset(preset.id)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    selectedPresetId === preset.id
                      ? "border-cyan-500 bg-cyan-950/20 shadow-md shadow-cyan-500/10"
                      : "border-slate-800 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-mono font-semibold text-cyan-400 uppercase tracking-widest">
                      {preset.category}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">
                      {preset.actors?.length || 2} Actors
                    </span>
                  </div>
                  <h3 className="text-sm font-bold text-slate-100">{preset.title}</h3>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {preset.tagline}
                  </p>
                </div>
              ))
            )}
          </div>

          {/* Preset Parameter Deck */}
          <div className="lg:col-span-7">
            {currentPreset && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 shadow-xl">
                <div className="border-b border-slate-800 pb-5 mb-6">
                  <span className="text-xs font-mono font-semibold text-cyan-400 uppercase tracking-widest">
                    CONFIGURABLE PARAMETERS
                  </span>
                  <h2 className="text-2xl font-bold text-slate-100 mt-1">{currentPreset.title}</h2>
                  <p className="text-xs text-slate-300 mt-2 leading-relaxed">
                    {currentPreset.description}
                  </p>
                </div>

                {/* Actor Roster */}
                <div className="mb-6">
                  <h3 className="text-xs font-mono font-semibold text-slate-400 uppercase mb-3">
                    Active Agent Organizations
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {currentPreset.actors?.map((actor: any) => (
                      <div
                        key={actor.id}
                        className="rounded-lg border border-slate-800 bg-slate-950 p-2.5 text-xs font-mono"
                      >
                        <div className="flex items-center gap-1.5 mb-1">
                          <div
                            className="h-2 w-2 rounded-full"
                            style={{ backgroundColor: actor.color || "#06B6D4" }}
                          />
                          <span className="font-bold text-slate-200 truncate">{actor.id}</span>
                        </div>
                        <p className="text-[10px] text-slate-400 truncate">{actor.role}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Parameter Sliders / Inputs */}
                <div className="space-y-4 mb-8">
                  <h3 className="text-xs font-mono font-semibold text-slate-400 uppercase">
                    Environmental Controls
                  </h3>
                  {currentPreset.parameter_schema?.map((field: any) => (
                    <div key={field.name} className="bg-slate-950/60 rounded-xl p-4 border border-slate-800/80">
                      <div className="flex justify-between items-center mb-2">
                        <label className="text-xs font-mono font-medium text-slate-300">
                          {field.label}
                        </label>
                        {field.type !== "file" && (
                          <span className="text-xs font-mono font-bold text-cyan-400">
                            {presetParams[field.name] ?? field.default}
                          </span>
                        )}
                      </div>
                      {field.type === "number" ? (
                        <input
                          type="range"
                          min={field.min}
                          max={field.max}
                          step={field.step || 1}
                          value={presetParams[field.name] ?? field.default}
                          onChange={(e) => handleParamChange(field.name, parseFloat(e.target.value))}
                          className="w-full accent-cyan-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
                        />
                      ) : field.type === "select" ? (
                        <select
                          value={presetParams[field.name] ?? field.default}
                          onChange={(e) => handleParamChange(field.name, e.target.value)}
                          className="w-full bg-slate-900 border border-slate-700 rounded-md px-3 py-1.5 text-xs font-mono text-slate-200"
                        >
                          {field.options?.map((opt: string) => (
                            <option key={opt} value={opt}>
                              {opt.toUpperCase()}
                            </option>
                          ))}
                        </select>
                      ) : field.type === "file" ? (
                        <div>
                          {presetParams[field.name] ? (
                            <div className="flex items-center justify-between p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-xs font-mono">
                              <div className="flex items-center gap-2 text-emerald-300 truncate">
                                <FileText className="h-4 w-4 shrink-0 text-emerald-400" />
                                <span className="font-semibold truncate">{presetParams[field.name].name}</span>
                                <span className="text-slate-400 text-[11px]">
                                  ({(presetParams[field.name].size / 1024).toFixed(1)} KB)
                                </span>
                              </div>
                              <button
                                type="button"
                                onClick={() => handleParamChange(field.name, null)}
                                className="text-xs text-rose-400 hover:text-rose-300 underline font-mono shrink-0 ml-3"
                              >
                                Remove (Use Default)
                              </button>
                            </div>
                          ) : (
                            <label className="flex flex-col items-center justify-center border-2 border-dashed border-slate-700/80 hover:border-cyan-500/60 rounded-xl p-4 bg-slate-900/40 cursor-pointer transition-colors group">
                              <Upload className="h-5 w-5 text-slate-400 group-hover:text-cyan-400 mb-1.5 transition-colors" />
                              <span className="text-xs font-mono text-slate-300 group-hover:text-cyan-300 text-center">
                                Drop custom PDF manuscript here, or <span className="underline text-cyan-400">browse</span>
                              </span>
                              <span className="text-[11px] font-mono text-slate-500 mt-1">
                                Accepts PDF (.pdf) only • Defaults to &quot;Waiting for Humphrey&quot; if omitted
                              </span>
                              <input
                                type="file"
                                accept=".pdf,application/pdf"
                                className="hidden"
                                onChange={(e) => handlePresetPdfUpload(e.target.files, field.name)}
                              />
                            </label>
                          )}
                          {field.description && (
                            <p className="text-[11px] font-mono text-slate-400 mt-2 leading-relaxed">
                              {field.description}
                            </p>
                          )}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>

                {/* Theoretical Benchmark Notice */}
                <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-950/80 text-xs font-mono text-slate-400 flex items-start gap-2.5 mb-6">
                  <Info className="h-4 w-4 text-cyan-400 shrink-0 mt-0.5" />
                  <span>{currentPreset.theoretical_benchmark}</span>
                </div>

                {/* Error Banner */}
                {presetError && (
                  <div className="p-3.5 rounded-lg border border-rose-500/40 bg-rose-950/40 text-xs font-mono text-rose-300 flex items-start gap-2.5 mb-6">
                    <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <span className="font-bold">Error: </span>
                      <span>{presetError}</span>
                    </div>
                  </div>
                )}

                {/* Run CTA Button */}
                <button
                  onClick={handleLaunchPreset}
                  disabled={submitting}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 py-3.5 text-sm font-mono font-bold text-slate-950 shadow-lg shadow-cyan-500/25 transition-all disabled:opacity-50"
                >
                  <Play className="h-4 w-4 fill-current" />
                  {submitting ? "Launching Live Telemetry..." : "Execute Simulation Preset (~30s)"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Pathway B: Custom Autonomous Laboratory */}
      {mode === "custom" && (
        <div className="max-w-3xl mx-auto rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 shadow-xl">
          <div className="border-b border-slate-800 pb-5 mb-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-mono text-indigo-400 mb-3">
              <Cpu className="h-3.5 w-3.5" />
              <span>Headless Muse Code Authoring Sandbox</span>
            </div>
            <h2 className="text-2xl font-bold text-slate-100">
              Author Custom Economic Simulation
            </h2>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Describe your research hypothesis in plain English. The coding agent will synthesize the 
              typed Pydantic contracts, turn schedule, discrete mechanics, and verify them in an isolated Docker sandbox.
            </p>
          </div>

          <div className="space-y-5">
            {/* 1. Experiment Description */}
            <div>
              <label className="block text-xs font-mono font-bold text-slate-300 uppercase mb-2">
                Experiment Hypothesis & Goal <span className="text-rose-400">*</span>
              </label>
              <textarea
                rows={3}
                value={customForm.hypothesis}
                onChange={(e) => setCustomForm({ ...customForm, hypothesis: e.target.value })}
                placeholder="What behavior or economic dynamic do you wish to test?"
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {/* 2. Turns & Agents */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono font-bold text-slate-300 uppercase mb-2">
                  Number of Rounds / Turns <span className="text-rose-400">*</span>
                </label>
                <input
                  type="number"
                  min={1}
                  max={25}
                  value={customForm.num_turns}
                  onChange={(e) => setCustomForm({ ...customForm, num_turns: parseInt(e.target.value) || 1 })}
                  className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2.5 text-xs font-mono text-slate-200 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-mono font-bold text-slate-300 uppercase mb-2">
                  Number of Agents <span className="text-rose-400">*</span>
                </label>
                <input
                  type="number"
                  min={2}
                  max={8}
                  value={customForm.num_agents}
                  onChange={(e) => setCustomForm({ ...customForm, num_agents: parseInt(e.target.value) || 2 })}
                  className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2.5 text-xs font-mono text-slate-200 focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            {/* 3. Turn Protocol */}
            <div>
              <label className="block text-xs font-mono font-bold text-slate-300 uppercase mb-2">
                Turn Description (What happens in 1 round) <span className="text-rose-400">*</span>
              </label>
              <textarea
                rows={3}
                value={customForm.turn_description}
                onChange={(e) => setCustomForm({ ...customForm, turn_description: e.target.value })}
                placeholder="E.g., In phase 1 buyers bid, in phase 2 sellers set quantities, in phase 3 market clears..."
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {/* 4. Constraints */}
            <div>
              <label className="block text-xs font-mono font-bold text-slate-300 uppercase mb-2">
                Physical / Economic Constraints <span className="text-slate-500">(Optional)</span>
              </label>
              <input
                type="text"
                value={customForm.constraints}
                onChange={(e) => setCustomForm({ ...customForm, constraints: e.target.value })}
                placeholder="E.g., Budget conservation, non-negative capacity, 1-day transit delay..."
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {/* 5. Agent Prompts / Personas */}
            <div>
              <label className="block text-xs font-mono font-bold text-slate-300 uppercase mb-2">
                Agent Personas & Objectives <span className="text-slate-500">(Optional)</span>
              </label>
              <textarea
                rows={2}
                value={customForm.agent_prompts}
                onChange={(e) => setCustomForm({ ...customForm, agent_prompts: e.target.value })}
                placeholder="By default, symmetric profit-maximizers are assumed. Enter custom behavioral roles here."
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2.5 text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {/* 6. Supporting Documents & Empirical Figures (PDF, JPEG, PNG only) */}
            <div>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-2">
                <label className="block text-xs font-mono font-bold text-slate-300 uppercase">
                  Supporting Documents & Research Data <span className="text-slate-500">(Optional)</span>
                </label>
                <span className="text-[10px] font-mono font-semibold text-cyan-400 bg-cyan-950/60 px-2.5 py-0.5 rounded border border-cyan-800/40">
                  Supported formats: PDF, JPEG, PNG only
                </span>
              </div>

              {/* Upload Drop Zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  handleFilesSelected(e.dataTransfer.files);
                }}
                className={`relative rounded-xl border border-dashed p-6 text-center transition-all ${
                  isDragging
                    ? "border-cyan-400 bg-cyan-950/20"
                    : "border-slate-800 bg-slate-950 hover:border-slate-700"
                }`}
              >
                <input
                  type="file"
                  multiple
                  accept=".pdf,image/png,image/jpeg,image/jpg"
                  onChange={(e) => handleFilesSelected(e.target.files)}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                />
                <div className="flex flex-col items-center justify-center gap-2">
                  <div className="h-10 w-10 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-cyan-400">
                    <UploadCloud className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-xs font-mono text-slate-200">
                      <span className="text-cyan-400 font-semibold underline">Click to upload</span> or drag and drop supporting research
                    </p>
                    <p className="text-[11px] font-mono text-slate-500 mt-1">
                      Upload PDF papers, empirical charts, or market structure diagrams (Max 15MB)
                    </p>
                  </div>
                </div>
              </div>

              {/* Upload Validation Error Notice */}
              {uploadError && (
                <div className="mt-2.5 p-2.5 rounded-lg bg-rose-950/30 border border-rose-500/40 text-[11px] font-mono text-rose-300 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-rose-400 shrink-0" />
                  <span>{uploadError}</span>
                </div>
              )}

              {/* Uploaded Files List */}
              {uploadedDocs.length > 0 && (
                <div className="mt-3 space-y-2">
                  <p className="text-[10px] font-mono text-slate-400 uppercase tracking-wider font-bold">
                    Attached Files ({uploadedDocs.length})
                  </p>
                  <div className="divide-y divide-slate-850 rounded-lg border border-slate-800 bg-slate-950 overflow-hidden">
                    {uploadedDocs.map((doc) => {
                      const isPdf = doc.type.includes("pdf") || doc.name.toLowerCase().endsWith(".pdf");
                      return (
                        <div key={doc.name} className="flex items-center justify-between p-2.5 text-xs font-mono">
                          <div className="flex items-center gap-2.5 min-w-0">
                            {isPdf ? (
                              <FileText className="h-4 w-4 text-rose-400 shrink-0" />
                            ) : (
                              <ImageIcon className="h-4 w-4 text-cyan-400 shrink-0" />
                            )}
                            <span className="text-slate-200 truncate">{doc.name}</span>
                            <span className="text-[10px] text-slate-500 shrink-0">
                              ({(doc.size / 1024).toFixed(1)} KB)
                            </span>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleRemoveDoc(doc.name)}
                            className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-900 transition-colors"
                            title="Remove file"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* Submit to Verification */}
            <div className="pt-4">
              <button
                onClick={handleProceedToVerify}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-cyan-500 hover:from-indigo-400 hover:to-cyan-400 py-3.5 text-sm font-mono font-bold text-white shadow-lg shadow-indigo-500/25 transition-all"
              >
                Proceed to Model Alignment & Verification
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SimulatePage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-64 items-center justify-center font-mono text-sm text-cyan-400">
          Loading Simulation Studio...
        </div>
      }
    >
      <SimulateContent />
    </Suspense>
  );
}
