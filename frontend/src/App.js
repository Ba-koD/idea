import React, { useEffect, useRef, useState } from 'react';
import './App.css';
import MermaidViewer from './components/MermaidViewer';

const ENVIRONMENTS = ['dev', 'stage', 'prod'];
const STORAGE_KEY = 'idea-project-state-v2';
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || '/api';

function buildApiUrl(path) {
  const base = API_BASE_URL.replace(/\/$/, '');
  return `${base}${path}`;
}

function deepMerge(base, override) {
  if (Array.isArray(base)) {
    return Array.isArray(override) ? [...override] : [...base];
  }

  if (base && typeof base === 'object' && override && typeof override === 'object') {
    const merged = { ...base };
    Object.entries(override).forEach(([key, value]) => {
      if (key in merged) {
        merged[key] = deepMerge(merged[key], value);
      } else if (Array.isArray(value)) {
        merged[key] = [...value];
      } else if (value && typeof value === 'object') {
        merged[key] = deepMerge({}, value);
      } else {
        merged[key] = value;
      }
    });
    return merged;
  }

  return override === undefined || override === null ? base : override;
}

function buildHostname(subdomain, baseDomain) {
  const normalizedBase = (baseDomain || '').trim().toLowerCase();
  const normalizedSubdomain = (subdomain || '').trim().toLowerCase();

  if (!normalizedBase) {
    return '';
  }

  if (!normalizedSubdomain || normalizedSubdomain === '@' || normalizedSubdomain === '*') {
    return normalizedBase;
  }

  return `${normalizedSubdomain}.${normalizedBase}`;
}

function parseKeyValueBlock(text) {
  return (text || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#') && line.includes('='))
    .reduce((acc, line) => {
      const separatorIndex = line.indexOf('=');
      const key = line.slice(0, separatorIndex).trim();
      const value = line.slice(separatorIndex + 1).trim();

      if (key) {
        acc[key] = value;
      }
      return acc;
    }, {});
}

function formatKeyValueBlock(values) {
  return Object.entries(values || {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join('\n');
}

function parseLines(text) {
  return (text || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function formatLines(values) {
  return (values || []).join('\n');
}

function defaultProjectState() {
  return {
    project: {
      name: 'repo-example',
      app_repo_url: 'https://github.com/Ba-koD/repo_example',
      git_ref: 'main',
      repo_access_secret_ref: 'github-repo-example-token'
    },
    build: {
      source_strategy: 'platform_build_runner',
      frontend_context: 'frontend',
      frontend_dockerfile_path: 'frontend/Dockerfile',
      backend_context: 'backend',
      backend_dockerfile_path: 'backend/Dockerfile'
    },
    argo: {
      project_name: 'default',
      destination_name: 'ncloud-nks-dev',
      destination_server: 'https://kubernetes.default.svc',
      gitops_repo_url: 'https://github.com/Ba-koD/idea.git',
      gitops_repo_branch: 'main',
      gitops_repo_path: 'gitops/generated/repo-example',
      gitops_repo_access_secret_ref: 'gitops-repo-token',
      access_hint: 'ssh MacMini && kubectl -n argocd port-forward svc/argocd-server 8081:80'
    },
    cloudflare: {
      enabled: true,
      account_id: '2052eb94f7b555bd3bf9db83c1f4edbf',
      zone_id: 'aaafd11f9c6912ba37c1d52a69b78398',
      api_token_secret_ref: 'cloudflare-api-token',
      tunnel_name: 'repo-example-platform',
      route_mode: 'platform_caddy',
      environments: {
        dev: { subdomain: 'repo-example-dev', base_domain: 'rnen.kr' },
        stage: { subdomain: 'repo-example-stage', base_domain: 'rnen.kr' },
        prod: { subdomain: 'repo-example', base_domain: 'rnen.kr' }
      }
    },
    targets: {
      dev: {
        provider: 'ncloud',
        cluster_type: 'nks',
        namespace: 'repo-example-dev',
        service_port: 80,
        ncloud: {
          region_code: 'KR',
          cluster_name: 'idea-dev',
          cluster_version: '1.30',
          auth_method: 'access_key',
          access_key_secret_ref: 'ncloud-dev-access-key',
          secret_key_secret_ref: 'ncloud-dev-secret-key',
          zone_code: 'KR-2',
          vpc_no: 'vpc-dev',
          subnet_no: 'subnet-dev',
          lb_subnet_no: 'lb-subnet-dev',
          node_pool_name: 'repo-example-dev-pool',
          node_count: 2,
          node_product_code: 'SVR.VSVR.STAND.C002.M004.NET.SSD.B050.G002',
          block_storage_size_gb: 50,
          autoscale_enabled: true,
          autoscale_min_node_count: 2,
          autoscale_max_node_count: 4
        }
      },
      stage: {
        provider: 'ncloud',
        cluster_type: 'nks',
        namespace: 'repo-example-stage',
        service_port: 80,
        ncloud: {
          region_code: 'KR',
          cluster_name: 'idea-stage',
          cluster_version: '1.30',
          auth_method: 'access_key',
          access_key_secret_ref: 'ncloud-stage-access-key',
          secret_key_secret_ref: 'ncloud-stage-secret-key',
          zone_code: 'KR-2',
          vpc_no: 'vpc-stage',
          subnet_no: 'subnet-stage',
          lb_subnet_no: 'lb-subnet-stage',
          node_pool_name: 'repo-example-stage-pool',
          node_count: 2,
          node_product_code: 'SVR.VSVR.STAND.C002.M004.NET.SSD.B050.G002',
          block_storage_size_gb: 50,
          autoscale_enabled: true,
          autoscale_min_node_count: 2,
          autoscale_max_node_count: 4
        }
      },
      prod: {
        provider: 'ncloud',
        cluster_type: 'nks',
        namespace: 'repo-example-prod',
        service_port: 80,
        ncloud: {
          region_code: 'KR',
          cluster_name: 'idea-prod',
          cluster_version: '1.30',
          auth_method: 'access_key',
          access_key_secret_ref: 'ncloud-prod-access-key',
          secret_key_secret_ref: 'ncloud-prod-secret-key',
          zone_code: 'KR-2',
          vpc_no: 'vpc-prod',
          subnet_no: 'subnet-prod',
          lb_subnet_no: 'lb-subnet-prod',
          node_pool_name: 'repo-example-prod-pool',
          node_count: 3,
          node_product_code: 'SVR.VSVR.STAND.C004.M008.NET.SSD.B100.G002',
          block_storage_size_gb: 100,
          autoscale_enabled: true,
          autoscale_min_node_count: 3,
          autoscale_max_node_count: 6
        }
      }
    },
    routing: {
      entry_service_name: 'frontend',
      backend_service_name: 'backend',
      backend_base_path: '/api',
      dev_hostname: 'repo-example-dev.rnen.kr',
      stage_hostname: 'repo-example-stage.rnen.kr',
      prod_hostname: 'repo-example.rnen.kr'
    },
    env: {
      dev: {
        APP_ENV: 'dev',
        APP_DISPLAY_NAME: 'Repo Example Dev',
        PUBLIC_API_BASE_URL: '/api'
      },
      stage: {
        APP_ENV: 'stage',
        APP_DISPLAY_NAME: 'Repo Example Stage',
        PUBLIC_API_BASE_URL: '/api'
      },
      prod: {
        APP_ENV: 'prod',
        APP_DISPLAY_NAME: 'Repo Example Prod',
        PUBLIC_API_BASE_URL: '/api',
        NODE_ENV: 'production'
      }
    },
    secrets: {
      dev: {
        EXAMPLE_API_TOKEN: 'secret://repo-example/dev/example-api-token'
      },
      stage: {
        EXAMPLE_API_TOKEN: 'secret://repo-example/stage/example-api-token'
      },
      prod: {
        EXAMPLE_API_TOKEN: 'secret://repo-example/prod/example-api-token'
      }
    },
    access: {
      admin_allowed_source_ips: ['58.123.221.76/32'],
      dev_allowed_source_ips: ['58.123.221.76/32'],
      stage_allowed_source_ips: ['58.123.221.76/32'],
      prod_allowed_source_ips: []
    },
    delivery: {
      prod_blue_green_enabled: true,
      healthcheck_path: '/api/healthz',
      healthcheck_timeout_seconds: 30,
      rollback_on_failure: true
    }
  };
}

function normalizeProjectState(rawState) {
  const merged = deepMerge(defaultProjectState(), rawState || {});
  const legacyBaseDomain = merged.cloudflare.base_domain || '';
  const legacyPrefix = merged.cloudflare.public_subdomain_prefix || '';

  ENVIRONMENTS.forEach((envName) => {
    const envCloudflare = merged.cloudflare.environments[envName] || {};
    const defaultEnvCloudflare = defaultProjectState().cloudflare.environments[envName];

    if (!envCloudflare.base_domain) {
      envCloudflare.base_domain = legacyBaseDomain || defaultEnvCloudflare.base_domain;
    }

    if (!envCloudflare.subdomain) {
      if (legacyPrefix) {
        const suffix = envName === 'prod' ? '' : `-${envName}`;
        envCloudflare.subdomain = `${legacyPrefix}${suffix}`;
      } else {
        envCloudflare.subdomain = defaultEnvCloudflare.subdomain;
      }
    }

    merged.cloudflare.environments[envName] = envCloudflare;
    merged.routing[`${envName}_hostname`] = buildHostname(envCloudflare.subdomain, envCloudflare.base_domain);

    merged.env[envName] = deepMerge(defaultProjectState().env[envName], merged.env[envName] || {});
    merged.secrets[envName] = deepMerge(defaultProjectState().secrets[envName], merged.secrets[envName] || {});
    merged.targets[envName] = deepMerge(defaultProjectState().targets[envName], merged.targets[envName] || {});
    merged.access[`${envName}_allowed_source_ips`] = merged.access[`${envName}_allowed_source_ips`] || [];
  });

  merged.delivery.healthcheck_path =
    merged.delivery.healthcheck_path || `${merged.routing.backend_base_path.replace(/\/$/, '')}/healthz`;

  return merged;
}

function readStoredState() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? normalizeProjectState(JSON.parse(raw)) : null;
  } catch (error) {
    return null;
  }
}

function App() {
  const [activeEnv, setActiveEnv] = useState('dev');
  const [projectState, setProjectState] = useState(defaultProjectState);
  const [logs, setLogs] = useState([]);
  const [downloadUrl, setDownloadUrl] = useState('');
  const [stateSource, setStateSource] = useState('loading');
  const [isReady, setIsReady] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeploying, setIsDeploying] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const logEndRef = useRef(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    let cancelled = false;

    async function loadProjectState() {
      try {
        const response = await fetch(buildApiUrl('/project-state'), { cache: 'no-store' });
        if (!response.ok) {
          throw new Error(`project-state returned ${response.status}`);
        }

        const payload = normalizeProjectState(await response.json());
        if (cancelled) {
          return;
        }

        setProjectState(payload);
        setLogs([`Loaded project state from backend for ${payload.project.name}.`]);
        setStateSource('backend');
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      } catch (error) {
        const stored = readStoredState();
        if (cancelled) {
          return;
        }

        if (stored) {
          setProjectState(stored);
          setLogs(['Backend state unavailable. Loaded the last browser snapshot.']);
          setStateSource('browser');
        } else {
          const fallback = normalizeProjectState({});
          setProjectState(fallback);
          setLogs(['No saved state found yet. Loaded repo_example defaults.']);
          setStateSource('default');
        }
      } finally {
        if (!cancelled) {
          setIsReady(true);
        }
      }
    }

    loadProjectState();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isReady) {
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(projectState));
  }, [isReady, projectState]);

  function updateProjectState(mutator) {
    setProjectState((current) => {
      const next = normalizeProjectState(current);
      mutator(next);
      return normalizeProjectState(next);
    });
  }

  async function persistProjectState(nextState = projectState) {
    const normalized = normalizeProjectState(nextState);
    const response = await fetch(buildApiUrl('/project-state'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(normalized)
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `save failed with ${response.status}`);
    }

    const saved = normalizeProjectState(await response.json());
    setProjectState(saved);
    setStateSource('backend');
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
    return saved;
  }

  async function handleSave() {
    setIsSaving(true);
    setStatusMessage('');

    try {
      await persistProjectState();
      setLogs((currentLogs) => [...currentLogs, 'Saved project state to backend.']);
      setStatusMessage('Project State saved.');
    } catch (error) {
      setLogs((currentLogs) => [...currentLogs, `Save failed: ${error.message}`]);
      setStatusMessage(`Save failed: ${error.message}`);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeploy() {
    setIsDeploying(true);
    setStatusMessage('');
    setDownloadUrl('');

    try {
      const saved = await persistProjectState();
      const response = await fetch(buildApiUrl('/deploy'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_env: activeEnv,
          project_state: saved
        })
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `deploy failed with ${response.status}`);
      }

      setLogs(payload.logs || ['Bundle generated.']);
      setDownloadUrl(payload.download_url || '');
      setStatusMessage(payload.message || 'Bundle generated.');
    } catch (error) {
      setLogs([`Deploy failed: ${error.message}`]);
      setStatusMessage(`Deploy failed: ${error.message}`);
    } finally {
      setIsDeploying(false);
    }
  }

  const currentCloudflare = projectState.cloudflare.environments[activeEnv];
  const currentTarget = projectState.targets[activeEnv];
  const currentRuntimeEnv = projectState.env[activeEnv];
  const currentHostname = projectState.routing[`${activeEnv}_hostname`];
  const currentAllowedIps = projectState.access[`${activeEnv}_allowed_source_ips`];
  const currentSecrets = projectState.secrets[activeEnv];
  const prodExampleBlock = [
    'APP_ENV=prod',
    'APP_DISPLAY_NAME=Repo Example Prod',
    'PUBLIC_API_BASE_URL=/api',
    'NODE_ENV=production'
  ].join('\n');

  const diagramCode = `
flowchart LR
  classDef focus fill:#1d4ed8,stroke:#1d4ed8,color:#ffffff
  classDef card fill:#f8fafc,stroke:#cbd5e1,color:#0f172a
  UI["idea.rnen.kr\\nProject State UI"] --> GitOps["GitOps input\\n${projectState.argo.gitops_repo_path}/${activeEnv}"]
  GitOps --> Argo["Argo CD\\n${projectState.argo.project_name}"]
  Argo --> NKS["Ncloud NKS\\n${currentTarget.ncloud.cluster_name}"]
  CF["Cloudflare Tunnel\\n${currentHostname || 'hostname pending'}"] --> Caddy["Platform Caddy\\n${projectState.routing.backend_base_path} => ${projectState.routing.backend_service_name}"]
  NKS --> Caddy
  Caddy --> Frontend["${projectState.routing.entry_service_name}\\nservice :${currentTarget.service_port}"]
  Caddy --> Backend["${projectState.routing.backend_service_name}\\nservice /api"]
  Backend --> DB["db service"]
  class CF,NKS focus
  class UI,GitOps,Argo,Caddy,Frontend,Backend,DB card
`;

  return (
    <div className="app-shell">
      <header className="hero-bar">
        <div>
          <p className="eyebrow">IDEA Control Plane</p>
          <h1>Repo Project State Editor</h1>
        </div>
        <div className="hero-status">
          <span className="pill">{stateSource}</span>
          <span className="status-text">{statusMessage || 'Ready'}</span>
        </div>
      </header>

      <div className="workspace">
        <section className="control-panel">
          <div className="panel-card">
            <div className="section-heading">
              <h2>App Repository</h2>
              <p>All environments inherit this repository and git ref.</p>
            </div>

            <div className="field-grid">
              <label className="field">
                <span>App Repository URL</span>
                <input
                  type="text"
                  value={projectState.project.app_repo_url}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.project.app_repo_url = event.target.value;
                    })
                  }
                />
              </label>

              <label className="field">
                <span>Git Ref</span>
                <input
                  type="text"
                  value={projectState.project.git_ref}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.project.git_ref = event.target.value;
                    })
                  }
                />
              </label>

              <label className="field">
                <span>Project Name</span>
                <input
                  type="text"
                  value={projectState.project.name}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.project.name = event.target.value;
                    })
                  }
                />
              </label>

              <label className="field">
                <span>Repo Access Secret Ref</span>
                <input
                  type="text"
                  value={projectState.project.repo_access_secret_ref}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.project.repo_access_secret_ref = event.target.value;
                    })
                  }
                />
              </label>
            </div>
          </div>

          <div className="panel-card">
            <div className="section-heading">
              <h2>Platform Routing</h2>
              <p>Keep repo internal nginx untouched and route through platform Caddy.</p>
            </div>

            <div className="field-grid">
              <label className="field">
                <span>Entry Service</span>
                <input
                  type="text"
                  value={projectState.routing.entry_service_name}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.routing.entry_service_name = event.target.value;
                    })
                  }
                />
              </label>

              <label className="field">
                <span>Backend Service</span>
                <input
                  type="text"
                  value={projectState.routing.backend_service_name}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.routing.backend_service_name = event.target.value;
                    })
                  }
                />
              </label>

              <label className="field">
                <span>Backend Base Path</span>
                <input
                  type="text"
                  value={projectState.routing.backend_base_path}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.routing.backend_base_path = event.target.value;
                    })
                  }
                />
              </label>

              <label className="field">
                <span>Healthcheck Path</span>
                <input
                  type="text"
                  value={projectState.delivery.healthcheck_path}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.delivery.healthcheck_path = event.target.value;
                    })
                  }
                />
              </label>
            </div>
          </div>

          <div className="env-tabs">
            {ENVIRONMENTS.map((envName) => (
              <button
                key={envName}
                type="button"
                className={activeEnv === envName ? 'active' : ''}
                onClick={() => setActiveEnv(envName)}
              >
                {envName.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="panel-card">
            <div className="section-heading">
              <h2>{activeEnv.toUpperCase()} Environment</h2>
              <p>Cloudflare hostname, runtime env, allowlist, and NKS target.</p>
            </div>

            <div className="subsection">
              <h3>Cloudflare Reconciler</h3>
              <div className="field-grid">
                <label className="field">
                  <span>Account ID</span>
                  <input
                    type="text"
                    value={projectState.cloudflare.account_id}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.cloudflare.account_id = event.target.value;
                      })
                    }
                  />
                </label>

                <label className="field">
                  <span>Zone ID</span>
                  <input
                    type="text"
                    value={projectState.cloudflare.zone_id}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.cloudflare.zone_id = event.target.value;
                      })
                    }
                  />
                </label>

                <label className="field">
                  <span>API Token Secret Ref</span>
                  <input
                    type="text"
                    value={projectState.cloudflare.api_token_secret_ref}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.cloudflare.api_token_secret_ref = event.target.value;
                      })
                    }
                  />
                </label>

                <label className="field">
                  <span>Tunnel Name</span>
                  <input
                    type="text"
                    value={projectState.cloudflare.tunnel_name}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.cloudflare.tunnel_name = event.target.value;
                      })
                    }
                  />
                </label>

                <label className="field">
                  <span>{activeEnv.toUpperCase()} Subdomain</span>
                  <input
                    type="text"
                    value={currentCloudflare.subdomain}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.cloudflare.environments[activeEnv].subdomain = event.target.value;
                      })
                    }
                    placeholder="@, *, repo-example-dev"
                  />
                </label>

                <label className="field">
                  <span>{activeEnv.toUpperCase()} Base Domain</span>
                  <input
                    type="text"
                    value={currentCloudflare.base_domain}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.cloudflare.environments[activeEnv].base_domain = event.target.value;
                      })
                    }
                    placeholder="rnen.kr"
                  />
                </label>
              </div>

              <div className="preview-banner">
                <strong>Hostname Preview</strong>
                <span>{currentHostname || 'base domain required'}</span>
              </div>
            </div>

            <div className="subsection">
              <h3>Runtime</h3>
              <div className="field-grid compact-grid">
                <label className="field">
                  <span>Namespace</span>
                  <input
                    type="text"
                    value={currentTarget.namespace}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.targets[activeEnv].namespace = event.target.value;
                      })
                    }
                  />
                </label>

                <label className="field">
                  <span>NKS Cluster</span>
                  <input
                    type="text"
                    value={currentTarget.ncloud.cluster_name}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.targets[activeEnv].ncloud.cluster_name = event.target.value;
                      })
                    }
                  />
                </label>

                <label className="field">
                  <span>Service Port</span>
                  <input
                    type="number"
                    value={currentTarget.service_port}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.targets[activeEnv].service_port = Number(event.target.value || '80');
                      })
                    }
                  />
                </label>

                <label className="field">
                  <span>Blue Green</span>
                  <select
                    value={projectState.delivery.prod_blue_green_enabled ? 'enabled' : 'disabled'}
                    onChange={(event) =>
                      updateProjectState((next) => {
                        next.delivery.prod_blue_green_enabled = event.target.value === 'enabled';
                      })
                    }
                  >
                    <option value="enabled">enabled</option>
                    <option value="disabled">disabled</option>
                  </select>
                </label>
              </div>

              <label className="field">
                <span>{activeEnv.toUpperCase()} Runtime Env</span>
                <textarea
                  rows="8"
                  value={formatKeyValueBlock(currentRuntimeEnv)}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.env[activeEnv] = parseKeyValueBlock(event.target.value);
                    })
                  }
                />
              </label>

              <label className="field">
                <span>{activeEnv.toUpperCase()} Secret Refs</span>
                <textarea
                  rows="4"
                  value={formatKeyValueBlock(currentSecrets)}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.secrets[activeEnv] = parseKeyValueBlock(event.target.value);
                    })
                  }
                />
              </label>

              <label className="field">
                <span>{activeEnv.toUpperCase()} Allowed Source IPs</span>
                <textarea
                  rows="4"
                  value={formatLines(currentAllowedIps)}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.access[`${activeEnv}_allowed_source_ips`] = parseLines(event.target.value);
                    })
                  }
                />
              </label>

              {activeEnv === 'prod' && (
                <div className="example-block">
                  <p>PROD RUNTIME ENV example</p>
                  <pre>{prodExampleBlock}</pre>
                </div>
              )}
            </div>
          </div>

          <div className="actions-row">
            <button type="button" className="secondary-action" onClick={handleSave} disabled={isSaving || isDeploying}>
              {isSaving ? 'Saving...' : 'Save Project State'}
            </button>
            <button type="button" className="primary-action" onClick={handleDeploy} disabled={isSaving || isDeploying}>
              {isDeploying ? 'Generating...' : `Generate ${activeEnv.toUpperCase()} Bundle`}
            </button>
          </div>

          {downloadUrl && (
            <a className="download-link" href={downloadUrl} download>
              Download generated bundle
            </a>
          )}
        </section>

        <section className="inspector-panel">
          <div className="summary-grid">
            <article className="summary-card">
              <span className="summary-label">Selected Env</span>
              <strong>{activeEnv.toUpperCase()}</strong>
              <p>{currentHostname || 'Hostname pending'}</p>
            </article>

            <article className="summary-card">
              <span className="summary-label">Repository</span>
              <strong>{projectState.project.git_ref}</strong>
              <p>{projectState.project.app_repo_url}</p>
            </article>

            <article className="summary-card">
              <span className="summary-label">Argo CD Access</span>
              <strong>{projectState.argo.project_name}</strong>
              <p>{projectState.argo.access_hint}</p>
            </article>

            <article className="summary-card">
              <span className="summary-label">NKS Namespace</span>
              <strong>{currentTarget.namespace}</strong>
              <p>{currentTarget.ncloud.cluster_name}</p>
            </article>
          </div>

          <div className="panel-card diagram-card">
            <div className="section-heading">
              <h2>Delivery Topology</h2>
              <p>Cloudflare Tunnel, Caddy, Argo CD, and NKS for the selected environment.</p>
            </div>
            <div className="diagram-surface">
              <MermaidViewer chartCode={diagramCode} />
            </div>
          </div>

          <div className="panel-card">
            <div className="section-heading">
              <h2>Argo CD</h2>
              <p>Current access path until a public route is added.</p>
            </div>
            <pre className="inline-command">{projectState.argo.access_hint}</pre>
          </div>

          <div className="panel-card">
            <div className="section-heading">
              <h2>Console</h2>
              <p>Backend load, save, and bundle generation logs.</p>
            </div>

            <div className="console-panel">
              {logs.map((log, index) => (
                <div key={`${log}-${index}`} className="console-line">
                  <span className="console-prefix">&gt;&gt;</span>
                  <span>{log}</span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default App;
