import React, { useEffect, useRef, useState } from 'react';
import './App.css';
import MermaidViewer from './components/MermaidViewer';

const ENVIRONMENTS = ['dev', 'stage', 'prod'];
const STORAGE_KEY = 'idea-project-state-v2';
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || '/api';
const SUPPORTED_NCLOUD_CLUSTER_VERSIONS = ['1.33.4', '1.34.3', '1.32.8'];
const ENVIRONMENT_META = {
  dev: { color: '#3b82f6', label: 'Development' },
  stage: { color: '#f59e0b', label: 'Staging' },
  prod: { color: '#10b981', label: 'Production' }
};

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

function pruneLegacyExampleSecrets(secretMap, envName) {
  const legacyExampleValue = `secret://repo-example/${envName}/example-api-token`;
  return Object.fromEntries(
    Object.entries(secretMap || {}).filter(
      ([key, value]) => !(key === 'EXAMPLE_API_TOKEN' && value === legacyExampleValue)
    )
  );
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
      destination_name: '',
      destination_server: 'https://kubernetes.default.svc',
      gitops_repo_url: 'https://github.com/Ba-koD/idea.git',
      gitops_repo_branch: 'main',
      gitops_repo_path: 'gitops/apps',
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
          cluster_uuid: '',
          cluster_version: SUPPORTED_NCLOUD_CLUSTER_VERSIONS[0],
          cluster_type_code: 'SVR.VNKS.STAND.C004.M016.G003',
          hypervisor_code: 'KVM',
          auth_method: 'access_key',
          access_key_secret_ref: 'ncloud-dev-access-key',
          secret_key_secret_ref: 'ncloud-dev-secret-key',
          zone_code: 'KR-2',
          vpc_no: 'vpc-dev',
          subnet_no: 'subnet-dev',
          lb_subnet_no: 'lb-subnet-dev',
          lb_public_subnet_no: '',
          login_key_name: 'idea-runtime-login',
          node_pool_name: 'repo-example-dev-pool',
          node_count: 2,
          node_product_code: 'SVR.VSVR.STAND.C002.M004.NET.SSD.B050.G002',
          node_image_label: 'ubuntu-22.04',
          block_storage_size_gb: 50,
          autoscale_enabled: true,
          autoscale_min_node_count: 2,
          autoscale_max_node_count: 4,
          vpc_cidr: '10.10.0.0/16',
          node_subnet_cidr: '10.10.1.0/24',
          lb_private_subnet_cidr: '10.10.10.0/24',
          lb_public_subnet_cidr: '10.10.11.0/24'
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
          cluster_uuid: '',
          cluster_version: SUPPORTED_NCLOUD_CLUSTER_VERSIONS[0],
          cluster_type_code: 'SVR.VNKS.STAND.C004.M016.G003',
          hypervisor_code: 'KVM',
          auth_method: 'access_key',
          access_key_secret_ref: 'ncloud-stage-access-key',
          secret_key_secret_ref: 'ncloud-stage-secret-key',
          zone_code: 'KR-2',
          vpc_no: 'vpc-stage',
          subnet_no: 'subnet-stage',
          lb_subnet_no: 'lb-subnet-stage',
          lb_public_subnet_no: '',
          login_key_name: 'idea-runtime-login',
          node_pool_name: 'repo-example-stage-pool',
          node_count: 2,
          node_product_code: 'SVR.VSVR.STAND.C002.M004.NET.SSD.B050.G002',
          node_image_label: 'ubuntu-22.04',
          block_storage_size_gb: 50,
          autoscale_enabled: true,
          autoscale_min_node_count: 2,
          autoscale_max_node_count: 4,
          vpc_cidr: '10.20.0.0/16',
          node_subnet_cidr: '10.20.1.0/24',
          lb_private_subnet_cidr: '10.20.10.0/24',
          lb_public_subnet_cidr: '10.20.11.0/24'
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
          cluster_uuid: '',
          cluster_version: SUPPORTED_NCLOUD_CLUSTER_VERSIONS[0],
          cluster_type_code: 'SVR.VNKS.STAND.C004.M016.G003',
          hypervisor_code: 'KVM',
          auth_method: 'access_key',
          access_key_secret_ref: 'ncloud-prod-access-key',
          secret_key_secret_ref: 'ncloud-prod-secret-key',
          zone_code: 'KR-2',
          vpc_no: 'vpc-prod',
          subnet_no: 'subnet-prod',
          lb_subnet_no: 'lb-subnet-prod',
          lb_public_subnet_no: '',
          login_key_name: 'idea-runtime-login',
          node_pool_name: 'repo-example-prod-pool',
          node_count: 3,
          node_product_code: 'SVR.VSVR.STAND.C004.M008.NET.SSD.B100.G002',
          node_image_label: 'ubuntu-22.04',
          block_storage_size_gb: 100,
          autoscale_enabled: true,
          autoscale_min_node_count: 3,
          autoscale_max_node_count: 6,
          vpc_cidr: '10.30.0.0/16',
          node_subnet_cidr: '10.30.1.0/24',
          lb_private_subnet_cidr: '10.30.10.0/24',
          lb_public_subnet_cidr: '10.30.11.0/24'
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
    provisioning: {
      terraform_executable: 'terraform',
      site: 'public',
      secret_values: {},
      last_results: {}
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
      dev: {},
      stage: {},
      prod: {}
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
  const incoming = rawState || {};
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
    if (incoming.secrets && Object.prototype.hasOwnProperty.call(incoming.secrets, envName)) {
      merged.secrets[envName] = pruneLegacyExampleSecrets({ ...(incoming.secrets[envName] || {}) }, envName);
    } else {
      merged.secrets[envName] = pruneLegacyExampleSecrets(
        deepMerge(defaultProjectState().secrets[envName], merged.secrets[envName] || {}),
        envName
      );
    }
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
  const [prodActiveColor, setProdActiveColor] = useState('blue');
  const [projectState, setProjectState] = useState(defaultProjectState);
  const [logs, setLogs] = useState([]);
  const [downloadUrl, setDownloadUrl] = useState('');
  const [stateSource, setStateSource] = useState('loading');
  const [isReady, setIsReady] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeploying, setIsDeploying] = useState(false);
  const [isProvisioningTarget, setIsProvisioningTarget] = useState(false);
  const [isImportingEnv, setIsImportingEnv] = useState(false);
  const [isExportingEnv, setIsExportingEnv] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [envImportSummaries, setEnvImportSummaries] = useState({
    dev: null,
    stage: null,
    prod: null
  });
  const [envExchangeText, setEnvExchangeText] = useState({
    dev: '',
    stage: '',
    prod: ''
  });
  const [envDownloadUrls, setEnvDownloadUrls] = useState({
    dev: '',
    stage: '',
    prod: ''
  });
  const [provisionArtifactUrls, setProvisionArtifactUrls] = useState({
    dev: { kubeconfig: '', argocd: '' },
    stage: { kubeconfig: '', argocd: '' },
    prod: { kubeconfig: '', argocd: '' }
  });
  const logEndRef = useRef(null);
  const envFileInputRef = useRef(null);

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

  async function handleProvisionTarget() {
    setIsProvisioningTarget(true);
    setStatusMessage('');

    try {
      const saved = await persistProjectState();
      const response = await fetch(buildApiUrl('/provision-target'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_env: activeEnv,
          project_state: saved,
          apply: true
        })
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `provision-target failed with ${response.status}`);
      }

      const nextState = normalizeProjectState(payload.project_state || saved);
      setProjectState(nextState);
      setStateSource('backend');
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
      setProvisionArtifactUrls((current) => ({
        ...current,
        [activeEnv]: {
          kubeconfig: payload.kubeconfig_download_url || '',
          argocd: payload.argocd_cluster_secret_download_url || ''
        }
      }));
      setLogs(payload.logs || ['Provisioning completed.']);
      setStatusMessage(payload.message || `${activeEnv.toUpperCase()} target provisioned.`);
    } catch (error) {
      setLogs([`Provisioning failed: ${error.message}`]);
      setStatusMessage(`Provisioning failed: ${error.message}`);
    } finally {
      setIsProvisioningTarget(false);
    }
  }

  async function handleTrafficSwitch(color) {
    setProdActiveColor(color);
    try {
      await fetch(buildApiUrl('/traffic/switch'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_color: color })
      });
    } catch (error) {
      setLogs((currentLogs) => [...currentLogs, `Traffic switch failed: ${error.message}`]);
    }
  }

  function openEnvImportPicker() {
    envFileInputRef.current?.click();
  }

  async function submitEnvImport({ file = null, text = '' }) {
    setIsImportingEnv(true);
    setStatusMessage('');

    try {
      const formData = new FormData();
      formData.append('selected_env', activeEnv);
      if (file) {
        formData.append('env_file', file);
      }
      if (text.trim()) {
        formData.append('env_text', text);
      }
      formData.append('project_state', JSON.stringify(projectState));

      const response = await fetch(buildApiUrl('/project-state/import-env'), {
        method: 'POST',
        body: formData
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `env import failed with ${response.status}`);
      }

      const nextState = normalizeProjectState(payload.project_state || projectState);
      const summary = payload.summary || null;
      const importedEnv = summary?.selected_env || activeEnv;

      setProjectState(nextState);
      setStateSource('backend');
      setEnvImportSummaries((current) => ({
        ...current,
        [importedEnv]: summary
      }));
      setEnvExchangeText((current) => ({
        ...current,
        [importedEnv]: text || current[importedEnv]
      }));
      setActiveEnv(importedEnv);
      setLogs((currentLogs) => [
        ...currentLogs,
        `Imported ${summary?.file_name || file?.name || 'pasted.env'} into ${importedEnv.toUpperCase()}.`,
        `Classified ${summary?.env_count || 0} runtime env keys, ${summary?.secret_count || 0} runtime secret keys, and ${summary?.control_plane_secret_count || 0} control-plane secret values.`
      ]);
      setStatusMessage(payload.message || `${importedEnv.toUpperCase()} .env imported.`);
    } catch (error) {
      setLogs((currentLogs) => [...currentLogs, `Env import failed: ${error.message}`]);
      setStatusMessage(`Env import failed: ${error.message}`);
    } finally {
      setIsImportingEnv(false);
    }
  }

  async function handleEnvFileSelected(event) {
    const file = event.target.files?.[0];
    event.target.value = '';

    if (!file) {
      return;
    }

    await submitEnvImport({ file });
  }

  async function handleEnvTextImport() {
    const currentText = envExchangeText[activeEnv] || '';
    if (!currentText.trim()) {
      setStatusMessage('Paste .env text first.');
      return;
    }
    await submitEnvImport({ text: currentText });
  }

  async function handleEnvExport() {
    setIsExportingEnv(true);
    setStatusMessage('');

    try {
      const response = await fetch(buildApiUrl('/project-state/export-env'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_env: activeEnv,
          project_state: projectState
        })
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `env export failed with ${response.status}`);
      }

      setEnvExchangeText((current) => ({
        ...current,
        [activeEnv]: payload.env_text || ''
      }));
      setEnvDownloadUrls((current) => ({
        ...current,
        [activeEnv]: payload.download_url || ''
      }));
      setLogs((currentLogs) => [
        ...currentLogs,
        `Exported ${payload.file_name || `${activeEnv}.env`} from current IDEA project state.`
      ]);
      setStatusMessage(payload.message || `${activeEnv.toUpperCase()} .env export generated.`);
    } catch (error) {
      setLogs((currentLogs) => [...currentLogs, `Env export failed: ${error.message}`]);
      setStatusMessage(`Env export failed: ${error.message}`);
    } finally {
      setIsExportingEnv(false);
    }
  }

  const currentMeta = ENVIRONMENT_META[activeEnv];
  const currentCloudflare = projectState.cloudflare.environments[activeEnv];
  const currentTarget = projectState.targets[activeEnv];
  const currentRuntimeEnv = projectState.env[activeEnv];
  const currentSecrets = projectState.secrets[activeEnv];
  const currentAllowedIps = projectState.access[`${activeEnv}_allowed_source_ips`];
  const currentHostname = projectState.routing[`${activeEnv}_hostname`];
  const currentImportSummary = envImportSummaries[activeEnv];
  const currentEnvExchangeText = envExchangeText[activeEnv];
  const currentEnvDownloadUrl = envDownloadUrls[activeEnv];
  const currentProvisionArtifacts = provisionArtifactUrls[activeEnv];
  const prodExampleBlock = [
    'APP_ENV=prod',
    'APP_DISPLAY_NAME=Repo Example Prod',
    'PUBLIC_API_BASE_URL=/api',
    'NODE_ENV=production'
  ].join('\n');

  const diagramCode = `%%{init: {
    'theme': 'base',
    'themeVariables': {
      'fontSize': '15px',
      'fontFamily': 'Pretendard Variable, Pretendard, SUIT Variable, SUIT, Noto Sans KR, sans-serif',
      'primaryColor': '#ffffff',
      'primaryTextColor': '#0f172a',
      'lineColor': '#64748b',
      'tertiaryColor': '#f8fafc'
    },
    'flowchart': {
      'htmlLabels': true,
      'curve': 'basis',
      'nodeSpacing': 60,
      'rankSpacing': 90,
      'padding': 30
    }
  }}%%
  graph LR
  classDef clusterBox fill:#f8fafc,stroke:${currentMeta.color},stroke-width:2px,stroke-dasharray: 5 5,rx:10,ry:10;
  classDef nodeStyle fill:#fff,color:#0f172a,stroke:#cbd5e1,stroke-width:2px,rx:8,ry:8,font-weight:bold;
  classDef activeNode fill:${currentMeta.color},color:#fff,stroke-width:0px,rx:8,ry:8,font-weight:bold;

  subgraph External [Cloudflare Edge]
    User((User)) --> CF((Tunnel<br/>${currentHostname || 'hostname pending'}))
  end

  subgraph Platform [idea Control Plane]
    CF --> Caddy["Platform Caddy<br/>${projectState.routing.backend_base_path} -> ${projectState.routing.backend_service_name}"]
    GitOps["Argo CD<br/>${projectState.argo.project_name}"] --> NKS

    subgraph NKS [Ncloud NKS: ${currentTarget.ncloud.cluster_name}]
      ${activeEnv === 'prod'
        ? `
        Caddy -->|Active| Blue["Frontend Slot: BLUE"]
        Caddy -.->|Standby| Green["Frontend Slot: GREEN"]
        Blue --> Api["Backend Service<br/>${projectState.routing.backend_service_name}"]
        Green --> Api
      `
        : `
        Caddy --> Frontend["Entry Service<br/>${projectState.routing.entry_service_name}"]
        Frontend --> Api["Backend Service<br/>${projectState.routing.backend_service_name}"]
      `}
      Api --> DB["db service"]
    end
  end

  class External,Platform,NKS clusterBox;
  class User,CF,Caddy,GitOps,Frontend,Api,DB,Blue,Green nodeStyle;
  ${activeEnv === 'prod' ? `class ${prodActiveColor === 'blue' ? 'Blue' : 'Green'} activeNode;` : 'class Frontend activeNode;'}
`;

  return (
    <div className="app-container">
      <input
        ref={envFileInputRef}
        type="file"
        accept=".env,text/plain"
        className="hidden-file-input"
        onChange={handleEnvFileSelected}
      />

      <header className="app-header">
        <h1>IDEA Platform <span className="version-tag">Project State</span></h1>
        <div className="header-right-status">
          <span className="live-status">
            <span className="status-dot green"></span>
            {statusMessage || `State source: ${stateSource}`}
          </span>
        </div>
      </header>

      <div className="content-layout">
        <aside className="sidebar">
          <h3 className="sidebar-title">환경 및 GitOps 설정</h3>

          <div className="config-card global-config-card">
            <div className="form-section-title">App Repository</div>
            <p className="scope-note">Applies to dev, stage, and prod.</p>

            <div className="form-group">
              <label>Project Name</label>
              <input
                type="text"
                value={projectState.project.name}
                onChange={(event) =>
                  updateProjectState((next) => {
                    next.project.name = event.target.value;
                  })
                }
              />
            </div>

            <div className="form-group">
              <label>App Repository URL</label>
              <input
                type="text"
                value={projectState.project.app_repo_url}
                onChange={(event) =>
                  updateProjectState((next) => {
                    next.project.app_repo_url = event.target.value;
                  })
                }
              />
            </div>

            <div className="double-input-row">
              <div className="form-group">
                <label>Git Ref</label>
                <input
                  type="text"
                  value={projectState.project.git_ref}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.project.git_ref = event.target.value;
                    })
                  }
                />
              </div>
              <div className="form-group">
                <label>Repo Access Secret Ref</label>
                <input
                  type="text"
                  value={projectState.project.repo_access_secret_ref}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.project.repo_access_secret_ref = event.target.value;
                    })
                  }
                />
              </div>
            </div>

            <div className="form-section-title">Build Input</div>
            <div className="double-input-row">
              <div className="form-group">
                <label>Frontend Context</label>
                <input
                  type="text"
                  value={projectState.build.frontend_context}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.build.frontend_context = event.target.value;
                    })
                  }
                />
              </div>
              <div className="form-group">
                <label>Frontend Dockerfile</label>
                <input
                  type="text"
                  value={projectState.build.frontend_dockerfile_path}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.build.frontend_dockerfile_path = event.target.value;
                    })
                  }
                />
              </div>
            </div>

            <div className="double-input-row">
              <div className="form-group">
                <label>Backend Context</label>
                <input
                  type="text"
                  value={projectState.build.backend_context}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.build.backend_context = event.target.value;
                    })
                  }
                />
              </div>
              <div className="form-group">
                <label>Backend Dockerfile</label>
                <input
                  type="text"
                  value={projectState.build.backend_dockerfile_path}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.build.backend_dockerfile_path = event.target.value;
                    })
                  }
                />
              </div>
            </div>
          </div>

          <div className="env-selector">
            {ENVIRONMENTS.map((envName) => (
              <button
                key={envName}
                className={`env-btn ${activeEnv === envName ? `selected ${envName}` : ''}`}
                onClick={() => setActiveEnv(envName)}
              >
                {envName.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="config-card" style={{ borderColor: currentMeta.color }}>
            <div className="form-section-title">Cloudflare Reconciler</div>

            <div className="double-input-row">
              <div className="form-group">
                <label>Cloudflare Account ID</label>
                <input
                  type="text"
                  value={projectState.cloudflare.account_id}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.cloudflare.account_id = event.target.value;
                    })
                  }
                />
              </div>
              <div className="form-group">
                <label>Cloudflare Zone ID</label>
                <input
                  type="text"
                  value={projectState.cloudflare.zone_id}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.cloudflare.zone_id = event.target.value;
                    })
                  }
                />
              </div>
            </div>

            <div className="double-input-row">
              <div className="form-group">
                <label>API Token Secret Ref</label>
                <input
                  type="text"
                  value={projectState.cloudflare.api_token_secret_ref}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.cloudflare.api_token_secret_ref = event.target.value;
                    })
                  }
                />
              </div>
              <div className="form-group">
                <label>Tunnel Name</label>
                <input
                  type="text"
                  value={projectState.cloudflare.tunnel_name}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.cloudflare.tunnel_name = event.target.value;
                    })
                  }
                />
              </div>
            </div>

            <div className="double-input-row">
              <div className="form-group">
                <label>{activeEnv.toUpperCase()} Subdomain</label>
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
              </div>
              <div className="form-group">
                <label>{activeEnv.toUpperCase()} Base Domain</label>
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
              </div>
            </div>

            <div className="hostname-preview">
              <span>Hostname Preview</span>
              <strong>{currentHostname || 'base domain required'}</strong>
            </div>

            <div className="form-section-title">Argo CD / Target</div>

            <div className="double-input-row">
              <div className="form-group">
                <label>Argo Project</label>
                <input
                  type="text"
                  value={projectState.argo.project_name}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.argo.project_name = event.target.value;
                    })
                  }
                />
              </div>
              <div className="form-group">
                <label>GitOps Path</label>
                <input
                  type="text"
                  value={projectState.argo.gitops_repo_path}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.argo.gitops_repo_path = event.target.value;
                    })
                  }
                />
              </div>
            </div>

            <div className="double-input-row">
              <div className="form-group">
                <label>NKS Cluster</label>
                <input
                  type="text"
                  value={currentTarget.ncloud.cluster_name}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.targets[activeEnv].ncloud.cluster_name = event.target.value;
                    })
                  }
                />
              </div>
              <div className="form-group">
                <label>Namespace</label>
                <input
                  type="text"
                  value={currentTarget.namespace}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.targets[activeEnv].namespace = event.target.value;
                    })
                  }
                />
              </div>
            </div>

            <div className="double-input-row">
              <div className="form-group">
                <label>Kubernetes Version</label>
                <select
                  value={currentTarget.ncloud.cluster_version}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.targets[activeEnv].ncloud.cluster_version = event.target.value;
                    })
                  }
                >
                  {SUPPORTED_NCLOUD_CLUSTER_VERSIONS.map((version) => (
                    <option key={version} value={version}>
                      {version}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Ncloud Login Key Name</label>
                <input
                  type="text"
                  value={currentTarget.ncloud.login_key_name}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.targets[activeEnv].ncloud.login_key_name = event.target.value;
                    })
                  }
                  placeholder="must already exist in Ncloud"
                />
              </div>
            </div>

            <div className="helper-box">
              <span>Ncloud Provisioning Notes</span>
              <pre>{[
                `Supported Kubernetes versions: ${SUPPORTED_NCLOUD_CLUSTER_VERSIONS.join(', ')}`,
                'login_key_name must match an existing Ncloud login key before provisioning runs.',
                'If cluster_uuid / vpc_no / subnet_no stay as placeholders, Terraform creates new target resources.',
                'If you want to reuse existing infra, replace those fields with real numeric ids or an existing cluster UUID.'
              ].join('\n')}</pre>
            </div>

            <div className="double-input-row">
              <div className="form-group">
                <label>Service Port</label>
                <input
                  type="number"
                  value={currentTarget.service_port}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.targets[activeEnv].service_port = Number(event.target.value || '80');
                    })
                  }
                />
              </div>
              <div className="form-group">
                <label>Argo CD Access</label>
                <input type="text" value={projectState.argo.access_hint} readOnly />
              </div>
            </div>

            {activeEnv === 'prod' && (
              <div className="form-group animate-fade">
                <label>Blue-Green Traffic Control</label>
                <div className="env-selector inline-selector">
                  <button
                    className={`env-btn ${prodActiveColor === 'blue' ? 'selected dev' : ''}`}
                    onClick={() => handleTrafficSwitch('blue')}
                  >
                    BLUE (Active)
                  </button>
                  <button
                    className={`env-btn ${prodActiveColor === 'green' ? 'selected prod' : ''}`}
                    onClick={() => handleTrafficSwitch('green')}
                  >
                    GREEN (Standby)
                  </button>
                </div>
              </div>
            )}

            <div className="form-section-title">{activeEnv.toUpperCase()} Runtime</div>
            <div className="env-import-row">
              <div className="env-import-actions">
                <button
                  type="button"
                  className="secondary-btn env-import-btn"
                  onClick={openEnvImportPicker}
                  disabled={isSaving || isDeploying || isProvisioningTarget || isImportingEnv || isExportingEnv}
                >
                  {isImportingEnv ? `IMPORTING ${activeEnv.toUpperCase()}...` : `IMPORT FILE`}
                </button>
                <button
                  type="button"
                  className="secondary-btn env-import-btn"
                  onClick={handleEnvTextImport}
                  disabled={isSaving || isDeploying || isProvisioningTarget || isImportingEnv || isExportingEnv}
                >
                  IMPORT TEXT
                </button>
                <button
                  type="button"
                  className="secondary-btn env-import-btn"
                  onClick={handleEnvExport}
                  disabled={isSaving || isDeploying || isProvisioningTarget || isImportingEnv || isExportingEnv}
                >
                  {isExportingEnv ? `EXPORTING ${activeEnv.toUpperCase()}...` : `EXPORT .ENV`}
                </button>
              </div>
              <p className="env-import-note">
                `IDEA_*` keys update project state for the selected app environment. `*_SECRET_REF` stores the logical secret name, while `IDEA_REPO_ACCESS_TOKEN_VALUE`, `IDEA_GITOPS_REPO_ACCESS_TOKEN_VALUE`, `IDEA_CLOUDFLARE_API_TOKEN_VALUE`, `IDEA_NCLOUD_ACCESS_KEY_VALUE`, and `IDEA_NCLOUD_SECRET_KEY_VALUE` carry the actual credentials used by tmp provisioning. Non-prefixed keys fill runtime env and secret values for the selected environment.
              </p>
            </div>

            {currentImportSummary && (
              <div className="helper-box import-summary-box">
                <span>Last .env Import</span>
                <pre>{[
                  `file=${currentImportSummary.file_name}`,
                  `mode=${currentImportSummary.import_mode || 'merge'}`,
                  `total_keys=${currentImportSummary.total_count}`,
                  `platform_keys=${currentImportSummary.platform_keys?.join(', ') || '-'}`,
                  `control_plane_secrets=${currentImportSummary.control_plane_secret_refs?.join(', ') || '-'}`,
                  `runtime_env=${currentImportSummary.env_keys.join(', ') || '-'}`,
                  `runtime_secrets=${currentImportSummary.secret_keys.join(', ') || '-'}`
                ].join('\n')}</pre>
              </div>
            )}

            <div className="form-group">
              <label>{activeEnv.toUpperCase()} Import / Export Text (.env)</label>
              <textarea
                rows="8"
                value={currentEnvExchangeText}
                onChange={(event) =>
                  setEnvExchangeText((current) => ({
                    ...current,
                    [activeEnv]: event.target.value
                  }))
                }
                placeholder={`IDEA_SELECTED_ENV=${activeEnv}\nIDEA_IMPORT_MODE=replace\nIDEA_PROJECT_NAME=repo-example\nAPP_ENV=${activeEnv}`}
              />
            </div>

            {currentEnvDownloadUrl && (
              <a href={currentEnvDownloadUrl} download className="download-btn-link env-download-link">
                DOWNLOAD {activeEnv.toUpperCase()} .ENV
              </a>
            )}

            <div className="form-group">
              <label>{activeEnv.toUpperCase()} Runtime Env (.env / non-secret)</label>
              <textarea
                rows="6"
                value={formatKeyValueBlock(currentRuntimeEnv)}
                onChange={(event) =>
                  updateProjectState((next) => {
                    next.env[activeEnv] = parseKeyValueBlock(event.target.value);
                  })
                }
              />
            </div>

            {activeEnv === 'prod' && (
              <div className="helper-box">
                <span>PROD RUNTIME ENV example</span>
                <pre>{prodExampleBlock}</pre>
              </div>
            )}

            <div className="form-group">
              <label>{activeEnv.toUpperCase()} Runtime Secrets / Secret Refs</label>
              <textarea
                rows="4"
                value={formatKeyValueBlock(currentSecrets)}
                onChange={(event) =>
                  updateProjectState((next) => {
                    next.secrets[activeEnv] = parseKeyValueBlock(event.target.value);
                  })
                }
              />
            </div>

            <div className="form-group">
              <label>{activeEnv.toUpperCase()} Allowed Source IPs</label>
              <textarea
                rows="4"
                value={formatLines(currentAllowedIps)}
                onChange={(event) =>
                  updateProjectState((next) => {
                    next.access[`${activeEnv}_allowed_source_ips`] = parseLines(event.target.value);
                  })
                }
              />
            </div>
          </div>

          <div className="action-row">
            <button className="secondary-btn" onClick={handleSave} disabled={isSaving || isDeploying || isProvisioningTarget || isImportingEnv || isExportingEnv}>
              {isSaving ? 'SAVING...' : 'SAVE STATE'}
            </button>

            <button
              className="secondary-btn"
              onClick={handleProvisionTarget}
              disabled={isSaving || isDeploying || isProvisioningTarget || isImportingEnv || isExportingEnv}
            >
              {isProvisioningTarget ? `PROVISIONING ${activeEnv.toUpperCase()}...` : `PROVISION ${activeEnv.toUpperCase()} TARGET`}
            </button>

            <button
              className="main-deploy-btn"
              style={{ backgroundColor: currentMeta.color }}
              onClick={handleDeploy}
              disabled={isSaving || isDeploying || isProvisioningTarget || isImportingEnv || isExportingEnv}
            >
              {isDeploying ? 'GENERATING...' : `GENERATE ${activeEnv.toUpperCase()} BUNDLE`}
            </button>
          </div>

          {(currentProvisionArtifacts.kubeconfig || currentProvisionArtifacts.argocd) && (
            <div className="action-row">
              {currentProvisionArtifacts.kubeconfig && (
                <a href={currentProvisionArtifacts.kubeconfig} download className="download-btn-link env-download-link">
                  DOWNLOAD KUBECONFIG
                </a>
              )}
              {currentProvisionArtifacts.argocd && (
                <a href={currentProvisionArtifacts.argocd} download className="download-btn-link env-download-link">
                  DOWNLOAD ARGO CLUSTER SECRET
                </a>
              )}
            </div>
          )}

          {downloadUrl && (
            <a href={downloadUrl} download className="download-btn-link">
              DOWNLOAD GITOPS BUNDLE
            </a>
          )}
        </aside>

        <main className="main-view">
          <div className="view-header">
            <h3>Infrastructure Topology (Ncloud NKS)</h3>
            <span className="live-badge">{stateSource.toUpperCase()} PROJECT STATE</span>
          </div>

          <div className="topology-summary">
            <div className="summary-tile">
              <span>Repository</span>
              <strong>{projectState.project.git_ref}</strong>
              <small>{projectState.project.app_repo_url}</small>
            </div>
            <div className="summary-tile">
              <span>Environment</span>
              <strong style={{ color: currentMeta.color }}>{currentMeta.label}</strong>
              <small>{currentHostname || 'hostname pending'}</small>
            </div>
            <div className="summary-tile">
              <span>NKS</span>
              <strong>{currentTarget.ncloud.cluster_name}</strong>
              <small>{currentTarget.namespace}</small>
            </div>
          </div>

          <div className="mermaid-wrapper">
            <MermaidViewer chartCode={diagramCode} />
          </div>

          <div className="console-wrapper">
            <div className="console-header">PROJECT_STATE_LOG_STREAM</div>
            <div className="console-content">
              {logs.length === 0 && <span style={{ color: '#444' }}>Waiting for project state signal...</span>}
              {logs.map((log, index) => (
                <div key={`${log}-${index}`}>
                  <span style={{ color: '#555' }}>&gt;&gt;&gt;</span> {log}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>

          <div className="status-bar">
            <p>
              ● Environment:{' '}
              <span style={{ color: currentMeta.color, fontWeight: 'bold' }}>{activeEnv.toUpperCase()}</span>
            </p>
            <p>
              ● Service URL:{' '}
              {currentHostname ? (
                <a
                  href={`https://${currentHostname}`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: currentMeta.color, fontWeight: 'bold', marginLeft: '5px' }}
                >
                  {currentHostname} ↗
                </a>
              ) : (
                <span style={{ color: '#666', marginLeft: '5px' }}>도메인을 입력해 주세요</span>
              )}
            </p>
            <p>
              ● Source: <strong>{stateSource}</strong>
            </p>
            <p>
              ● Cluster: <strong>{currentTarget.ncloud.cluster_name}</strong>
            </p>
            {activeEnv === 'prod' && (
              <p>
                ● Active Slot:{' '}
                <strong style={{ color: prodActiveColor === 'blue' ? '#3b82f6' : '#10b981' }}>
                  {prodActiveColor.toUpperCase()}
                </strong>
              </p>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
