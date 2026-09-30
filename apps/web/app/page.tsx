"use client";

import { ChangeEvent, FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowRight, Bot, Check, FileArchive, House, LoaderCircle, LogOut, MessageCircle, Plus, Send, Sparkles, Workflow, X } from "lucide-react";

const API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
type UserState = { id: string; email: string; workspaces: { id: string; name: string; role: string }[] };
type Analysis = { id: string; status: string; stage: string; repository_name: string; repository_id: string; result?: Result | null; error?: string | null; current_stack?: string[]; target_stack?: string[] };
type Result = { status: string; repository_name: string; file_count: number; parsed_file_count: number; unsupported_file_count: number; languages: Record<string, number>; technologies: string[]; architecture_hints: string[]; warnings: string[]; dependencies: { source: string; target: string; kind: string; evidence: { file: string; start_line: number; end_line: number; detail: string } }[]; database_access: { file: string; start_line: number; detail: string }[]; api_routes: { file: string; start_line: number; detail: string }[]; risks: { name: string; score: number; detail: string; evidence: { file: string; start_line: number; end_line: number; detail: string }[] }[] };
type Plan = { id: string; title: string; generation_source?: "gemini" | "evidence"; current_stack: string[]; target_stack: string[]; phases: { id: string; title: string; objective: string; validation: string; rollback: string; tasks: { id: string; title: string; next_action: string; description: string; done_when: string; status: string; affected_files: string[] }[] }[] };
type Recent = { id: string; repository_name: string; status: string; stage: string; created_at: string };
type Simulation = { target_stack: string[]; basis: string; metrics: Record<string, number>; affected_files: string[]; modules: string[]; risks: { name: string; score: number; detail: string }[]; evidence: { file: string; start_line: number; detail: string }[] };
type Citation = { file: string; start_line: number; end_line: number };
type ChatClaim = { claim: string; type: string; confidence: number; evidence: Citation[] };
type ChatMessage = { role: "user" | "assistant"; content: string; evidence?: ChatClaim[]; model?: string; latency_ms?: number };

const STACK_GROUPS = [
  { label: "Runtime", choices: ["Node.js", "Python", "Java", "Go", "Rust", ".NET", "PHP", "Ruby"] },
  { label: "Framework", choices: ["Spring Boot", "FastAPI", "Django", "ASP.NET Core", "Express", "Laravel", "Rails"] },
  { label: "Web", choices: ["React", "Next.js", "Angular", "Vue"] },
  { label: "Data", choices: ["PostgreSQL", "MySQL", "MongoDB", "SQLite", "Redis"] },
  { label: "Platform", choices: ["AWS", "Azure", "Google Cloud", "Kubernetes"] },
];

type StackSuggestionGroups = Record<string, string[]>;

const TARGET_OPTIONS_BY_SOURCE: Record<string, StackSuggestionGroups> = {
  "node.js": { Runtime: ["Java", "Python", "Go", ".NET"] },
  python: { Runtime: ["Java", "Node.js", "Go", ".NET"] },
  java: { Runtime: ["Python", "Node.js", "Go", ".NET"] },
  go: { Runtime: ["Java", "Python", "Node.js", ".NET"] },
  rust: { Runtime: ["Java", "Python", "Go", ".NET"] },
  ".net": { Runtime: ["Java", "Python", "Node.js", "Go"] },
  php: { Runtime: ["Java", "Python", "Node.js"] },
  ruby: { Runtime: ["Java", "Python", "Node.js"] },
  express: { Framework: ["Spring Boot", "FastAPI", "Django", "ASP.NET Core"] },
  springboot: { Framework: ["FastAPI", "Django", "Express", "ASP.NET Core"] },
  fastapi: { Framework: ["Spring Boot", "Django", "Express", "ASP.NET Core"] },
  django: { Framework: ["Spring Boot", "FastAPI", "Express", "ASP.NET Core"] },
  "asp.netcore": { Framework: ["Spring Boot", "FastAPI", "Django", "Express"] },
  laravel: { Framework: ["Spring Boot", "FastAPI", "Express"] },
  rails: { Framework: ["Spring Boot", "FastAPI", "Express"] },
  react: { Web: ["Next.js", "Angular", "Vue"] },
  angular: { Web: ["React", "Next.js", "Vue"] },
  vue: { Web: ["React", "Next.js", "Angular"] },
  "next.js": { Web: ["Angular", "Vue"] },
  mongodb: { Data: ["PostgreSQL", "MySQL", "SQLite"] },
  postgresql: { Data: ["MySQL", "SQLite", "MongoDB"] },
  mysql: { Data: ["PostgreSQL", "SQLite", "MongoDB"] },
  sqlite: { Data: ["PostgreSQL", "MySQL", "MongoDB"] },
  aws: { Platform: ["Azure", "Google Cloud"] },
  azure: { Platform: ["AWS", "Google Cloud"] },
  googlecloud: { Platform: ["AWS", "Azure"] },
};

function normalizeTechnology(technology: string): string {
  return technology.toLowerCase().replace(/[^a-z0-9+#.]/g, "");
}

function detectCurrentStack(result: Result): string[] {
  const languages = Object.keys(result.languages).map((language) => language.toLowerCase());
  const technologies = result.technologies.map((technology) => technology.toLowerCase().replace(/[^a-z0-9+#.]/g, ""));
  const has = (...aliases: string[]) => aliases.some((alias) => technologies.some((technology) => technology.includes(alias.replace(/[^a-z0-9+#.]/g, ""))));
  const detected = new Set<string>();

  if (has("node.js", "nodejs") || languages.some((language) => ["javascript", "typescript"].includes(language))) detected.add("Node.js");
  if (has("express")) detected.add("Express");
  if (has("fastapi")) { detected.add("Python"); detected.add("FastAPI"); }
  if (has("django")) { detected.add("Python"); detected.add("Django"); }
  if (has("spring-boot", "springboot")) { detected.add("Java"); detected.add("Spring Boot"); }
  if (has("asp.net", "aspnetcore")) { detected.add(".NET"); detected.add("ASP.NET Core"); }
  if (has("react")) detected.add("React");
  if (has("next")) detected.add("Next.js");
  if (has("angular")) detected.add("Angular");
  if (has("vue")) detected.add("Vue");
  if (has("mongoose", "mongodb", "mongodb")) detected.add("MongoDB");
  if (has("postgresql", "postgres", "psycopg")) detected.add("PostgreSQL");
  if (has("mysql", "pymysql")) detected.add("MySQL");
  if (has("sqlite")) detected.add("SQLite");
  if (has("redis")) detected.add("Redis");
  if (languages.includes("python") || has("fastapi", "django")) detected.add("Python");
  if (languages.includes("java") || has("java/jvm", "spring-boot", "springboot")) detected.add("Java");
  if (languages.includes("go")) detected.add("Go");
  if (languages.some((language) => ["c#", "csharp"].includes(language)) || has("microsoft.net", "aspnetcore")) detected.add(".NET");
  if (languages.includes("php")) detected.add("PHP");
  if (languages.includes("ruby")) detected.add("Ruby");

  return STACK_GROUPS.flatMap((group) => group.choices).filter((technology) => detected.has(technology));
}

function suggestTargets(current: string[]): StackSuggestionGroups {
  const currentKeys = new Set(current.map(normalizeTechnology));
  const candidates: Record<string, Set<string>> = {};

  for (const technology of current) {
    const matches = TARGET_OPTIONS_BY_SOURCE[normalizeTechnology(technology)];
    if (!matches) continue;
    for (const [group, options] of Object.entries(matches)) {
      candidates[group] ??= new Set<string>();
      for (const option of options) {
        if (!currentKeys.has(normalizeTechnology(option))) candidates[group].add(option);
      }
    }
  }

  const suggestions: StackSuggestionGroups = {};
  for (const [group, options] of Object.entries(candidates)) {
    if (options.size > 0) suggestions[group] = Array.from(options);
  }
  return suggestions;
}

export default function Home() {
  const [user, setUser] = useState<UserState | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [workspaceId, setWorkspaceId] = useState("");
  const [authMode, setAuthMode] = useState<"signup" | "login">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspaceName, setWorkspaceName] = useState("Acme Migration");
  const [file, setFile] = useState<File | null>(null);
  const [analysisId, setAnalysisId] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [recent, setRecent] = useState<Recent[]>([]);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [planError, setPlanError] = useState("");
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatConversationId, setChatConversationId] = useState<string | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [currentStack, setCurrentStack] = useState("");
  const [targetStack, setTargetStack] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nextTask = plan?.phases.flatMap((phase) => phase.tasks).find((task) => task.status !== "done");
  const nextTaskLabel = nextTask?.status === "blocked" ? "UNBLOCK THIS STEP" : nextTask?.status === "in_progress" ? "CONTINUE THIS STEP" : "START HERE";

  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await fetch(`${API}${path}`, { ...init, credentials: "include", headers: { ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...init.headers } });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request failed (${response.status})`);
    }
    if (response.status === 204) return null;
    return response.json();
  }, []);

  const loadWorkspace = useCallback(async (id: string) => {
    const [runs] = await Promise.all([request(`/api/workspaces/${id}/analyses`)]);
    setWorkspaceId(id);
    setRecent(runs as Recent[]);
  }, [request]);

  async function switchWorkspace(id: string) {
    setAnalysisId(""); setAnalysis(null); setPlan(null); setPlanError(""); setSimulation(null);
    setChatMessages([]); setChatConversationId(null); setChatError(""); setCurrentStack(""); setTargetStack(""); setError("");
    try { await loadWorkspace(id); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load workspace."); }
  }

  useEffect(() => {
    request("/api/auth/me").then((data) => {
      const account = data as UserState;
      setUser(account);
      if (account.workspaces[0]) void loadWorkspace(account.workspaces[0].id);
    }).catch(() => { }).finally(() => setAuthChecked(true));
  }, [request, loadWorkspace]);

  const refreshAnalysis = useCallback(async (id: string) => {
    const value = await request(`/api/analysis/${id}`) as Analysis;
    setAnalysis(value);
    if (value.result) {
      setCurrentStack((s) => s || value.current_stack?.join(", ") || detectCurrentStack(value.result!).join(", ") || "");
      setTargetStack((s) => s || value.target_stack?.join(", ") || "");
    }
    return value;
  }, [request]);

  useEffect(() => {
    if (!analysisId || !user) return;
    let alive = true;
    const poll = async () => {
      try {
        const value = await request(`/api/analysis/${analysisId}`) as Analysis;
        if (!alive) return;
        setAnalysis(value);
        if (value.result) {
          setCurrentStack((stack) => stack || value.current_stack?.join(", ") || detectCurrentStack(value.result!).join(", ") || "");
          setTargetStack((stack) => stack || value.target_stack?.join(", ") || "");
        }
        if (value.status === "queued" || value.status === "running") setTimeout(poll, 1800);
        else if (workspaceId) void loadWorkspace(workspaceId);
      } catch (e) { if (alive) setError(e instanceof Error ? e.message : "Could not load analysis."); }
    };
    void poll();
    return () => { alive = false; };
  }, [analysisId, user, workspaceId, request, loadWorkspace]);

  useEffect(() => {
    if (!analysisId || !user) return;
    let active = true;
    setChatMessages([]); setChatConversationId(null); setChatError(""); setChatLoading(true);
    request(`/api/analysis/${analysisId}/chat`).then((history) => {
      if (!active) return;
      const value = history as { conversation_id: string | null; messages: ChatMessage[] };
      setChatConversationId(value.conversation_id);
      setChatMessages(value.messages);
    }).catch((e) => {
      if (active) setChatError(e instanceof Error ? e.message : "Could not load conversation history.");
    }).finally(() => { if (active) setChatLoading(false); });
    return () => { active = false; };
  }, [analysisId, user, request]);

  async function authenticate(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const path = authMode === "signup" ? "/api/auth/signup" : "/api/auth/login";
      const account = await request(path, { method: "POST", body: JSON.stringify({ email, password }) }) as { id: string; email: string; workspace?: { id: string; name: string; role: string } };
      let workspaces = account.workspace ? [account.workspace] : [];
      if (!workspaces.length) workspaces = await request("/api/workspaces") as UserState["workspaces"];
      const state: UserState = { id: account.id, email: account.email, workspaces };
      setUser(state);
      if (workspaces[0]) await loadWorkspace(workspaces[0].id);
    } catch (e) { setError(e instanceof Error ? e.message : "Sign-in failed."); }
    finally { setBusy(false); }
  }

  async function createWorkspace(event: FormEvent) {
    event.preventDefault();
    try {
      const workspace = await request("/api/workspaces", { method: "POST", body: JSON.stringify({ name: workspaceName }) }) as { id: string; name: string; role: string };
      setUser((old) => old ? { ...old, workspaces: [...old.workspaces, workspace] } : old);
      await loadWorkspace(workspace.id);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not create workspace."); }
  }

  async function analyze() {
    if (!file || !workspaceId) return;
    setBusy(true); setError(""); setAnalysisId(""); setAnalysis(null); setPlan(null); setPlanError(""); setSimulation(null);
    setChatMessages([]); setChatConversationId(null); setChatError(""); setCurrentStack(""); setTargetStack("");
    const body = new FormData(); body.append("file", file);
    try {
      const created = await request(`/api/workspaces/${workspaceId}/repositories/upload`, { method: "POST", body }) as { analysis_id: string; repository_id: string };
      setAnalysisId(created.analysis_id);
      setAnalysis({ id: created.analysis_id, repository_id: created.repository_id, status: "queued", stage: "queued", repository_name: file.name });
    } catch (e) { setError(e instanceof Error ? e.message : "Upload failed."); }
    finally { setBusy(false); }
  }

  async function openRecent(id: string) {
    setError(""); setPlan(null); setPlanError(""); setSimulation(null); setCurrentStack(""); setTargetStack(""); setAnalysisId(id);
    try { await refreshAnalysis(id); } catch (e) { setError(e instanceof Error ? e.message : "Could not open analysis."); }
  }

  async function generatePlan() {
    if (!analysis) return;
    setBusy(true); setError(""); setPlanError("");
    try {
      const body = { current_stack: currentStack.split(",").map((s) => s.trim()).filter(Boolean), target_stack: targetStack.split(",").map((s) => s.trim()).filter(Boolean) };
      await request(`/api/analysis/${analysis.id}/migration`, { method: "PUT", body: JSON.stringify(body) });
      const created = await request(`/api/analysis/${analysis.id}/plans`, { method: "POST" }) as Plan;
      setPlan(created);
    } catch (e) { setPlanError(e instanceof Error ? e.message : "Could not generate migration plan."); }
    finally { setBusy(false); }
  }

  async function simulate() {
    if (!analysis) return;
    setBusy(true); setError(""); setSimulation(null);
    try {
      const targets = targetStack.split(",").map((s) => s.trim()).filter(Boolean);
      setSimulation(await request(`/api/analysis/${analysis.id}/simulate`, { method: "POST", body: JSON.stringify({ current_stack: currentStack.split(",").map((s) => s.trim()).filter(Boolean), target_stack: targets }) }) as Simulation);
    } catch (e) { setError(e instanceof Error ? e.message : "Simulation failed."); }
    finally { setBusy(false); }
  }

  async function askAssistant(question = chatInput) {
    const message = question.trim();
    if (!analysis || !analysis.result || !message || chatBusy) return;
    setChatBusy(true); setChatError(""); setChatInput("");
    try {
      const response = await request(`/api/analysis/${analysis.id}/chat`, {
        method: "POST",
        body: JSON.stringify({ message, conversation_id: chatConversationId }),
      }) as { conversation_id: string | null; answer: string; claims: ChatClaim[]; model?: string; latency_ms?: number };
      setChatConversationId(response.conversation_id);
      setChatMessages((old) => [
        ...old,
        { role: "user", content: message },
        { role: "assistant", content: response.answer, evidence: response.claims, model: response.model, latency_ms: response.latency_ms },
      ]);
    } catch (e) {
      setChatInput(message);
      setChatError(e instanceof Error ? e.message : "The repository analyst could not answer.");
    } finally { setChatBusy(false); }
  }

  async function changeTask(id: string, status: string) {
    try {
      await request(`/api/tasks/${id}?status=${encodeURIComponent(status)}`, { method: "PATCH" });
      setPlan((old) => old ? { ...old, phases: old.phases.map((p) => ({ ...p, tasks: p.tasks.map((t) => t.id === id ? { ...t, status } : t) })) } : old);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update task."); }
  }

  async function logout() {
    try { await request("/api/auth/logout", { method: "POST" }); } catch { }
    setUser(null); setWorkspaceId(""); setAnalysis(null); setAnalysisId(""); setPlan(null); setSimulation(null);
    setRecent([]); setChatMessages([]); setChatConversationId(null); setChatError("");
  }
  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    if (selected && !selected.name.toLowerCase().endsWith(".zip")) { setError("Choose a ZIP archive to analyze."); setFile(null); return; }
    if (selected && selected.size > 50 * 1024 * 1024) { setError("The ZIP archive must be 50 MB or smaller."); setFile(null); return; }
    setError(""); setFile(selected);
  }

  if (!authChecked) return <main className="authScreen"><div className="brand">M<span>✳</span></div><p>Connecting to your workspace…</p></main>;
  if (!user) return <main className="authScreen"><div className="authCard"><div className="brand">M<span>✳</span></div><span className="eyebrow">EVIDENCE BASED MODERNIZATION</span><h1>{authMode === "signup" ? "Create your account" : "Welcome back"}</h1><p>Plan a safer path from legacy software to what comes next.</p><form onSubmit={authenticate}><label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label><label>Password<input type="password" required minLength={12} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={authMode === "signup" ? "new-password" : "current-password"} /></label><button className="primary" disabled={busy}>{busy ? "Please wait…" : authMode === "signup" ? "Create account" : "Sign in"}<span>→</span></button></form>{error && <div className="error">{error}</div>}<button className="textButton" onClick={() => { setAuthMode(authMode === "signup" ? "login" : "signup"); setError(""); }}>{authMode === "signup" ? "Already have an account? Sign in" : "New to MigrateAI? Create account"}</button><small>Email verification and password recovery are not configured in this build.</small></div></main>;

  return <main className="shell">
    <aside className="rail">
      <a className="brand" href="#overview" aria-label="MigrateAI overview">M<span>✳</span></a>
      <nav className="railNav" aria-label="Workspace sections">
        <a className="railIcon" href="#overview" title="Overview" aria-label="Overview"><House size={18} /></a>
        <a className="railIcon" href="#repository" title="Repository" aria-label="Repository"><FileArchive size={18} /></a>
        <a className="railIcon" href={analysis?.result ? "#assistant" : "#repository"} title="Gemini analyst" aria-label="Gemini analyst"><MessageCircle size={18} /></a>
        <a className="railIcon" href={plan ? "#plan" : "#destination"} title="Migration plan" aria-label="Migration plan"><Workflow size={18} /></a>
      </nav>
      <div className="railFoot" title="Evidence-linked analysis"><Sparkles size={17} /></div>
    </aside>
    <section className="main">
      <header>
        <div><span className="eyebrow">{user.workspaces.find((workspace) => workspace.id === workspaceId)?.name ?? "WORKSPACE"} / OVERVIEW</span><h1>Migration intelligence</h1></div>
        <div className="headerActions">
          {user.workspaces.length > 1 && <label className="workspacePicker"><span>Workspace</span><select value={workspaceId} aria-label="Switch workspace" onChange={(event) => void switchWorkspace(event.target.value)}>{user.workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select></label>}
          <div className="userMenu"><span>{user.email}</span><button className="avatar" onClick={logout} title="Sign out" aria-label="Sign out"><LogOut size={16} /></button></div>
        </div>
      </header>
      <div className="welcome" id="overview">
        <div className="welcomeCopy"><div className="pill"><i /> REPOSITORY MIGRATION WORKSPACE</div><h2>Understand before<br />you modernize.</h2><p>Map your code, inspect evidence, and build a migration plan you can validate.</p></div>
        <aside className="analystPreview">
          <div className="analystPreviewTop"><span><Sparkles size={15} /> GEMINI REPOSITORY ANALYST</span><span className="previewStatus">SERVER-SIDE AI</span></div>
          <div className="analystPreviewBody"><div className="analystGlyph"><Bot size={25} /></div><div><strong>Ask questions about your code</strong><p>Get focused answers with source-file citations from each scan.</p></div></div>
          <div className="previewSignals"><span>Bounded code retrieval</span><span>Evidence-checked answers</span></div>
        </aside>
      </div>
      {!workspaceId && <form className="uploadCard" onSubmit={createWorkspace}><input aria-label="Workspace name" value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} minLength={2} /><button className="primary">Create workspace <span>→</span></button></form>}
      {workspaceId && <><div className="sectionHeading" id="repository"><div><span className="eyebrow">GET STARTED</span><h3>Analyze a repository</h3></div><span className="subtle">ZIP archive · code is never executed · up to 50 MB</span></div>
        <div className="uploadCard"><div className="uploadIcon"><FileArchive size={21} /></div><div className="uploadCopy"><strong>{file?.name ?? "Bring your codebase"}</strong><span>{file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · ZIP archive` : "Upload a ZIP to map architecture, dependencies, and migration signals."}</span></div><label className="choose">Choose ZIP<input type="file" accept=".zip,application/zip" onChange={onFile} /></label><button className="primary" disabled={!file || busy} onClick={analyze}>{busy ? "Uploading…" : "Analyze repository"}<ArrowRight size={16} /></button></div></>}
      {error && <div className="error">{error}</div>}
      {recent.length > 0 && <><div className="sectionHeading" id="history"><div><span className="eyebrow">WORKSPACE HISTORY</span><h3>Recent analyses</h3></div><span className="subtle">{recent.length} {recent.length === 1 ? "repository" : "repositories"}</span></div><div className="recentList">{recent.map((item) => <button key={item.id} className="recentItem" onClick={() => openRecent(item.id)}><span className="recentName">{item.repository_name}</span><span className={`status ${item.status}`}>{item.status.replaceAll("_", " ")} · {item.stage.replaceAll("_", " ")}</span><ArrowRight size={16} /></button>)}</div></>}
      {analysis && <><div className="sectionHeading" id="analysis"><div><span className="eyebrow">ANALYSIS / {analysis.status.toUpperCase()}</span><h3>{analysis.repository_name}</h3></div><span className="subtle">{analysis.stage.replaceAll("_", " ")}</span></div>
        {(analysis.status === "queued" || analysis.status === "running") && <div className="progress"><div className="spinner" /><div><b>{analysis.status === "queued" ? "Repository scan queued" : "Scanning repository"}</b><span>The scan runs automatically. This view will update when evidence is ready.</span></div></div>}
        {analysis.status === "failed" && <div className="error">{analysis.error ?? "Analysis failed."}</div>}
        {analysis.result && <><div className="stats"><Stat label="FILES SCANNED" value={analysis.result.file_count} /><Stat label="LANGUAGES" value={Object.keys(analysis.result.languages).length} /><Stat label="DEPENDENCY EDGES" value={analysis.result.dependencies.length} /><Stat label="STATUS" value={analysis.status} /></div><div className="results"><article><span className="eyebrow">REPOSITORY PROFILE</span><h3>{analysis.result.repository_name}</h3><div className="chips">{Object.entries(analysis.result.languages).map(([name, count]) => <span key={name}>{name} <b>{count}</b></span>)}</div><p>{analysis.result.architecture_hints.join(" · ")}</p><div className="chips">{analysis.result.technologies.slice(0, 18).map((x) => <span key={x}>{x}</span>)}</div>{analysis.result.warnings.map((w, i) => <p className="warning" key={i}>{w}</p>)}</article><article><span className="eyebrow">TRACEABLE SIGNALS</span><h3>{analysis.result.risks.length} things to check</h3>{analysis.result.risks.map((risk) => <div className="risk" key={risk.name}><div><b>{risk.name}</b><span>{risk.detail}</span>{risk.evidence.slice(0, 3).map((ev, i) => <small className="evidence" key={i}>{ev.file}:{ev.start_line} — {ev.detail}</small>)}</div></div>)}<div className="mini">{analysis.result.database_access.length} database references · {analysis.result.api_routes.length} route candidates · {analysis.result.unsupported_file_count} unsupported files</div></article></div>
          <div className="sectionHeading assistantHeading" id="assistant"><div><span className="eyebrow">GEMINI REPOSITORY ANALYST</span><h3>Ask with evidence</h3></div><span className="assistantModel"><Sparkles size={15} /> Grounded in this scan</span></div>
          <section className="assistantPanel" aria-label="Gemini repository analyst">
            <div className="assistantIntro"><span className="assistantAvatar"><Bot size={20} /></span><div><strong>Ask about the codebase</strong><p>Answers are checked against retrieved source and include file-and-line citations. Repository code is treated as data, not instructions.</p></div></div>
            <div className="chatPrompts"><button type="button" disabled={chatBusy} onClick={() => void askAssistant("Where is database access defined?")}>Where is database access defined?</button><button type="button" disabled={chatBusy} onClick={() => void askAssistant("Which modules are most coupled?")}>Which modules are most coupled?</button><button type="button" disabled={chatBusy} onClick={() => void askAssistant("What should I validate before migrating?")}>What should I validate before migrating?</button></div>
            <div className="chatThread" role="log" aria-live="polite" aria-label="Conversation">
              {!chatMessages.length && !chatLoading && <div className="chatEmpty"><MessageCircle size={18} /><span>Ask a question to start. Answers appear here with the source files used.</span></div>}
              {chatLoading && <div className="chatLoading"><LoaderCircle size={16} /> Loading conversation history</div>}
              {chatMessages.map((message, index) => {
                const references = citationsFor(message);
                return <article className={`chatMessage ${message.role}`} key={`${message.role}-${index}`}>
                  <span className="messageRole">{message.role === "assistant" ? <><Bot size={14} /> Gemini analyst</> : "You"}</span>
                  <p>{message.content}</p>
                  {references.length > 0 && <div className="citationList"><span>CITED SOURCE</span>{references.map((citation) => <code key={`${citation.file}:${citation.start_line}-${citation.end_line}`}>{citation.file}:{citation.start_line}{citation.end_line !== citation.start_line ? `-${citation.end_line}` : ""}</code>)}</div>}
                  {message.model && <small className="messageMeta">{message.model}{message.latency_ms ? ` · ${(message.latency_ms / 1000).toFixed(1)}s` : ""}</small>}
                </article>;
              })}
              {chatBusy && <div className="chatLoading"><LoaderCircle size={16} /> Searching repository evidence and composing an answer</div>}
            </div>
            {chatError && <div className="error chatError" role="alert">{chatError}</div>}
            <form className="chatComposer" onSubmit={(event) => { event.preventDefault(); void askAssistant(); }}>
              <textarea value={chatInput} maxLength={4000} rows={2} onChange={(event) => setChatInput(event.target.value)} placeholder="Ask a question about this repository…" aria-label="Question for Gemini analyst" disabled={chatBusy} />
              <button className="primary sendButton" type="submit" disabled={!chatInput.trim() || chatBusy} aria-label="Send question" title="Send question">{chatBusy ? <LoaderCircle size={17} /> : <Send size={17} />}</button>
            </form>
            <div className="assistantFoot"><span>Gemini API · key stays server-side</span><span>{analysis.result.file_count} files scanned</span></div>
          </section>
          <div className="sectionHeading" id="destination"><div><span className="eyebrow">MIGRATION DESIGN</span><h3>Choose your destination</h3></div><span className="subtle">Select technologies to get a clear, ordered list of work</span></div>
          <div className="migrationForm">
            <div className="stackFields">
              <StackPicker label="Current stack" value={currentStack} detectedFromZip onChange={(value) => { setCurrentStack(value); setSimulation(null); setPlan(null); setPlanError(""); }} />
              <StackPicker label="Target stack" value={targetStack} suggestions={suggestTargets(currentStack.split(",").map((technology) => technology.trim()).filter(Boolean))} onChange={(value) => { setTargetStack(value); setSimulation(null); setPlan(null); setPlanError(""); }} />
            </div>
            <div className="migrationActions"><span>Get a first action, clear follow-up steps, and a check for when each step is finished.</span><div><button className="secondary" disabled={busy || !targetStack.trim()} onClick={simulate}>Simulate impact</button><button className="primary" disabled={busy || !targetStack.trim()} onClick={generatePlan}>{busy ? "Writing your steps…" : "Generate step-by-step plan"}<ArrowRight size={16} /></button></div></div>
            {planError && <div className="error planError" role="alert">{planError}</div>}
          </div></>}
        {simulation && <><div className="sectionHeading"><div><span className="eyebrow">WHAT-IF IMPACT</span><h3>Estimated blast radius</h3></div><span className="subtle">{simulation.target_stack.join(", ")}</span></div><p className="basisNote">{simulation.basis}</p><div className="stats"><Stat label="AFFECTED FILES" value={simulation.metrics.affected_files} /><Stat label="AFFECTED MODULES" value={simulation.metrics.affected_modules} /><Stat label="API FILES" value={simulation.metrics.api_files} /><Stat label="DATABASE FILES" value={simulation.metrics.database_files} /></div><div className="results"><article><span className="eyebrow">IMPACTED FILES</span>{simulation.affected_files.length ? simulation.affected_files.map((path) => <small className="evidence" key={path}>{path}</small>) : <p>No API or database files matched the scanned signals.</p>}</article><article><span className="eyebrow">SUPPORTING EVIDENCE</span>{simulation.evidence.slice(0, 20).map((ev, i) => <small className="evidence" key={`${ev.file}:${ev.start_line}:${i}`}>{ev.file}:{ev.start_line} — {ev.detail}</small>)}</article></div></>}
        {plan && <><div className="sectionHeading" id="plan"><div><span className="eyebrow">{plan.generation_source === "evidence" ? "PLAN FROM REPOSITORY SCAN" : "PLAN FROM AI AND REPOSITORY SCAN"}</span><h3>{plan.title}</h3></div><span className="subtle">{plan.current_stack.join(", ")} → {plan.target_stack.join(", ")}</span></div><p className="planReviewNote"><Sparkles size={15} /> {plan.generation_source === "evidence" ? "This plan is based on files found in your repository and general compatibility steps. Start with the action below; file paths are shown when the scan found a match." : "Start with the action below. Each step includes what to do and how to tell when it is finished."}</p>
          <section className="nextStep" aria-label="Your next step"><span className="eyebrow">{nextTask ? nextTaskLabel : "PLAN COMPLETE"}</span>{nextTask ? <><h3>{nextTask.title}</h3><p><b>Do this:</b> {nextTask.next_action}</p><p><b>Done when:</b> {nextTask.done_when}</p>{nextTask.affected_files.length > 0 && <div className="nextStepFiles"><span>Open these files</span>{nextTask.affected_files.map((path) => <code key={path}>{path}</code>)}</div>}</> : <p>All listed steps are marked done.</p>}</section>
          <div className="exportRow"><a className="secondary" href={`${API}/api/plans/${plan.id}/export`}>Export report ↓</a></div><div className="planList">{plan.phases.map((phase, index) => <article className="phase" key={phase.id}><div className="phaseNumber">{String(index + 1).padStart(2, "0")}</div><div className="phaseContent"><div className="phaseTitle"><h3>{phase.title}</h3></div><p>{phase.objective}</p><div className="phaseDetail"><b>Check your work:</b> {phase.validation}<br /><b>If you need to undo it:</b> {phase.rollback}</div>{phase.tasks.map((task) => <div className="task" key={task.id}><select value={task.status} aria-label={`Status: ${task.title}`} onChange={(event) => changeTask(task.id, event.target.value)}><option value="todo">To do</option><option value="in_progress">In progress</option><option value="done">Done</option><option value="blocked">Blocked</option></select><div><b>{task.title}</b><span><strong>Do this:</strong> {task.next_action}</span><span><strong>Why:</strong> {task.description}</span><span><strong>Done when:</strong> {task.done_when}</span>{task.affected_files.map((path) => <small className="evidence" key={path}>{path}</small>)}</div></div>)}</div></article>)}</div></>}
      </>}
      <footer><span>© 2026 MIGRATEAI</span><span>Evidence over assumptions</span></footer>
    </section>
  </main>;
}
function citationsFor(message: ChatMessage): Citation[] {
  const citations = new Map<string, Citation>();
  for (const claim of message.evidence ?? []) {
    for (const citation of claim.evidence) {
      citations.set(`${citation.file}:${citation.start_line}-${citation.end_line}`, citation);
    }
  }
  return Array.from(citations.values());
}

function Stat({ label, value }: { label: string; value: string | number }) { return <div className="stat"><span>{label}</span><strong>{value}</strong></div>; }

function StackPicker({ label, value, onChange, suggestions = {}, detectedFromZip = false }: { label: string; value: string; onChange: (value: string) => void; suggestions?: StackSuggestionGroups; detectedFromZip?: boolean }) {
  const [custom, setCustom] = useState("");
  const selected = value.split(",").map((technology) => technology.trim()).filter(Boolean);
  const contains = (technology: string) => selected.some((item) => normalizeTechnology(item) === normalizeTechnology(technology));
  const suggestedOptions = new Set(Object.values(suggestions).flat());
  const suggestionGroups = STACK_GROUPS
    .map((group) => ({ label: group.label, choices: suggestions[group.label] ?? [] }))
    .filter((group) => group.choices.length > 0);

  function toggle(technology: string) {
    const next = contains(technology)
      ? selected.filter((item) => normalizeTechnology(item) !== normalizeTechnology(technology))
      : [...selected, technology];
    onChange(next.join(", "));
  }

  function addCustom() {
    const technology = custom.trim();
    if (!technology || contains(technology)) return;
    onChange([...selected, technology].join(", "));
    setCustom("");
  }

  return <fieldset className="stackPicker">
    <legend>{label}</legend>
    <span className="stackHint">{detectedFromZip ? "Detected from the uploaded ZIP. Review or adjust the technologies." : "Suggestions are grouped by technology type. Choose the pieces you want in the destination."}</span>
    {suggestionGroups.length > 0 && <div className="stackSuggestions"><span>SUGGESTED FROM YOUR CURRENT STACK</span><p>These are starting points, not automatic compatibility checks. Choose the runtime, framework, data store, and platform that fit your project.</p>{suggestionGroups.map((group) => <div className="suggestionGroup" key={group.label}><b>{group.label}</b><div>{group.choices.map((technology) => <button type="button" className={`suggestionChip${contains(technology) ? " selected" : ""}`} key={technology} aria-pressed={contains(technology)} onClick={() => toggle(technology)}>{contains(technology) ? <Check size={12} /> : <Plus size={12} />}{technology}</button>)}</div></div>)}</div>}
    {label === "Target stack" && suggestionGroups.length === 0 && <div className="suggestionEmpty">Select a current technology above to see category suggestions. You can still choose any target below.</div>}
    <div className="stackOptions">{STACK_GROUPS.map((group) => <div className="stackGroup" key={group.label}><span>{group.label}</span><div>{group.choices.map((technology) => { const suggested = suggestedOptions.has(technology); return <button className={`stackOption${contains(technology) ? " selected" : ""}${suggested ? " suggested" : ""}`} type="button" key={technology} title={suggested ? `Suggested ${group.label.toLowerCase()} option` : undefined} aria-pressed={contains(technology)} onClick={() => toggle(technology)}>{technology}{suggested && <Sparkles size={12} />}{contains(technology) && <Check size={13} />}</button>; })}</div></div>)}</div>
    <div className="customStackRow"><input value={custom} onChange={(event) => setCustom(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addCustom(); } }} placeholder="Add another technology" aria-label={`Add to ${label}`} /><button type="button" className="addStackButton" disabled={!custom.trim()} onClick={addCustom}><Plus size={14} /> Add</button></div>
    <div className="selectedStack"><span>Selected</span>{selected.length ? selected.map((technology) => <button type="button" className="selectedTechnology" key={technology} onClick={() => toggle(technology)} aria-label={`Remove ${technology} from ${label}`}>{technology}<X size={12} /></button>) : <em>No technologies selected</em>}</div>
  </fieldset>;
}
