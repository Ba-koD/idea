import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import MermaidViewer from './components/MermaidViewer';

function App() {
  const [activeEnv, setActiveEnv] = useState('dev'); 
  const [prodActiveColor, setProdActiveColor] = useState('blue');
  const [showToken, setShowToken] = useState(false);
  
  const [logs, setLogs] = useState([]);
  const [downloadUrl, setDownloadUrl] = useState(null);
  
  const logEndRef = useRef(null);

  const [projectInfo, setProjectInfo] = useState({
    name: 'Infra-Forge-Project',
    repoUrl: '', // ✅ GitHub 레포지토리 기본값 제거
    imageTag: 'latest', 
    cfToken: '',      
    cfZoneId: '',    
    cfTunnelId: '',  
    baseDomain: '' // ✅ 하단 상태바 깔끔함을 위해 기본 도메인도 빈 값으로 설정
  });

  const [envs, setEnvs] = useState({
    dev: { envVars: 'DB_HOST=db-svc\nDEBUG=true', replica: 1, color: '#3b82f6' },
    stage: { envVars: 'DB_HOST=db-svc\nDEBUG=false', replica: 2, color: '#f59e0b' },
    prod: { envVars: 'DB_HOST=db-svc\nDEBUG=false', replica: 3, color: '#10b981' }
  });

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleDeploy = async () => {
    // 유효성 검사: 레포지토리 주소 확인
    if (!projectInfo.repoUrl.trim()) {
      alert("❌ GitHub Repository URL을 입력해 주세요!");
      return;
    }

    setLogs([`🚀 [Step 2] Initiating reconciliation for ${activeEnv.toUpperCase()}...`]);
    setDownloadUrl(null);

    const payload = {
      project_name: projectInfo.name,
      repo_url: projectInfo.repoUrl,
      image_tag: projectInfo.imageTag,
      env_type: activeEnv,
      env_vars: envs[activeEnv].envVars,
      replica: parseInt(envs[activeEnv].replica),
      cloudflare: {
        token: projectInfo.cfToken,
        zone_id: projectInfo.cfZoneId,
        tunnel_id: projectInfo.cfTunnelId,
        domain: projectInfo.baseDomain 
          ? `${activeEnv === 'prod' ? 'www' : activeEnv}.${projectInfo.baseDomain}`
          : ""
      }
    };

    try {
      const response = await fetch('http://localhost:8000/api/deploy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const data = await response.json();

      if (response.ok) {
        setLogs(data.logs || ["Deployment manifests reconciled."]);
        setDownloadUrl(data.download_url);
        alert(`✅ ${activeEnv.toUpperCase()} GitOps 반영 완료!`);
      } else {
        setLogs([`❌ Error: ${data.detail || "Reconciliation failed"}`]);
      }
    } catch (err) {
      setLogs(["🚫 Error: Backend server unreachable (localhost:8000)"]);
      alert("🚫 백엔드 연결 실패!");
    }
  };

  const handleTrafficSwitch = async (color) => {
    setProdActiveColor(color);
    try {
      await fetch('http://localhost:8000/api/traffic/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_color: color })
      });
    } catch (err) { console.error("전환 실패"); }
  };

  const handleInputChange = (field, value) => {
    setEnvs({ ...envs, [activeEnv]: { ...envs[activeEnv], [field]: value } });
  };

  const handleProjectInfoChange = (field, value) => {
    setProjectInfo({ ...projectInfo, [field]: value });
  };

  const getDiagramCode = () => {
    const isProd = activeEnv === 'prod';
    const envLabel = activeEnv.toUpperCase();
    const themeColor = envs[activeEnv].color;
    const currentDomain = projectInfo.baseDomain 
      ? `${activeEnv === 'prod' ? 'www' : activeEnv}.${projectInfo.baseDomain}`
      : "Not Configured";
    
    return `%%{init: {
        'theme': 'base', 
        'themeVariables': { 
          'fontSize': '15px', 
          'fontFamily': 'Pretendard, sans-serif',
          'primaryColor': '#ffffff',
          'primaryTextColor': '#0f172a',
          'lineColor': '#64748b',
          'tertiaryColor': '#f8fafc'
        },
        'flowchart': { 
          'htmlLabels': true, 
          'curve': 'basis',
          'nodeSpacing': 60,
          'rankSpacing': 100,
          'padding': 30
        }
      }}%%
      graph LR
      classDef clusterBox fill:#f8fafc,stroke:${themeColor},stroke-width:2px,stroke-dasharray: 5 5,rx:10,ry:10;
      classDef nodeStyle fill:#fff,color:#0f172a,stroke:#cbd5e1,stroke-width:2px,rx:8,ry:8,font-weight:bold;
      classDef activeNode fill:${themeColor},color:#fff,stroke-width:0px,rx:8,ry:8,font-weight:bold;

      subgraph External [Internet Access]
        User((👤 User)) --> CF((☁️ CF Tunnel<br/>${currentDomain}))
      end

      subgraph Platform [idea Control Plane]
        CF --> Caddy["🌐 Platform Caddy<br/>(Reverse Proxy)"]
        
        subgraph Cluster [kind Cluster: ${envLabel}]
          ${isProd ? `
            Caddy -->|Active| Blue
            Caddy -.->|Standby| Green
            Blue["📦 Prod-Slot: BLUE "]
            Green["📦 Prod-Slot: GREEN "]
            DB["🗄️ K8s Service: DB "]
            Blue --> DB
            Green --> DB
          ` : `
            Caddy --> Svc["🔌 K8s Service<br/>${envLabel} "]
            Svc --> Pod1["📦 App Pod<br/>(Replica 1) "]
            ${envs[activeEnv].replica > 1 ? `Svc --> Pod2["📦 App Pod<br/>(Replica 2+) "]` : ''}
            DB["🗄️ K8s Service: DB "]
            Svc --> DB
          `}
        end
      end

      class External,Platform,Cluster clusterBox;
      class User,CF,Caddy,Svc,Pod1,Pod2,Blue,Green,DB nodeStyle;
      ${isProd ? `class ${prodActiveColor === 'blue' ? 'Blue' : 'Green'} activeNode;` : ''}
    `;
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>🏗️ Infra-Forge <span className="version-tag">Professional</span></h1>
        <div className="header-right-status">
            <span className="live-status"><span className="status-dot green"></span> System Online</span>
        </div>
      </header>

      <div className="content-layout">
        <aside className="sidebar">
          <h3 className="sidebar-title">환경 및 GitOps 설정</h3>
          
          <div className="env-selector">
            {['dev', 'stage', 'prod'].map(env => (
              <button key={env} className={`env-btn ${activeEnv === env ? 'selected ' + env : ''}`} onClick={() => setActiveEnv(env)}>
                {env.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="config-card" style={{ borderColor: envs[activeEnv].color }}>
            <div className="form-group">
              <label>App Repository URL (Repo B)</label>
              <input 
                type="text" 
                value={projectInfo.repoUrl} 
                onChange={(e) => handleProjectInfoChange('repoUrl', e.target.value)} 
                placeholder="GitHub 레포지토리 주소를 입력하세요" 
              />
            </div>

            <div className="form-group">
              <label>App Image Tag (Branch/Version)</label>
              <input 
                type="text" 
                value={projectInfo.imageTag} 
                onChange={(e) => handleProjectInfoChange('imageTag', e.target.value)} 
                placeholder="예: latest, v1.0.1, main"
              />
            </div>

            <div className="form-section-title">🌐 Cloudflare Reconciler</div>
            <div className="form-group">
              <label>Cloudflare API Token</label>
              <div style={{ position: 'relative' }}>
                <input 
                  type={showToken ? "text" : "password"} 
                  placeholder="CF_API_TOKEN" 
                  value={projectInfo.cfToken} 
                  onChange={(e) => handleProjectInfoChange('cfToken', e.target.value)} 
                />
                <button 
                  type="button"
                  onClick={() => setShowToken(!showToken)}
                  style={{ position: 'absolute', right: '5px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '12px' }}
                >
                  {showToken ? "👀" : "🙈"}
                </button>
              </div>
            </div>
            <div className="form-group">
              <label>Tunnel ID / Base Domain</label>
              <div style={{ display: 'flex', gap: '5px' }}>
                <input type="text" placeholder="Tunnel ID" value={projectInfo.cfTunnelId} onChange={(e) => handleProjectInfoChange('cfTunnelId', e.target.value)} />
                <input type="text" placeholder="Base Domain (예: example.com)" value={projectInfo.baseDomain} onChange={(e) => handleProjectInfoChange('baseDomain', e.target.value)} />
              </div>
            </div>
            
            {activeEnv === 'prod' && (
              <div className="form-group animate-fade">
                <label>Blue-Green Traffic Control</label>
                <div className="env-selector">
                  <button className={`env-btn ${prodActiveColor === 'blue' ? 'selected dev' : ''}`} onClick={() => handleTrafficSwitch('blue')}>BLUE (Active)</button>
                  <button className={`env-btn ${prodActiveColor === 'green' ? 'selected prod' : ''}`} onClick={() => handleTrafficSwitch('green')}>GREEN (Standby)</button>
                </div>
              </div>
            )}

            <div className="form-group">
              <label>{activeEnv.toUpperCase()} Runtime Env (.env)</label>
              <textarea rows="4" value={envs[activeEnv].envVars} onChange={(e) => handleInputChange('envVars', e.target.value)} />
            </div>

            <div className="form-group">
              <label>Target Replicas (K8s Pods)</label>
              <input type="number" value={envs[activeEnv].replica} onChange={(e) => handleInputChange('replica', e.target.value)} />
            </div>
          </div>

          <button className="main-deploy-btn" style={{ backgroundColor: envs[activeEnv].color }} onClick={handleDeploy}>
            RECONCILE TO {activeEnv.toUpperCase()}
          </button>

          {downloadUrl && (
            <a 
              href={downloadUrl} 
              download={`${projectInfo.name}_${activeEnv}_manifests.zip`} 
              className="download-btn-link" 
              style={{ 
                display: 'block', 
                marginTop: '10px', 
                padding: '12px', 
                backgroundColor: '#10b981', 
                color: 'white', 
                textAlign: 'center', 
                textDecoration: 'none', 
                borderRadius: '8px',
                fontWeight: 'bold',
                fontSize: '14px',
                boxShadow: '0 4px 6px rgba(16, 185, 129, 0.2)'
              }}
            >
              📦 DOWNLOAD GITOPS BUNDLE
            </a>
          )}
        </aside>

        <main className="main-view">
          <div className="view-header">
            <h3>Infrastructure Topology (kind Cluster)</h3>
            <span className="live-badge">STEP 4: LIVE ROUTING</span>
          </div>
          
          <div className="mermaid-wrapper">
            <MermaidViewer chartCode={getDiagramCode()} />
          </div>

          <div className="console-wrapper">
            <div className="console-header">
              RECONCILIATION_LOG_STREAM
            </div>
            <div className="console-content">
              {logs.length === 0 && <span style={{color: '#444'}}>Waiting for reconciliation signal...</span>}
              {logs.map((log, i) => (
                <div key={i}><span style={{color: '#555'}}>&gt;&gt;&gt;</span> {log}</div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
          
          <div className="status-bar">
            <p>● Environment: <span style={{color: envs[activeEnv].color, fontWeight: 'bold'}}>{activeEnv.toUpperCase()}</span></p>
            <p>
              ● Service URL: 
              {projectInfo.baseDomain ? (
                <a href={`https://${activeEnv === 'prod' ? 'www' : activeEnv}.${projectInfo.baseDomain}`} target="_blank" rel="noreferrer" style={{color: envs[activeEnv].color, fontWeight: 'bold', marginLeft: '5px'}}>
                  {activeEnv === 'prod' ? 'www' : activeEnv}.{projectInfo.baseDomain} ↗
                </a>
              ) : (
                <span style={{color: '#666', marginLeft: '5px'}}>도메인을 입력해 주세요</span>
              )}
            </p>
            {activeEnv === 'prod' && <p>● Active Slot: <strong style={{color: prodActiveColor === 'blue' ? '#3b82f6' : '#10b981'}}>{prodActiveColor.toUpperCase()}</strong></p>}
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;