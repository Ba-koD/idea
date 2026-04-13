const config = window.__APP_CONFIG__ || {};

const fields = {
  displayName: document.getElementById("display-name"),
  environment: document.getElementById("environment"),
  apiBaseUrl: document.getElementById("api-base-url"),
  hostname: document.getElementById("hostname"),
  appTime: document.getElementById("app-time"),
  dbTime: document.getElementById("db-time"),
  dbName: document.getElementById("db-name"),
  status: document.getElementById("status")
};

function buildApiUrl(path) {
  const base = (config.PUBLIC_API_BASE_URL || "/api").replace(/\/$/, "");
  return `${base}${path}`;
}

async function loadTime() {
  fields.displayName.textContent = config.APP_DISPLAY_NAME || "idea Service Demo";
  fields.environment.textContent = config.APP_ENV || "unknown";
  fields.apiBaseUrl.textContent = config.PUBLIC_API_BASE_URL || "/api";
  fields.status.textContent = "loading";

  try {
    const response = await fetch(buildApiUrl("/time"), {
      headers: {
        Accept: "application/json"
      }
    });

    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }

    const payload = await response.json();
    fields.environment.textContent = payload.environment || config.APP_ENV || "unknown";
    fields.hostname.textContent = payload.hostname;
    fields.appTime.textContent = payload.appTime;
    fields.dbTime.textContent = payload.databaseTime;
    fields.dbName.textContent = payload.databaseName;
    fields.status.textContent = payload.status;
  } catch (error) {
    fields.status.textContent = error instanceof Error ? error.message : "request failed";
  }
}

document.getElementById("refresh").addEventListener("click", () => {
  void loadTime();
});

void loadTime();
window.setInterval(() => {
  void loadTime();
}, 5000);
