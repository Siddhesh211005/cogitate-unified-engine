"use strict";

const path = require("path");
const express = require("express");
const multer = require("multer");
const { createProxyMiddleware } = require("http-proxy-middleware");
const adapters = require("./adapters");

// ── Config ────────────────────────────────────────────────────────────────────

const app = express();
const PORT = Number(process.env.PORT || 4000);
const PUBLIC_DIR = path.join(__dirname, "public");

const ENGINE_COOKIE = "cogitate_engine";
const ENGINE_VALUES = new Set(["schema", "excel"]);

const BACKEND_TARGETS = {
  schema: process.env.SCHEMA_BACKEND_TARGET || "http://127.0.0.1:5002",
  excel: process.env.EXCEL_BACKEND_TARGET || "http://127.0.0.1:5001",
};

const FRONTEND_TARGET =
  process.env.FRONTEND_TARGET || "http://127.0.0.1:3000";

// ── Middleware ─────────────────────────────────────────────────────────────────

app.use(express.json());
app.use(express.urlencoded({ extended: false }));

const upload = multer({ storage: multer.memoryStorage() });

// ── Cookie helpers ────────────────────────────────────────────────────────────

function parseCookies(req) {
  const raw = req.headers.cookie || "";
  if (!raw) return {};
  return raw.split(";").reduce((acc, chunk) => {
    const [k, ...rest] = chunk.trim().split("=");
    if (k) acc[k] = decodeURIComponent(rest.join("="));
    return acc;
  }, {});
}

function getSelectedEngine(req) {
  const cookies = parseCookies(req);
  const engine = (cookies[ENGINE_COOKIE] || "").toLowerCase();
  return ENGINE_VALUES.has(engine) ? engine : null;
}

function buildEngineCookie(engine) {
  return `${ENGINE_COOKIE}=${engine}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800`;
}

function clearEngineCookie() {
  return `${ENGINE_COOKIE}=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax; Max-Age=0`;
}

// ── Backend fetch helper ──────────────────────────────────────────────────────

async function backendFetch(engine, urlPath, options = {}) {
  const url = `${BACKEND_TARGETS[engine]}${urlPath}`;
  return fetch(url, options);
}

async function backendJson(engine, urlPath, options = {}) {
  const res = await backendFetch(engine, urlPath, options);
  const body = await res.json().catch(() => ({ detail: res.statusText }));
  return { status: res.status, ok: res.ok, body };
}

// ── Guard: require engine cookie ──────────────────────────────────────────────

function requireEngine(req, res, next) {
  const engine = getSelectedEngine(req);
  if (!engine) {
    return res.status(428).json({
      error: "No engine selected. Please choose an engine first.",
      selectAt: "/",
    });
  }
  req.engine = engine;
  next();
}

// ── Frontend proxy (HMR + all non-api routes) ─────────────────────────────────

const frontendProxy = createProxyMiddleware({
  target: FRONTEND_TARGET,
  changeOrigin: true,
  ws: true,
  logLevel: "silent",
});

// ── Static (engine-selector fallback page) ────────────────────────────────────

app.use("/gateway-static", express.static(PUBLIC_DIR, { index: false }));

// ── Gateway management routes ─────────────────────────────────────────────────

app.get("/gateway/current", (req, res) => {
  res.json({ selected: getSelectedEngine(req) });
});

app.post("/gateway/select/:engine", (req, res) => {
  const engine = (req.params.engine || "").toLowerCase();
  if (!ENGINE_VALUES.has(engine)) {
    return res.status(400).json({
      error: "Invalid engine",
      accepted: Array.from(ENGINE_VALUES),
    });
  }
  res.setHeader("Set-Cookie", buildEngineCookie(engine));
  res.json({ ok: true, selected: engine });
});

app.post("/gateway/reset", (_req, res) => {
  res.setHeader("Set-Cookie", clearEngineCookie());
  res.json({ ok: true });
});

app.get("/gateway/home", (req, res) => {
  res.setHeader("Set-Cookie", clearEngineCookie());
  res.redirect("/");
});

// ── Normalized API routes ─────────────────────────────────────────────────────

// Health check
app.get("/api/health", requireEngine, async (req, res) => {
  try {
    const { status, body } = await backendJson(req.engine, "/api/health");
    res.status(status).json({ ...body, engine: req.engine });
  } catch (e) {
    res.status(502).json({ error: "Backend unreachable", detail: e.message });
  }
});

// List raters
app.get("/api/raters", requireEngine, async (req, res) => {
  try {
    const { status, ok, body } = await backendJson(req.engine, "/api/raters");
    if (!ok) return res.status(status).json(body);
    res.json(adapters.normalizeRaterList(body, req.engine, "raters"));
  } catch (e) {
    res.status(502).json({ error: "Backend unreachable", detail: e.message });
  }
});

// List templates (excel only; schema returns empty array)
app.get("/api/templates", requireEngine, async (req, res) => {
  try {
    if (adapters.isSchema(req.engine)) return res.json([]);
    const { status, ok, body } = await backendJson(req.engine, "/api/templates");
    if (!ok) return res.status(status).json(body);
    res.json(adapters.normalizeRaterList(body, req.engine, "templates"));
  } catch (e) {
    res.status(502).json({ error: "Backend unreachable", detail: e.message });
  }
});

// Upload rater file (normalized: single endpoint, returns type:"complete"|"pending")
app.post("/api/upload", requireEngine, upload.single("file"), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: "No file provided" });
    const form = new FormData();
    form.append(
      "file",
      new Blob([req.file.buffer], { type: req.file.mimetype }),
      req.file.originalname
    );
    const urlPath = adapters.getUploadPath(req.engine);
    const backendRes = await backendFetch(req.engine, urlPath, {
      method: "POST",
      body: form,
    });
    const raw = await backendRes.json();
    if (!backendRes.ok) return res.status(backendRes.status).json(raw);
    res.json(adapters.normalizeUploadResponse(raw, req.engine));
  } catch (e) {
    res.status(502).json({ error: "Upload failed", detail: e.message });
  }
});

// Get rater config / schema  (?source=raters|templates)
app.get("/api/raters/:id/config", requireEngine, async (req, res) => {
  try {
    const source = req.query.source || "raters";
    const urlPath = adapters.getConfigPath(req.params.id, req.engine, source);
    const { status, ok, body } = await backendJson(req.engine, urlPath);
    if (!ok) return res.status(status).json(body);
    res.json(adapters.normalizeSchema(body, req.engine, req.params.id));
  } catch (e) {
    res.status(502).json({ error: "Backend unreachable", detail: e.message });
  }
});

// Calculate  { modelId, inputs, source? }
app.post("/api/calculate", requireEngine, async (req, res) => {
  try {
    const { url: urlPath, body: backendBody } = adapters.buildCalculateRequest(
      req.body,
      req.engine
    );
    const { status, ok, body } = await backendJson(req.engine, urlPath, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(backendBody),
    });
    if (!ok) return res.status(status).json(body);
    res.json(adapters.normalizeResult(body, req.engine));
  } catch (e) {
    res.status(502).json({ error: "Calculation failed", detail: e.message });
  }
});

// Delete rater
app.delete("/api/raters/:id", requireEngine, async (req, res) => {
  try {
    const urlPath = adapters.getDeletePath(req.params.id, req.engine);
    const backendRes = await backendFetch(req.engine, urlPath, {
      method: "DELETE",
    });
    if (backendRes.status === 204) return res.json({ deleted: true });
    const body = await backendRes.json().catch(() => ({}));
    res
      .status(backendRes.ok ? 200 : backendRes.status)
      .json(backendRes.ok ? { deleted: true } : body);
  } catch (e) {
    res.status(502).json({ error: "Delete failed", detail: e.message });
  }
});

// ── Excel-specific two-step upload routes ─────────────────────────────────────

// Step 1 already handled by POST /api/upload above.
// Step 2: save after admin config review
app.post("/api/admin/save", requireEngine, async (req, res) => {
  try {
    const { status, ok, body } = await backendJson(
      req.engine,
      "/api/admin/save",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req.body),
      }
    );
    res.status(status).json(body);
  } catch (e) {
    res.status(502).json({ error: "Save failed", detail: e.message });
  }
});

// Test-calculate during admin review (excel)
app.post("/api/admin/test-calculate", requireEngine, async (req, res) => {
  try {
    const { status, ok, body } = await backendJson(
      req.engine,
      "/api/admin/test-calculate",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req.body),
      }
    );
    if (!ok) return res.status(status).json(body);
    res.json(adapters.normalizeResult(body, req.engine));
  } catch (e) {
    res.status(502).json({ error: "Test-calculate failed", detail: e.message });
  }
});

// ── Fallback: proxy everything else to frontend (HMR, assets, pages) ──────────

app.use("/", frontendProxy);

// ── Server ────────────────────────────────────────────────────────────────────

const server = app.listen(PORT, () => {
  console.log(`[gateway] Running on http://localhost:${PORT}`);
  console.log(`[gateway] Frontend  : ${FRONTEND_TARGET}`);
  console.log(`[gateway] Schema API: ${BACKEND_TARGETS.schema}`);
  console.log(`[gateway] Excel API : ${BACKEND_TARGETS.excel}`);
});

server.on("error", (err) => {
  if (err && err.code === "EADDRINUSE") {
    console.error(
      `[gateway] Port ${PORT} is already in use. Stop the existing dev stack and run npm run dev again.`
    );
    process.exit(1);
  }
  console.error("[gateway] Unexpected server error:", err);
  process.exit(1);
});

server.on("upgrade", (req, socket, head) => {
  // WebSocket pass-through for Vite HMR
  frontendProxy.upgrade(req, socket, head);
});
