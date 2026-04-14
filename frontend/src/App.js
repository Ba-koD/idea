import React, { useEffect, useRef, useState } from 'react';
import './App.css';
import MermaidViewer from './components/MermaidViewer';

const ENVIRONMENTS = ['dev', 'stage', 'prod'];
const STORAGE_KEY = 'idea-project-state-v3';
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || '/api';
const SUPPORTED_NCLOUD_CLUSTER_VERSIONS = ['1.33.4', '1.34.3', '1.32.8'];
const DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV = {
  dev: 's2-g3a',
  stage: 's2-g3a',
  prod: 's4-g3a'
};
const DEFAULT_PLATFORM_TUNNEL_NAME = 'idea-platform';
const ENVIRONMENT_META = {
  dev: { color: '#3b82f6', label: 'Development' },
  stage: { color: '#f59e0b', label: 'Staging' },
  prod: { color: '#10b981', label: 'Production' }
};

function buildApiUrl(path) {
  const base = API_BASE_URL.replace(/\/$/, '');
  return `${base}${path}`;
}

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function stripAnsiSequences(text) {
  return String(text || '').replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, '');
}

function ansiStyleForState(state) {
  const style = {};

  if (state.bold) {
    style.fontWeight = 700;
  }
  if (state.color) {
    style.color = state.color;
  }

  return style;
}

function parseAnsiSegments(text) {
  const raw = String(text || '');
  const pattern = /\u001b\[([0-9;]*)m/g;
  const segments = [];
  let lastIndex = 0;
  let match;
  const state = {
    color: '',
    bold: false
  };

  const colorMap = {
    30: '#111827',
    31: '#ef4444',
    32: '#22c55e',
    33: '#f59e0b',
    34: '#3b82f6',
    35: '#d946ef',
    36: '#06b6d4',
    37: '#e5e7eb',
    90: '#6b7280',
    91: '#f87171',
    92: '#4ade80',
    93: '#fbbf24',
    94: '#60a5fa',
    95: '#e879f9',
    96: '#22d3ee',
    97: '#f9fafb'
  };

  function pushText(endIndex) {
    if (endIndex <= lastIndex) {
      return;
    }
    const value = raw.slice(lastIndex, endIndex);
    if (!value) {
      return;
    }
    segments.push({
      text: value,
      style: ansiStyleForState(state)
    });
  }

  function applyCode(code) {
    if (code === 0) {
      state.color = '';
      state.bold = false;
      return;
    }
    if (code === 1) {
      state.bold = true;
      return;
    }
    if (code === 22) {
      state.bold = false;
      return;
    }
    if (code === 39) {
      state.color = '';
      return;
    }
    if (Object.prototype.hasOwnProperty.call(colorMap, code)) {
      state.color = colorMap[code];
    }
  }

  while ((match = pattern.exec(raw)) !== null) {
    pushText(match.index);
    const codes = (match[1] || '0')
      .split(';')
      .map((value) => Number(value))
      .filter((value) => !Number.isNaN(value));

    if (codes.length === 0) {
      applyCode(0);
    } else {
      codes.forEach(applyCode);
    }

    lastIndex = pattern.lastIndex;
  }

  pushText(raw.length);

  return segments.length > 0 ? segments : [{ text: raw, style: {} }];
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

function preferredBaseDomain(state) {
  for (const envName of ['prod', 'stage', 'dev']) {
    const baseDomain = (state?.cloudflare?.environments?.[envName]?.base_domain || '').trim().toLowerCase();
    if (baseDomain) {
      return baseDomain;
    }
  }
  return '';
}

function desiredArgoAccessHint(state) {
  return `https://argo.${preferredBaseDomain(state) || 'rnen.kr'}`;
}

function normalizeArgoAccessHint(rawHint, state) {
  const hint = String(rawHint || '').trim();
  const desired = desiredArgoAccessHint(state);

  if (!hint) {
    return desired;
  }

  try {
    const url = new URL(hint.includes('://') ? hint : `https://${hint}`);
    return `${url.protocol}//${url.hostname}`;
  } catch (error) {
    return desired;
  }
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

function appendLogMessage(currentLogs, message) {
  if (!message) {
    return currentLogs;
  }
  if (currentLogs[currentLogs.length - 1] === message) {
    return currentLogs;
  }
  return [...currentLogs, message];
}

function pruneLegacyExampleSecrets(secretMap, envName) {
  const legacyExampleValue = `secret://repo-example/${envName}/example-api-token`;
  return Object.fromEntries(
    Object.entries(secretMap || {}).filter(
      ([key, value]) => !(key === 'EXAMPLE_API_TOKEN' && value === legacyExampleValue)
    )
  );
}

function normalizeNcloudNodeProductCode(rawValue, envName) {
  const fallback = DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV[envName] || 's2-g3a';
  const value = String(rawValue || '').trim();
  if (!value || value.toUpperCase().startsWith('SVR.')) {
    return fallback;
  }
  return value;
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
      admin_password_secret_ref: 'argocd-admin-password',
      admin_password_last_applied_at: '',
      access_hint: 'https://argo.rnen.kr'
    },
    cloudflare: {
      enabled: true,
      account_id: '2052eb94f7b555bd3bf9db83c1f4edbf',
      zone_id: 'aaafd11f9c6912ba37c1d52a69b78398',
      api_token_secret_ref: 'cloudflare-api-token',
      tunnel_name: DEFAULT_PLATFORM_TUNNEL_NAME,
      route_mode: 'platform_caddy',
      environments: {
        dev: { subdomain: 'dev', base_domain: 'rnen.kr' },
        stage: { subdomain: 'stage', base_domain: 'rnen.kr' },
        prod: { subdomain: 'prod', base_domain: 'rnen.kr' }
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
          node_pool_id: '',
          login_key_name: 'idea-runtime-login',
          node_pool_name: 'repo-example-dev-pool',
          node_count: 2,
          node_product_code: DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV.dev,
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
          node_pool_id: '',
          login_key_name: 'idea-runtime-login',
          node_pool_name: 'repo-example-stage-pool',
          node_count: 2,
          node_product_code: DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV.stage,
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
          node_pool_id: '',
          login_key_name: 'idea-runtime-login',
          node_pool_name: 'repo-example-prod-pool',
          node_count: 3,
          node_product_code: DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV.prod,
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
      dev_hostname: 'dev.rnen.kr',
      stage_hostname: 'stage.rnen.kr',
      prod_hostname: 'prod.rnen.kr'
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

  if (!String(merged.cloudflare.tunnel_name || '').trim()) {
    merged.cloudflare.tunnel_name = DEFAULT_PLATFORM_TUNNEL_NAME;
  }

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
    if (incoming.env && Object.prototype.hasOwnProperty.call(incoming.env, envName)) {
      merged.env[envName] = { ...(incoming.env[envName] || {}) };
    } else {
      merged.env[envName] = deepMerge(defaultProjectState().env[envName], merged.env[envName] || {});
    }
    if (incoming.secrets && Object.prototype.hasOwnProperty.call(incoming.secrets, envName)) {
      merged.secrets[envName] = pruneLegacyExampleSecrets({ ...(incoming.secrets[envName] || {}) }, envName);
    } else {
      merged.secrets[envName] = pruneLegacyExampleSecrets(
        deepMerge(defaultProjectState().secrets[envName], merged.secrets[envName] || {}),
        envName
      );
    }
    merged.targets[envName] = deepMerge(defaultProjectState().targets[envName], merged.targets[envName] || {});
    merged.targets[envName].ncloud.node_product_code = normalizeNcloudNodeProductCode(
      merged.targets[envName].ncloud.node_product_code,
      envName
    );
    merged.access[`${envName}_allowed_source_ips`] = merged.access[`${envName}_allowed_source_ips`] || [];
  });

  merged.delivery.healthcheck_path =
    merged.delivery.healthcheck_path || `${merged.routing.backend_base_path.replace(/\/$/, '')}/healthz`;
  merged.argo.access_hint = normalizeArgoAccessHint(merged.argo.access_hint, merged);

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

function defaultEnvLogs() {
  return {
    dev: [],
    stage: [],
    prod: []
  };
}

function buildEnvLogsFromState(state, activeEnv, activeMessage = '') {
  const nextLogs = defaultEnvLogs();
  ENVIRONMENTS.forEach((envName) => {
    const savedLogs = state?.provisioning?.last_results?.[envName]?.logs_tail;
    nextLogs[envName] = Array.isArray(savedLogs) ? [...savedLogs] : [];
  });
  if (activeMessage) {
    nextLogs[activeEnv] = appendLogMessage(nextLogs[activeEnv], activeMessage);
  }
  return nextLogs;
}

function getEnvProvisionState(state, envName) {
  const result = state?.provisioning?.last_results?.[envName] || {};
  const clusterUuid = String(state?.targets?.[envName]?.ncloud?.cluster_uuid || '').trim();

  if (result.status === 'destroyed') {
    return 'Destroyed';
  }
  if (clusterUuid) {
    return 'Provisioned';
  }
  if (result.status === 'failed') {
    return 'Failed';
  }
  return 'Not provisioned';
}

function App() {
  const [activeEnv, setActiveEnv] = useState('dev');
  const [prodActiveColor, setProdActiveColor] = useState('blue');
  const [projectState, setProjectState] = useState(defaultProjectState);
  const [envLogs, setEnvLogs] = useState(defaultEnvLogs);
  const [stateSource, setStateSource] = useState('loading');
  const [isReady, setIsReady] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [activeTargetOperation, setActiveTargetOperation] = useState('');
  const [isImportingEnv, setIsImportingEnv] = useState(false);
  const [isExportingEnv, setIsExportingEnv] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [isToastExpanded, setIsToastExpanded] = useState(false);
  const [isToastDismissed, setIsToastDismissed] = useState(false);
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
  const isProvisioningTarget = activeTargetOperation === 'apply';
  const isDestroyingTarget = activeTargetOperation === 'destroy';
  const isTargetOperationPending = Boolean(activeTargetOperation);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeEnv, envLogs]);

  useEffect(() => {
    if (statusMessage) {
      setIsToastDismissed(false);
      setIsToastExpanded(false);
    }
  }, [statusMessage]);

  useEffect(() => {
    if (!statusMessage) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      setStatusMessage('');
      setIsToastExpanded(false);
      setIsToastDismissed(false);
    }, 5000);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [statusMessage]);

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
        setEnvLogs(buildEnvLogsFromState(payload, activeEnv, `Loaded project state from backend for ${payload.project.name}.`));
        setStateSource('backend');
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      } catch (error) {
        const stored = readStoredState();
        if (cancelled) {
          return;
        }

        if (stored) {
          setProjectState(stored);
          setEnvLogs(buildEnvLogsFromState(stored, activeEnv, 'Backend state unavailable. Loaded the last browser snapshot.'));
          setStateSource('browser');
        } else {
          const fallback = normalizeProjectState({});
          setProjectState(fallback);
          setEnvLogs(buildEnvLogsFromState(fallback, activeEnv, 'No saved state found yet. Loaded repo_example defaults.'));
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
      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [activeEnv]: appendLogMessage(currentLogs[activeEnv] || [], 'Saved project state to backend.')
      }));
      setStatusMessage('Project State saved.');
    } catch (error) {
      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [activeEnv]: appendLogMessage(currentLogs[activeEnv] || [], `Save failed: ${error.message}`)
      }));
      setStatusMessage(`Save failed: ${error.message}`);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTargetOperation(operation) {
    setActiveTargetOperation(operation);
    setStatusMessage('');

    try {
      const saved = await persistProjectState();
      const response = await fetch(buildApiUrl('/provision-target/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_env: activeEnv,
          project_state: saved,
          apply: true,
          operation
        })
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `provision-target failed with ${response.status}`);
      }

      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [activeEnv]: payload.logs || [`Started ${activeEnv.toUpperCase()} ${operation}.`]
      }));
      setStatusMessage(payload.message || `${activeEnv.toUpperCase()} ${operation} started.`);

      while (true) {
        await sleep(1000);
        const statusResponse = await fetch(buildApiUrl(`/provision-target/status/${payload.task_id}`), {
          cache: 'no-store'
        });
        const statusPayload = await statusResponse.json();
        if (!statusResponse.ok) {
          throw new Error(statusPayload.detail?.message || statusPayload.detail || `provision status failed with ${statusResponse.status}`);
        }

        setEnvLogs((currentLogs) => ({
          ...currentLogs,
          [activeEnv]: statusPayload.logs || []
        }));

        if (statusPayload.status === 'completed') {
          const result = statusPayload.result || {};
          const nextState = normalizeProjectState(result.project_state || saved);
          setProjectState(nextState);
          setStateSource('backend');
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
          setProvisionArtifactUrls((current) => ({
            ...current,
            [activeEnv]: operation === 'destroy'
              ? { kubeconfig: '', argocd: '' }
              : {
                  kubeconfig: result.kubeconfig_download_url || '',
                  argocd: result.argocd_cluster_secret_download_url || ''
                }
          }));
          setStatusMessage(
            result.message || `${activeEnv.toUpperCase()} target ${operation === 'destroy' ? 'destroyed' : 'provisioned'}.`
          );
          break;
        }

        if (statusPayload.status === 'failed') {
          const failedResult = statusPayload.result || {};
          if (failedResult.project_state) {
            const nextState = normalizeProjectState(failedResult.project_state);
            setProjectState(nextState);
            setStateSource('backend');
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
          }
          throw new Error(statusPayload.error || 'provisioning task failed');
        }
      }
    } catch (error) {
      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [activeEnv]: appendLogMessage(
          currentLogs[activeEnv] || [],
          `${operation === 'destroy' ? 'Destroy' : 'Provisioning'} failed: ${error.message}`
        )
      }));
      setStatusMessage(`${operation === 'destroy' ? 'Destroy' : 'Provisioning'} failed: ${error.message}`);
    } finally {
      setActiveTargetOperation('');
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
      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [activeEnv]: appendLogMessage(currentLogs[activeEnv] || [], `Traffic switch failed: ${error.message}`)
      }));
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
      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [importedEnv]: [
          ...(currentLogs[importedEnv] || []),
          `Imported ${summary?.file_name || file?.name || 'pasted.env'} into ${importedEnv.toUpperCase()}.`,
          `Classified ${summary?.env_count || 0} runtime env keys, ${summary?.secret_count || 0} runtime secret keys, and ${summary?.control_plane_secret_count || 0} control-plane secret values.`
        ]
      }));
      setStatusMessage(payload.message || `${importedEnv.toUpperCase()} .env imported.`);
    } catch (error) {
      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [activeEnv]: appendLogMessage(currentLogs[activeEnv] || [], `Env import failed: ${error.message}`)
      }));
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
      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [activeEnv]: [
          ...(currentLogs[activeEnv] || []),
          `Exported ${payload.file_name || `${activeEnv}.env`} from current IDEA project state.`
        ]
      }));
      setStatusMessage(payload.message || `${activeEnv.toUpperCase()} .env export generated.`);
    } catch (error) {
      setEnvLogs((currentLogs) => ({
        ...currentLogs,
        [activeEnv]: appendLogMessage(currentLogs[activeEnv] || [], `Env export failed: ${error.message}`)
      }));
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
  const currentLogs = envLogs[activeEnv] || [];
  const currentProvisionState = getEnvProvisionState(projectState, activeEnv);
  const currentProvisionResult = projectState.provisioning?.last_results?.[activeEnv] || null;
  const canDestroyCurrentTarget =
    currentProvisionState === 'Provisioned' ||
    Boolean(String(currentTarget.ncloud.cluster_uuid || '').trim()) ||
    Boolean(String(currentTarget.ncloud.node_pool_id || '').trim());
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
            {`State source: ${stateSource} · ${activeEnv.toUpperCase()} ${currentProvisionState}`}
          </span>
        </div>
      </header>

      <div className="content-layout">
        <aside className="sidebar">
          <h3 className="sidebar-title">환경 및 GitOps 설정</h3>
          <div className="sidebar-scroll">

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
                  placeholder="@, *, dev"
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
                <label>Argo Admin Password Secret Ref</label>
                <input
                  type="text"
                  value={projectState.argo.admin_password_secret_ref}
                  onChange={(event) =>
                    updateProjectState((next) => {
                      next.argo.admin_password_secret_ref = event.target.value;
                    })
                  }
                  placeholder="argocd-admin-password"
                />
              </div>
              <div className="form-group">
                <label>Argo Password Applied At</label>
                <input
                  type="text"
                  value={projectState.argo.admin_password_last_applied_at || 'not applied yet'}
                  readOnly
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
                  placeholder="created automatically if missing"
                />
              </div>
            </div>

            <div className="helper-box">
              <span>Ncloud Provisioning Notes</span>
              <pre>{[
                `Supported Kubernetes versions: ${SUPPORTED_NCLOUD_CLUSTER_VERSIONS.join(', ')}`,
                `Default node server spec: ${DEFAULT_NCLOUD_NODE_SERVER_SPEC_BY_ENV[activeEnv]}`,
                'Legacy SVR.* node product codes are normalized to valid NKS serverSpecCode values automatically.',
                'login_key_name is created automatically if it does not exist yet.',
                'Provisioning also tries to register the new cluster into the platform Argo CD automatically.',
                'If IDEA_ARGO_ADMIN_PASSWORD_VALUE is present, provisioning also updates the platform Argo CD admin password automatically.',
                'If Cloudflare control-plane values are present, provisioning also tries to reconcile argo.rnen.kr automatically.',
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
                <label>Argo CD URL</label>
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
            <div className="form-section-title import-section-title">Import / Export (.env)</div>
            <div className="env-import-row">
              <div className="env-import-actions">
                <button
                  type="button"
                  className="secondary-btn env-import-btn"
                  onClick={openEnvImportPicker}
                  disabled={isSaving || isTargetOperationPending || isImportingEnv || isExportingEnv}
                >
                  {isImportingEnv ? `IMPORTING ${activeEnv.toUpperCase()}...` : `IMPORT FILE`}
                </button>
                <button
                  type="button"
                  className="secondary-btn env-import-btn"
                  onClick={handleEnvTextImport}
                  disabled={isSaving || isTargetOperationPending || isImportingEnv || isExportingEnv}
                >
                  IMPORT TEXT
                </button>
                <button
                  type="button"
                  className="secondary-btn env-import-btn"
                  onClick={handleEnvExport}
                  disabled={isSaving || isTargetOperationPending || isImportingEnv || isExportingEnv}
                >
                  {isExportingEnv ? `EXPORTING ${activeEnv.toUpperCase()}...` : `EXPORT .ENV`}
                </button>
              </div>
              <p className="env-import-note">
                `IDEA_*` keys update project state for the selected app environment. `*_SECRET_REF` stores the logical secret name, while `IDEA_REPO_ACCESS_TOKEN_VALUE`, `IDEA_GITOPS_REPO_ACCESS_TOKEN_VALUE`, `IDEA_ARGO_ADMIN_PASSWORD_VALUE`, `IDEA_CLOUDFLARE_API_TOKEN_VALUE`, `IDEA_NCLOUD_ACCESS_KEY_VALUE`, and `IDEA_NCLOUD_SECRET_KEY_VALUE` carry the actual credentials used by tmp provisioning. Non-prefixed keys fill runtime env and secret values for the selected environment.
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
                placeholder={`IDEA_SELECTED_ENV=${activeEnv}\nIDEA_IMPORT_MODE=replace\nIDEA_PROJECT_NAME=repo-example\nIDEA_CLOUDFLARE_SUBDOMAIN=${activeEnv}\nAPP_ENV=${activeEnv}`}
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
            <button className="secondary-btn" onClick={handleSave} disabled={isSaving || isTargetOperationPending || isImportingEnv || isExportingEnv}>
              {isSaving ? 'SAVING...' : 'SAVE STATE'}
            </button>

            <button
              className="success-btn"
              onClick={() => handleTargetOperation('apply')}
              disabled={isSaving || isTargetOperationPending || isImportingEnv || isExportingEnv}
            >
              {isProvisioningTarget ? `PROVISIONING ${activeEnv.toUpperCase()}...` : `PROVISION ${activeEnv.toUpperCase()} TARGET`}
            </button>

            <button
              className="danger-btn"
              onClick={() => handleTargetOperation('destroy')}
              disabled={isSaving || isTargetOperationPending || isImportingEnv || isExportingEnv || !canDestroyCurrentTarget}
            >
              {isDestroyingTarget ? `DESTROYING ${activeEnv.toUpperCase()}...` : `DESTROY ${activeEnv.toUpperCase()} TARGET`}
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

          </div>
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
            <div className="console-header">{`${activeEnv.toUpperCase()}_PROJECT_STATE_LOG_STREAM`}</div>
            <div className="console-content">
              {currentLogs.length === 0 && <span style={{ color: '#444' }}>Waiting for project state signal...</span>}
              {currentLogs.map((log, index) => (
                <div key={`${log}-${index}`}>
                  <span style={{ color: '#555' }}>&gt;&gt;&gt;</span>{' '}
                  {parseAnsiSegments(log).map((segment, segmentIndex) => (
                    <span key={`${index}-${segmentIndex}`} style={segment.style}>
                      {segment.text}
                    </span>
                  ))}
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
              ● Provisioning: <strong>{currentProvisionState}</strong>
            </p>
            <p>
              ● Cluster: <strong>{currentTarget.ncloud.cluster_name}</strong>
            </p>
            {currentProvisionResult?.applied_at && (
              <p>
                ● Last Applied: <strong>{new Date(currentProvisionResult.applied_at).toLocaleString()}</strong>
              </p>
            )}
            {currentProvisionResult?.destroyed_at && (
              <p>
                ● Last Destroyed: <strong>{new Date(currentProvisionResult.destroyed_at).toLocaleString()}</strong>
              </p>
            )}
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

      {statusMessage && !isToastDismissed && (
        <div className={`floating-toast ${isToastExpanded ? 'expanded' : ''}`} role="status" aria-live="polite">
          <button
            type="button"
            className="toast-text"
            onClick={() => setIsToastExpanded((current) => !current)}
            title={stripAnsiSequences(statusMessage)}
          >
            {stripAnsiSequences(statusMessage)}
          </button>
          <button
            type="button"
            className="toast-close"
            onClick={() => {
              setIsToastDismissed(true);
              setStatusMessage('');
            }}
            aria-label="Dismiss status message"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}

export default App;
