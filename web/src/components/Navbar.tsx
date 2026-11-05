"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BookOpen, Play, Sparkles } from "lucide-react";
import { useState } from "react";

export function Navbar() {
  const pathname = usePathname();
  const [showLoginModal, setShowLoginModal] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-50 w-full border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500 to-indigo-600 p-1.5 shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-transform">
              <Activity className="h-full w-full text-white" />
            </div>
            <div className="flex flex-col">
              <span className="font-mono text-base font-bold tracking-wider text-slate-100 group-hover:text-cyan-400 transition-colors">
                HYPOTHESIS
              </span>
              <span className="text-[10px] font-mono tracking-widest text-cyan-500/80 uppercase -mt-1">
                Autonomous Sim Lab
              </span>
            </div>
          </Link>

          {/* Navigation Links */}
          <nav className="flex items-center gap-1 sm:gap-2">
            <Link
              href="/"
              className={`px-3 py-1.5 text-xs font-mono rounded-md transition-colors ${
                pathname === "/"
                  ? "bg-slate-800 text-cyan-400"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
              }`}
            >
              Home
            </Link>
            <Link
              href="/case-studies"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-md transition-colors ${
                pathname?.startsWith("/case-studies")
                  ? "bg-slate-800 text-cyan-400"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
              }`}
            >
              <BookOpen className="h-3.5 w-3.5" />
              Featured Showcase
            </Link>
            <Link
              href="/simulate"
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono rounded-md font-semibold border transition-all ${
                pathname?.startsWith("/simulate")
                  ? "border-cyan-500 bg-cyan-500/10 text-cyan-300 shadow-sm shadow-cyan-500/30"
                  : "border-cyan-500/40 bg-gradient-to-r from-cyan-500/20 to-indigo-500/20 text-cyan-400 hover:border-cyan-400 hover:from-cyan-500/30 hover:to-indigo-500/30"
              }`}
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              Simulate
            </Link>
            <button
              onClick={() => setShowLoginModal(true)}
              className="ml-2 px-3 py-1.5 text-xs font-mono text-slate-400 hover:text-slate-200 border border-slate-800 hover:border-slate-700 rounded-md transition-colors"
            >
              Log In
            </button>
          </nav>
        </div>
      </header>

      {/* Login / Sandbox Modal */}
      {showLoginModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-2xl relative">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-100">Guest Sandbox Active</h3>
                <p className="text-xs text-slate-400 font-mono">Session ID: #GUEST-8842</p>
              </div>
            </div>
            <p className="text-sm text-slate-300 mb-6 leading-relaxed">
              Implementation in progress! You are currently operating in full unauthenticated Guest Sandbox mode. 
              All presets, custom scenarios, and real-time streaming simulation engines are immediately accessible.
            </p>
            <div className="flex justify-end">
              <button
                onClick={() => setShowLoginModal(false)}
                className="px-4 py-2 text-xs font-mono font-medium rounded-md bg-cyan-500 hover:bg-cyan-400 text-slate-950 transition-colors"
              >
                Continue as Guest
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
