const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || '/api';

export function buildApiUrl(path) {
  const base = API_BASE_URL.replace(/\/$/, '');
  return `${base}${path}`;
}

async function request(path, options = {}) {
  const response = await fetch(buildApiUrl(path), options);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.detail || `${path} failed with ${response.status}`);
  }

  return payload;
}

export function fetchProjectState() {
  return request('/project-state', { cache: 'no-store' });
}

export function saveProjectState(projectState) {
  return request('/project-state', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(projectState)
  });
}

export function deployProject(selectedEnv, projectState) {
  return request('/deploy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      selected_env: selectedEnv,
      project_state: projectState
    })
  });
}
