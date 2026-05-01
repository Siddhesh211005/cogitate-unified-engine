const path = require("path");
const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");

const app = express();
const PORT = Number(process.env.PORT || 8080);
const PUBLIC_DIR = path.join(__dirname, "public");

const ENGINE_COOKIE = "cogitate_engine";
const ENGINE_VALUES = new Set(["schema", "excel"]);

const FRONTEND_TARGETS = {
  schema: process.env.SCHEMA_FRONTEND_TARGET || "http://127.0.0.1:3000",
  excel: process.env.EXCEL_FRONTEND_TARGET || "http://127.0.0.1:3000",
};

const BACKEND_TARGETS = {
  schema: process.env.SCHEMA_BACKEND_TARGET || "http://127.0.0.1:8000",
  excel: process.env.EXCEL_BACKEND_TARGET || "http://127.0.0.1:8001",
};

function parseCookies(req) {
  const raw = req.headers.cookie || "";
  if (!raw) {
    return {};
  }

  return raw.split(";").reduce((acc, chunk) => {
    const [k, ...rest] = chunk.trim().split("=");
    if (!k) {
      return acc;
    }
    acc[k] = decodeURIComponent(rest.join("="));
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

app.use("/gateway-static", express.static(PUBLIC_DIR, { index: false }));

app.get("/gateway/current", (req, res) => {
  return res.json({ selected: getSelectedEngine(req) });
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
  return res.json({ ok: true, selected: engine, redirectTo: "/" });
});

app.post("/gateway/reset", (_req, res) => {
  res.setHeader("Set-Cookie", clearEngineCookie());
  return res.json({ ok: true, redirectTo: "/" });
});

app.get("/gateway/home", (req, res) => {
  res.setHeader("Set-Cookie", clearEngineCookie());
  return res.redirect("/");
});

const apiProxy = createProxyMiddleware({
  target: BACKEND_TARGETS.schema,
  changeOrigin: true,
  xfwd: true,
  ws: true,
  router: (req) => BACKEND_TARGETS[getSelectedEngine(req)] || BACKEND_TARGETS.schema,
  on: {
    proxyReq: (proxyReq, req) => {
      const engine = getSelectedEngine(req);
      if (engine) {
        proxyReq.setHeader("x-cogitate-engine", engine);
      }
    },
  },
  logLevel: "warn",
});

const frontendProxy = createProxyMiddleware({
  target: FRONTEND_TARGETS.schema,
  changeOrigin: true,
  xfwd: true,
  ws: true,
  router: (req) => FRONTEND_TARGETS[getSelectedEngine(req)] || FRONTEND_TARGETS.schema,
  logLevel: "warn",
});

app.use((req, res, next) => {
  if (!req.url || !req.url.startsWith("/api")) {
    return next();
  }
  const engine = getSelectedEngine(req);
  if (!engine) {
    return res.status(428).json({
      error: "Please select a rater from the splash screen first",
      selectAt: "/",
    });
  }
  return apiProxy(req, res, next);
});

app.get("/", (req, res, next) => {
  const engine = getSelectedEngine(req);

  if (!engine) {
    res.setHeader("Cache-Control", "no-store");
    return res.sendFile(path.join(PUBLIC_DIR, "index.html"));
  }

  return frontendProxy(req, res, next);
});

app.use((req, res, next) => {
  const engine = getSelectedEngine(req);

  if (!engine) {
    return res.redirect("/");
  }

  return frontendProxy(req, res, next);
});

const server = app.listen(PORT, () => {
  console.log(`[gateway] Running on http://localhost:${PORT}`);
  console.log(`[gateway] Schema FE: ${FRONTEND_TARGETS.schema}`);
  console.log(`[gateway] Excel FE : ${FRONTEND_TARGETS.excel}`);
  console.log(`[gateway] Schema API: ${BACKEND_TARGETS.schema}`);
  console.log(`[gateway] Excel API : ${BACKEND_TARGETS.excel}`);
});

server.on('error', (err) => {
  if (err && err.code === 'EADDRINUSE') {
    console.error(`[gateway] Port ${PORT} is already in use. Stop the existing dev stack and run npm run dev again.`);
    process.exit(1);
    return;
  }

  console.error('[gateway] Unexpected server error:', err);
  process.exit(1);
});

server.on("upgrade", (req, socket, head) => {
  if (req.url && req.url.startsWith("/api")) {
    apiProxy.upgrade(req, socket, head);
    return;
  }
  frontendProxy.upgrade(req, socket, head);
});
