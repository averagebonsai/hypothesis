"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiUrl } from "@/lib/api";
import { 
  CheckCircle2, 
  Edit3, 
  Play, 
  ShieldAlert, 
  Sparkles, 
  Terminal, 
  Plus, 
  Trash2, 
  X, 
  Save, 
  AlertTriangle, 
  BookOpen,
  RefreshCw,
  Image as ImageIcon
} from "lucide-react";

export default function VerificationPage() {
  const router = useRouter();
  const [alignmentData, setAlignmentData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [rawForm, setRawForm] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  // Editable fields state
  const [editHypothesis, setEditHypothesis] = useState("");
  const [editTurnDesc, setEditTurnDesc] = useState("");
  const [editNumTurns, setEditNumTurns] = useState(5);
  const [editNumAgents, setEditNumAgents] = useState(3);
  const [editAssumptions, setEditAssumptions] = useState<string[]>([]);
  const [editFeasibilityRules, setEditFeasibilityRules] = useState<string[]>([]);
  const [newAssumptionText, setNewAssumptionText] = useState("");
  const [contradictions, setContradictions] = useState<string[]>([]);
  const [visualImageUrl, setVisualImageUrl] = useState<string | null>(null);
  const [generatingImage, setGeneratingImage] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);

  const handleGenerateImage = async (promptOverride?: string) => {
    const prompt = promptOverride || alignmentData?.schematic_image_prompt;
    if (!prompt) return;
    setGeneratingImage(true);
    setImageError(null);
    try {
      const res = await fetch(apiUrl("/api/simulations/generate-image"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
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
      console.error(err);
      setImageError(err.message || "Failed to generate visual schematic with Muse Image.");
    } finally {
      setGeneratingImage(false);
    }
  };

  useEffect(() => {
    const raw = sessionStorage.getItem("hypothesis_custom_spec");
    if (!raw) {
      router.push("/simulate");
      return;
    }
    const parsed = JSON.parse(raw);
    setRawForm(parsed);
    setEditHypothesis(parsed.hypothesis || "");
    setEditTurnDesc(parsed.turn_description || "");
    setEditNumTurns(parsed.num_turns || 5);
    setEditNumAgents(parsed.num_agents || 3);

    fetch(apiUrl("/api/simulations/align"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed),
    })
      .then(async (res) => {
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || "Unable to connect to the LLM. Please verify your API credentials.");
        }
        return res.json();
      })
      .then((data) => {
        setAlignmentData(data);
        setEditAssumptions(data.assumptions || []);
        setEditFeasibilityRules(data.feasibility_rules || []);
        setContradictions(data.contradictions || []);
        setConnectionError(null);
        setLoading(false);
        if (data.schematic_image_prompt) {
          handleGenerateImage(data.schematic_image_prompt);
        }
      })
      .catch((err) => {
        console.error("Alignment failed:", err);
        setConnectionError(err.message || "Unable to connect to the LLM.");
        setLoading(false);
      });
  }, [router]);

  // Apply all edits
  const handleSaveEdits = async () => {
    setLoading(true);
    const updatedForm = {
      ...rawForm,
      hypothesis: editHypothesis,
      turn_description: editTurnDesc,
      num_turns: editNumTurns,
      num_agents: editNumAgents,
    };
    setRawForm(updatedForm);
    sessionStorage.setItem("hypothesis_custom_spec", JSON.stringify(updatedForm));

    try {
      const res = await fetch(apiUrl("/api/simulations/align"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updatedForm),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Unable to connect to the LLM. Please verify your API credentials.");
      }
      const data = await res.json();
      // Keep any user-added or modified assumptions if preserved
      setAlignmentData({
        ...data,
        assumptions: editAssumptions.length > 0 ? editAssumptions : data.assumptions,
        feasibility_rules: editFeasibilityRules.length > 0 ? editFeasibilityRules : data.feasibility_rules,
      });
      setContradictions(data.contradictions || []);
      setConnectionError(null);
      setIsEditing(false);
      setLoading(false);
      if (data.schematic_image_prompt) {
        handleGenerateImage(data.schematic_image_prompt);
      }
    } catch (err: any) {
      console.error(err);
      setConnectionError(err.message || "Unable to connect to the LLM.");
      setLoading(false);
    }
  };

  const handleAddAssumption = () => {
    if (!newAssumptionText.trim()) return;
    setEditAssumptions([...editAssumptions, newAssumptionText.trim()]);
    setNewAssumptionText("");
  };

  const handleRemoveAssumption = (idx: number) => {
    setEditAssumptions(editAssumptions.filter((_, i) => i !== idx));
  };

  const handleResolveContradictionAsAssumption = (index: number) => {
    const text = contradictions[index];
    const resolvedAssumption = `Resolved contradiction: ${text} (formally resolved into an explicit boundary modeling assumption).`;
    setEditAssumptions((prev) => [...prev, resolvedAssumption]);
    setContradictions((prev) => prev.filter((_, i) => i !== index));
  };

  const handleDismissContradiction = (index: number) => {
    setContradictions((prev) => prev.filter((_, i) => i !== index));
  };

  const handleApproveAndExecute = async () => {
    if (contradictions.length > 0) {
      alert("Please resolve all contradictions before executing.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(apiUrl("/api/simulations/run"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: "custom",
          scenario_id: "custom_experiment",
          parameters: {
            ...rawForm,
            hypothesis: editHypothesis,
            turn_description: editTurnDesc,
            num_turns: editNumTurns,
            num_agents: editNumAgents,
            custom_assumptions: editAssumptions,
            contradictions: contradictions,
            visual_image_url: visualImageUrl,
            blueprint: alignmentData?.blueprint,
          },
        }),
      });
      const data = await res.json();
      if (data.job_id) {
        router.push(`/simulate/live/${data.job_id}`);
      }
    } catch (err) {
      console.error("Execution dispatch failed:", err);
      alert("Failed to dispatch to sandbox worker.");
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-20 text-center font-mono">
        <Sparkles className="h-8 w-8 text-cyan-400 mx-auto animate-pulse mb-4" />
        <p className="text-sm text-cyan-300">Synthesizing mathematical contract & assumptions...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800 pb-6 gap-4">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono text-cyan-400 mb-3">
            <Terminal className="h-3.5 w-3.5" />
            <span>Stage 2 // Model Alignment & Verification</span>
          </div>
          <h1 className="text-3xl font-extrabold text-slate-100">
            Verify Simulation Contract
          </h1>
          <p className="mt-2 text-xs font-mono text-slate-400">
            Inspect the interpreted game protocol, assumptions, and visual schematic. You can edit any parameter below.
          </p>
        </div>

        <button
          onClick={() => setIsEditing(!isEditing)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-mono text-xs font-semibold border transition-all ${
            isEditing
              ? "border-amber-500/50 bg-amber-500/10 text-amber-300"
              : "border-slate-800 bg-slate-900 text-slate-300 hover:border-slate-700"
          }`}
        >
          {isEditing ? (
            <>
              <X className="h-3.5 w-3.5" />
              Exit Edit Mode
            </>
          ) : (
            <>
              <Edit3 className="h-3.5 w-3.5 text-cyan-400" />
              Edit Requirements & Assumptions
            </>
          )}
        </button>
      </div>

      {/* Connection Error Banner */}
      {connectionError && (
        <div className="rounded-2xl border border-rose-500/50 bg-rose-950/20 p-6 sm:p-8 font-mono text-xs shadow-2xl space-y-4">
          <div className="flex items-center gap-3 text-rose-400 font-bold text-sm">
            <AlertTriangle className="h-6 w-6 text-rose-400 shrink-0" />
            <span>Unable to Connect to the LLM</span>
          </div>
          <p className="text-slate-300 leading-relaxed text-xs">
            {connectionError}
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Link
              href="/case-studies"
              className="flex items-center gap-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-4 py-2.5 font-bold transition-all shadow-md shadow-cyan-500/20"
            >
              <BookOpen className="h-4 w-4" />
              Explore Completed Simulations in Featured Showcase
            </Link>
            <button
              onClick={() => router.push("/simulate")}
              className="px-4 py-2.5 rounded-lg border border-slate-800 bg-slate-900 text-slate-300 hover:text-white transition-colors"
            >
              Back to Studio
            </button>
          </div>
        </div>
      )}

      {/* Comprehensive In-Place Editor Panel */}
      {isEditing && (
        <div className="rounded-2xl border border-cyan-500/40 bg-slate-950 p-6 sm:p-8 font-mono text-xs shadow-2xl space-y-6">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <span className="font-bold text-cyan-400 text-sm uppercase tracking-wider">
              Edit All Requirements & Parameters
            </span>
            <span className="text-[10px] text-slate-400">Modify any field directly</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-slate-300 font-bold mb-1.5 uppercase">
                Number of Turns / Horizon
              </label>
              <input
                type="number"
                min={1}
                max={30}
                value={editNumTurns}
                onChange={(e) => setEditNumTurns(parseInt(e.target.value) || 1)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-slate-300 font-bold mb-1.5 uppercase">
                Number of Autonomous Agents
              </label>
              <input
                type="number"
                min={2}
                max={8}
                value={editNumAgents}
                onChange={(e) => setEditNumAgents(parseInt(e.target.value) || 2)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-slate-100 focus:border-cyan-500 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-slate-300 font-bold mb-1.5 uppercase">
              Experiment Hypothesis & Goal
            </label>
            <textarea
              rows={2}
              value={editHypothesis}
              onChange={(e) => setEditHypothesis(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3 text-slate-100 focus:border-cyan-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-slate-300 font-bold mb-1.5 uppercase">
              1-Round Turn Sequence & Protocol
            </label>
            <textarea
              rows={3}
              value={editTurnDesc}
              onChange={(e) => setEditTurnDesc(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3 text-slate-100 focus:border-cyan-500 focus:outline-none"
            />
          </div>

          {/* Edit Assumptions List */}
          <div>
            <label className="block text-slate-300 font-bold mb-2 uppercase">
              Explicit Modeling Assumptions (Editable List)
            </label>
            <div className="space-y-2 mb-3">
              {editAssumptions.map((asm, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={asm}
                    onChange={(e) => {
                      const copy = [...editAssumptions];
                      copy[idx] = e.target.value;
                      setEditAssumptions(copy);
                    }}
                    className="flex-1 bg-slate-900 border border-slate-800 rounded px-3 py-1.5 text-slate-200 focus:border-cyan-500 focus:outline-none"
                  />
                  <button
                    onClick={() => handleRemoveAssumption(idx)}
                    className="p-1.5 rounded hover:bg-slate-800 text-rose-400"
                    title="Remove assumption"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Add custom assumption..."
                value={newAssumptionText}
                onChange={(e) => setNewAssumptionText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddAssumption()}
                className="flex-1 bg-slate-900 border border-slate-800 rounded px-3 py-1.5 text-slate-300 focus:border-cyan-500 focus:outline-none placeholder:text-slate-600"
              />
              <button
                onClick={handleAddAssumption}
                className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded"
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </button>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              onClick={() => setIsEditing(false)}
              className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300"
            >
              Cancel
            </button>
            <button
              onClick={handleSaveEdits}
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold"
            >
              <Save className="h-3.5 w-3.5" />
              Apply Changes & Re-Align
            </button>
          </div>
        </div>
      )}

      {/* Main Verification Cards Stack */}
      <div className="space-y-6">
        {/* Card 1: Interpreted Mechanism Protocol */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 font-mono text-xs shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
            <span className="font-bold text-slate-200 uppercase tracking-wider">
              1. Interpreted Mechanism Protocol
            </span>
            <span className="text-[10px] text-cyan-400 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800/40 font-bold">
              {alignmentData?.blueprint?.domain_archetype ? `Archetype: ${alignmentData.blueprint.domain_archetype.replace(/_/g, ' ').toUpperCase()}` : "Contract Verified"}
            </span>
          </div>
          <div className="text-slate-300 whitespace-pre-line leading-relaxed bg-slate-950 p-4 rounded-lg border border-slate-850">
            {alignmentData?.readback}
          </div>
        </div>

        {/* Card 2: Explicit Assumptions */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-6 font-mono text-xs shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
            <span className="font-bold text-slate-200 uppercase tracking-wider">
              2. Explicit Modeling Assumptions ({editAssumptions.length})
            </span>
            <button
              onClick={() => setIsEditing(true)}
              className="text-[10px] text-cyan-400 hover:underline flex items-center gap-1"
            >
              <Edit3 className="h-3 w-3" />
              Edit Assumptions
            </button>
          </div>
          <ul className="space-y-2 text-slate-300">
            {editAssumptions.map((asm: string, idx: number) => (
              <li key={idx} className="flex items-start gap-2.5">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>{asm}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Card 3: Feasibility Enforcement & Penalties */}
        <div className="rounded-xl border border-amber-500/30 bg-amber-950/10 p-6 font-mono text-xs shadow-lg">
          <div className="flex items-center justify-between border-b border-amber-500/20 pb-3 mb-4">
            <div className="flex items-center gap-2 text-amber-400">
              <ShieldAlert className="h-4 w-4" />
              <span className="font-bold uppercase tracking-wider">
                3. Feasibility Enforcement & Penalty Rules
              </span>
            </div>
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Live API Policy Active
            </span>
          </div>
          <ul className="space-y-2 text-slate-300">
            {editFeasibilityRules.map((rule: string, idx: number) => (
              <li key={idx} className="flex items-start gap-2.5">
                <div className="h-1.5 w-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                <span>{rule}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Card 4: Simulation Image Canvas (Generated by Muse Image) */}
        <div className="rounded-xl border border-cyan-500/30 bg-slate-900/60 p-6 font-mono text-xs shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <ImageIcon className="h-4 w-4 text-cyan-400" />
              <span className="font-bold text-slate-200 uppercase tracking-wider">
                4. Visual Simulation Schematic (Muse Image)
              </span>
            </div>
            <div className="flex items-center gap-2">
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
                    Muse Image Ready (1024x1024)
                  </>
                ) : generatingImage ? (
                  <>
                    <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                    Generating with muse-image-1.0...
                  </>
                ) : (
                  "Muse Image Ready"
                )}
              </span>
              {alignmentData?.schematic_image_prompt && (
                <button
                  onClick={() => handleGenerateImage()}
                  disabled={generatingImage}
                  className="flex items-center gap-1 text-[10px] bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded border border-slate-700 transition-colors disabled:opacity-50"
                  title="Generate or regenerate visual schematic"
                >
                  <RefreshCw className={`h-3 w-3 ${generatingImage ? "animate-spin" : ""}`} />
                  {visualImageUrl ? "Regenerate" : "Generate"}
                </button>
              )}
            </div>
          </div>

          {/* Visual Display Container */}
          {generatingImage ? (
            <div className="rounded-xl border border-dashed border-cyan-500/40 bg-slate-950 p-12 text-center space-y-3">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan-950/50 border border-cyan-500/30 text-cyan-400">
                <Sparkles className="h-7 w-7 animate-pulse text-cyan-300" />
              </div>
              <p className="text-xs font-bold text-cyan-300">
                Invoking Muse Image (<span className="text-white">muse-image-1.0</span>)...
              </p>
              <p className="text-[11px] text-slate-400 max-w-md mx-auto">
                Synthesizing clear, high-resolution visual schematic illustrating the interaction protocol, participant actors, and feedback loops.
              </p>
            </div>
          ) : visualImageUrl ? (
            <div className="space-y-3">
              <div className="relative rounded-xl border border-slate-800 overflow-hidden bg-slate-950 shadow-2xl flex items-center justify-center">
                <img
                  src={visualImageUrl}
                  alt="Synthesized Simulation Blueprint"
                  className="w-full max-h-[520px] object-contain rounded-xl"
                />
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-400 bg-slate-950 p-2.5 rounded-lg border border-slate-850">
                <span className="text-cyan-400 font-semibold">Model: muse-image-1.0</span>
                <span>Resolution: 1024x1024 Vector Schematic</span>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/80 p-8 text-center space-y-3">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-slate-900 border border-slate-800 text-slate-400">
                <ImageIcon className="h-6 w-6" />
              </div>
              <p className="text-xs font-semibold text-slate-300">
                Click Generate above to synthesize the visual simulation blueprint with Muse Image.
              </p>
            </div>
          )}

          {/* Error Notice */}
          {imageError && (
            <div className="p-3 rounded-lg bg-rose-950/30 border border-rose-500/30 text-[11px] text-rose-300 flex items-center justify-between">
              <span>⚠️ {imageError}</span>
              <button
                onClick={() => handleGenerateImage()}
                className="underline text-rose-400 hover:text-rose-200"
              >
                Retry
              </button>
            </div>
          )}

          {/* Prompt Readback */}
          {alignmentData?.schematic_image_prompt && (
            <div className="pt-1">
              <p className="text-[10px] text-slate-500 italic bg-slate-950 p-2.5 rounded-lg border border-slate-850 text-left">
                <span className="text-cyan-400/80 not-italic font-semibold">Synthesized Visual Prompt: </span>
                {alignmentData.schematic_image_prompt}
              </p>
            </div>
          )}
        </div>

        {/* Card 5: Contradictions & Material Inconsistencies */}
        <div className={`rounded-xl border p-6 font-mono text-xs shadow-lg transition-all ${
          contradictions.length > 0
            ? "border-rose-500/50 bg-rose-950/20"
            : "border-emerald-500/30 bg-emerald-950/10"
        }`}>
          <div className={`flex items-center justify-between border-b pb-3 mb-4 ${
            contradictions.length > 0 ? "border-rose-500/30" : "border-emerald-500/20"
          }`}>
            <div className="flex items-center gap-2">
              {contradictions.length > 0 ? (
                <AlertTriangle className="h-4 w-4 text-rose-400" />
              ) : (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              )}
              <span className={`font-bold uppercase tracking-wider ${
                contradictions.length > 0 ? "text-rose-300" : "text-emerald-300"
              }`}>
                5. Contradictions & Material Inconsistencies ({contradictions.length})
              </span>
            </div>
            <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-semibold border ${
              contradictions.length > 0
                ? "bg-rose-950 text-rose-300 border-rose-800"
                : "bg-emerald-950 text-emerald-400 border-emerald-800"
            }`}>
              {contradictions.length > 0 ? "Action Required Before Execution" : "Verified Coherent"}
            </span>
          </div>

          {contradictions.length > 0 ? (
            <div className="space-y-4">
              <p className="text-slate-300 leading-relaxed text-xs">
                The Muse Code Agent detected the following material contradictions or conflicting constraints in your specification. 
                You <strong className="text-rose-400">must resolve all contradictions</strong> before the simulation can continue.
              </p>
              <div className="space-y-3">
                {contradictions.map((contra: string, idx: number) => (
                  <div key={idx} className="p-3.5 bg-slate-950/90 rounded-lg border border-rose-900/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                    <div className="flex items-start gap-2.5 text-rose-200">
                      <span className="text-rose-400 font-bold shrink-0 mt-0.5">•</span>
                      <span className="leading-relaxed">{contra}</span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                      <button
                        onClick={() => handleResolveContradictionAsAssumption(idx)}
                        className="px-2.5 py-1.5 rounded bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 text-[10px] font-semibold transition-colors"
                        title="Convert into an explicit boundary assumption"
                      >
                        Resolve as Assumption
                      </button>
                      <button
                        onClick={() => handleDismissContradiction(idx)}
                        className="px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-semibold transition-colors"
                        title="Dismiss after operator review"
                      >
                        Dismiss
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3 text-slate-300">
              <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
              <span>
                ✓ No material contradictions or logical impossibilities detected. The research hypothesis, actor personas, constraints, and turn protocol are mathematically coherent and verified.
              </span>
            </div>
          )}
        </div>

        {/* Bottom CTA Button */}
        <div className="pt-4 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
          <button
            onClick={() => setIsEditing(true)}
            className="w-full sm:w-auto px-5 py-3 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-300 font-mono text-xs font-medium transition-colors"
          >
            Edit Specifications
          </button>

          <div className="w-full sm:w-auto flex-1 flex flex-col items-end gap-1.5">
            <button
              onClick={handleApproveAndExecute}
              disabled={submitting || isEditing || Boolean(connectionError) || contradictions.length > 0}
              className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 px-6 py-3.5 text-sm font-mono font-bold text-slate-950 shadow-lg shadow-cyan-500/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Play className="h-4 w-4 fill-current" />
              {submitting ? "Dispatching Sandbox Environment..." : "Approve & Execute Simulation"}
            </button>
            {contradictions.length > 0 && (
              <span className="text-[11px] font-mono text-rose-400">
                ⚠️ Execution blocked: Resolve all {contradictions.length} material contradiction(s) above to proceed.
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
