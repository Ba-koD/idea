import express from "express";
import os from "node:os";
import pg from "pg";

const { Pool } = pg;

const app = express();
const port = Number.parseInt(process.env.PORT || "8080", 10);
const appEnv = process.env.APP_ENV || "dev";

function buildConnectionConfig() {
  if (process.env.DATABASE_URL) {
    return {
      connectionString: process.env.DATABASE_URL
    };
  }

  return {
    host: process.env.DATABASE_HOST || "db",
    port: Number.parseInt(process.env.DATABASE_PORT || "5432", 10),
    database: process.env.DATABASE_NAME || "idea",
    user: process.env.DATABASE_USER || "idea",
    password: process.env.DATABASE_PASSWORD || "change-me"
  };
}

const pool = new Pool(buildConnectionConfig());

async function readDatabaseTime() {
  const result = await pool.query(
    "select now() as database_time, current_database() as database_name"
  );
  return result.rows[0];
}

function buildPayload(databaseRow) {
  const now = new Date().toISOString();
  return {
    status: "ok",
    service: "idea-backend",
    environment: appEnv,
    appTime: now,
    databaseTime: databaseRow.database_time,
    databaseName: databaseRow.database_name,
    hostname: os.hostname()
  };
}

app.get("/api/healthz", async (_req, res) => {
  try {
    const databaseRow = await readDatabaseTime();
    res.json(buildPayload(databaseRow));
  } catch (error) {
    res.status(503).json({
      status: "error",
      service: "idea-backend",
      environment: appEnv,
      error: error instanceof Error ? error.message : "unknown error",
      hostname: os.hostname()
    });
  }
});

app.get("/api/readyz", async (_req, res) => {
  try {
    await pool.query("select 1");
    res.json({
      status: "ready",
      service: "idea-backend",
      environment: appEnv,
      hostname: os.hostname()
    });
  } catch (error) {
    res.status(503).json({
      status: "not-ready",
      service: "idea-backend",
      environment: appEnv,
      error: error instanceof Error ? error.message : "unknown error",
      hostname: os.hostname()
    });
  }
});

app.get("/api/time", async (_req, res) => {
  try {
    const databaseRow = await readDatabaseTime();
    res.json(buildPayload(databaseRow));
  } catch (error) {
    res.status(500).json({
      status: "error",
      service: "idea-backend",
      environment: appEnv,
      error: error instanceof Error ? error.message : "unknown error",
      hostname: os.hostname()
    });
  }
});

app.get("/", (_req, res) => {
  res.json({
    status: "ok",
    service: "idea-backend",
    environment: appEnv,
    message: "Use /api/time or /api/healthz."
  });
});

const server = app.listen(port, () => {
  console.log(`idea-backend listening on :${port}`);
});

async function shutdown(signal) {
  console.log(`received ${signal}, shutting down`);
  server.close(async () => {
    await pool.end().catch(() => {});
    process.exit(0);
  });
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    void shutdown(signal);
  });
}
