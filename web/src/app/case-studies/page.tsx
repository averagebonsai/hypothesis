"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BookOpen, Download, Play } from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
} from "recharts";

const COLOR_PALETTE = [
  "#06B6D4", // cyan
  "#10B981", // emerald
  "#EC4899", // pink
  "#F59E0B", // amber
  "#8B5CF6", // purple
  "#3B82F6", // blue
  "#EF4444", // red
];

function CaseStudyChart({ fig }: { fig: any }) {
  const categories = fig.categories || [];
  const series = fig.series || [];

  const chartData = categories.map((cat: string, cIdx: number) => {
    const row: Record<string, any> = {
      category: cat.replace("Round ", "R").replace("Day ", "D"),
      fullCategory: cat,
    };
    series.forEach((s: any) => {
      row[s.label] = s.values?.[cIdx] ?? 0;
    });
    return row;
  });

  const isLine = fig.kind === "line";

  return (
    <div className="h-56 w-full pt-2">
      <ResponsiveContainer width="100%" height="100%">
        {isLine ? (
          <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis
              dataKey="category"
              stroke="#64748b"
              fontSize={10}
              tick={{ fill: "#64748b" }}
            />
            <YAxis
              stroke="#64748b"
              fontSize={10}
              tick={{ fill: "#64748b" }}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0b0f19",
                borderColor: "#334155",
                fontSize: "11px",
                fontFamily: "monospace",
              }}
              labelFormatter={(_, payload) => payload?.[0]?.payload?.fullCategory || ""}
            />
            <Legend
              wrapperStyle={{
                fontSize: "10px",
                fontFamily: "monospace",
                paddingTop: "6px",
              }}
            />
            {series.map((s: any, sIdx: number) => (
              <Line
                key={s.label}
                type="monotone"
                dataKey={s.label}
                name={s.label}
                stroke={COLOR_PALETTE[sIdx % COLOR_PALETTE.length]}
                strokeWidth={2}
                dot={{ r: 3, fill: COLOR_PALETTE[sIdx % COLOR_PALETTE.length] }}
                activeDot={{ r: 5 }}
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis
              dataKey="category"
              stroke="#64748b"
              fontSize={10}
              tick={{ fill: "#64748b" }}
            />
            <YAxis
              stroke="#64748b"
              fontSize={10}
              tick={{ fill: "#64748b" }}
              domain={["auto", "auto"]}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0b0f19",
                borderColor: "#334155",
                fontSize: "11px",
                fontFamily: "monospace",
              }}
              labelFormatter={(_, payload) => payload?.[0]?.payload?.fullCategory || ""}
            />
            <Legend
              wrapperStyle={{
                fontSize: "10px",
                fontFamily: "monospace",
                paddingTop: "6px",
              }}
            />
            {series.map((s: any, sIdx: number) => (
              <Bar
                key={s.label}
                dataKey={s.label}
                name={s.label}
                fill={COLOR_PALETTE[sIdx % COLOR_PALETTE.length]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

export default function CaseStudiesPage() {
  const [caseStudies, setCaseStudies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/api/case-studies")
      .then((res) => res.json())
      .then((data) => {
        setCaseStudies(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch case studies:", err);
        setLoading(false);
      });
  }, []);

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="border-b border-slate-800 pb-8 mb-10">
        <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-mono text-cyan-400 mb-4">
          <BookOpen className="h-3.5 w-3.5" />
          <span>Featured Showcase // Completed Empirical Benchmarks</span>
        </div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-100">
          Featured Showcase
        </h1>
        <p className="mt-3 text-sm text-slate-400 max-w-3xl leading-relaxed">
          Pre-computed, verified simulation studies & empirical benchmarks with complete datasets and downloadable 
          analysis notebooks. Inspect market dynamics, agent observation constraints, and observed equilibrium outcomes 
          without requiring an active LLM connection.
        </p>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center font-mono text-sm text-cyan-400">
          Loading case study archives...
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-10">
          {caseStudies.map((study) => (
            <div
              key={study.id}
              className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 sm:p-8 hover:border-slate-700 transition-all shadow-xl"
            >
              <div className="flex flex-col lg:flex-row justify-between items-start gap-6 mb-6">
                <div>
                  <span className="text-xs font-mono font-semibold text-cyan-400 uppercase tracking-wider">
                    {study.preset_id.toUpperCase()} SCENARIO
                  </span>
                  <h2 className="text-2xl font-bold text-slate-100 mt-1">{study.title}</h2>
                  <p className="mt-3 text-sm text-slate-300 leading-relaxed max-w-4xl">
                    {study.abstract}
                  </p>
                </div>

                <div className="flex flex-wrap lg:flex-col gap-2.5 w-full sm:w-auto">
                  <Link
                    href={`/simulate?preset=${study.preset_id}`}
                    className="flex items-center justify-center gap-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 px-4 py-2 text-xs font-mono font-bold transition-all shadow-md shadow-cyan-500/20"
                  >
                    <Play className="h-3.5 w-3.5 fill-current" />
                    Clone & Run
                  </Link>
                  <a
                    href={`http://localhost:8000${study.notebook_url}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-center gap-2 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-800/80 text-slate-300 px-4 py-2 text-xs font-mono transition-all"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Download .ipynb
                  </a>
                </div>
              </div>

              {/* KPI metrics row */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 py-4 border-y border-slate-800/80 mb-6 bg-slate-950/40 rounded-lg px-4">
                {study.kpis?.map((kpi: any, idx: number) => (
                  <div key={idx}>
                    <p className="text-[11px] font-mono text-slate-400 uppercase tracking-wider">
                      {kpi.label}
                    </p>
                    <p className="text-base sm:text-lg font-bold font-mono text-cyan-300 mt-0.5">
                      {kpi.value}
                    </p>
                  </div>
                ))}
              </div>

              {/* Graphical figures preview */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {study.figures?.map((fig: any, fIdx: number) => (
                  <div
                    key={fIdx}
                    className="rounded-xl border border-slate-800/80 bg-slate-950 p-4 font-mono text-xs"
                  >
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-1">
                      <span className="font-semibold text-slate-200">{fig.title}</span>
                      <span className="text-[10px] text-slate-500 uppercase">{fig.kind} chart</span>
                    </div>

                    {/* Chart component */}
                    <CaseStudyChart fig={fig} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
