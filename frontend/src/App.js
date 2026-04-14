import React, { useState } from 'react';
import './App.css';
import MermaidViewer from './components/MermaidViewer';

function App() {
  const [activeEnv, setActiveEnv] = useState('dev'); 
  const [prodActiveColor, setProdActiveColor] = useState('blue');
  const [showToken, setShowToken] = useState(false);
  
  // 추가된 상태: 실시간 로그 및 다운로드 URL
  const [logs, setLogs] = useState([]);
  const [downloadUrl, setDownloadUrl] = useState(null);

  const [projectInfo, setProjectInfo] = useState({
    name: 'Infra-Forge-Project',
    repoUrl: 'https://github.com/yutju/sixsenste-iac', 
    cfToken: '',      
    cfZoneId: '',    
    cfTunnelId: '',  
    baseDomain: 'example.com' 
  });

  const [envs, setEnvs] = useState({
    dev: { envVars: 'DB_HOST=localhost\nDEBUG=true', replica: 1, color: '#3b82f6' },
    stage: { envVars: 'DB_HOST=stage-db\nDEBUG=false', replica: 2, color: '#f59e0b' },
    prod: { envVars: 'DB_HOST=prod-db\nDEBUG=false', replica: 3, color: '#10b981' }
  });

  const handleDeploy = async () => {
    // 배포 시작 시 로그 초기화 및 로딩 메시지
    setLogs([`Initiating deployment for ${activeEnv.toUpperCase()}...`]);
    setDownloadUrl(null);

    const payload = {
      project_name: projectInfo.name,
      repo_url: projectInfo.repoUrl,
      env_type: activeEnv,
      env_vars: envs[activeEnv].envVars,
      replica: parseInt(envs[activeEnv].replica),
      cloudflare: {
        token: projectInfo.cfToken,
        zone_id: projectInfo.cfZoneId,
        tunnel_id: projectInfo.cfTunnelId,
        domain: `${activeEnv}.${projectInfo.baseDomain}`
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
        // 백엔드에서 받은 로그와 다운로드 URL 업데이트
        setLogs(data.logs || ["Deployment completed successfully."]);
        setDownloadUrl(data.download_url);
        alert(`✅ ${activeEnv.toUpperCase()} 배포 완료!`);
      } else {
        setLogs([`❌ Error: ${data.detail || "Unknown error occurred"}`]);
      }
    } catch (err) {
      setLogs(["🚫 Error: Cannot connect to Backend server (localhost:8000)"]);
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
    const currentDomain = `${activeEnv === 'prod' ? 'www' : activeEnv}.${projectInfo.baseDomain}`;
    
    return `graph TD
      classDef vpcBox fill:none,stroke:${themeColor},stroke-width:2px,stroke-dasharray: 5 5;
      classDef nodeStyle fill:#fff,stroke:#232F3E,stroke-width:2px;
      classDef activeNode fill:${themeColor},color:#fff,stroke-width:3px;

      subgraph AWS_Cloud [AWS Cloud: ${envLabel}]
        direction TB
        subgraph VPC [VPC 영역]
          ${isProd ? `
            Caddy["🌐 Caddy (Proxy)"]
            Caddy -->|Active| Blue
            Caddy -.->|Standby| Green
            Blue["🔹 Prod-V1"]
            Green["🌿 Prod-V2"]
            RDS["🗄️ RDS Cluster"]
            Blue & Green --> RDS
          ` : `
            EC2["🖥️ ${envLabel} Server"]
            RDS["🗄️ ${envLabel} DB"]
            EC2 --> RDS
          `}
        end
        Tunnel((☁️ CF Tunnel: ${currentDomain})) --> ${isProd ? 'Caddy' : 'EC2'}
      end

      class VPC vpcBox;
      class EC2,RDS,Caddy,Blue,Green nodeStyle;
      ${isProd ? `class ${prodActiveColor === 'blue' ? 'Blue' : 'Green'} activeNode;` : ''}
    `;
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>🏗️ Infra-Forge <span className="version-tag">Professional</span></h1>
      </header>

      <div className="content-layout">
        <aside className="sidebar">
          <h3 className="sidebar-title">환경 및 인프라 설정</h3>
          
          <div className="env-selector">
            {['dev', 'stage', 'prod'].map(env => (
              <button key={env} className={`env-btn ${activeEnv === env ? 'selected ' + env : ''}`} onClick={() => setActiveEnv(env)}>
                {env.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="config-card" style={{ borderColor: envs[activeEnv].color }}>
            <div className="form-group">
              <label>GitHub Repository URL</label>
              <input type="text" value={projectInfo.repoUrl} onChange={(e) => handleProjectInfoChange('repoUrl', e.target.value)} />
            </div>

            <div className="form-section-title">🌐 Cloudflare Network</div>
            <div className="form-group">
              <label>API Token</label>
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
                <input type="text" placeholder="Domain" value={projectInfo.baseDomain} onChange={(e) => handleProjectInfoChange('baseDomain', e.target.value)} />
              </div>
            </div>
            
            {activeEnv === 'prod' && (
              <div className="form-group animate-fade">
                <label>Active Slot Control</label>
                <div className="env-selector">
                  <button className={`env-btn ${prodActiveColor === 'blue' ? 'selected dev' : ''}`} onClick={() => handleTrafficSwitch('blue')}>BLUE (V1)</button>
                  <button className={`env-btn ${prodActiveColor === 'green' ? 'selected prod' : ''}`} onClick={() => handleTrafficSwitch('green')}>GREEN (V2)</button>
                </div>
              </div>
            )}

            <div className="form-group">
              <label>{activeEnv.toUpperCase()} Env Variables</label>
              <textarea rows="4" value={envs[activeEnv].envVars} onChange={(e) => handleInputChange('envVars', e.target.value)} />
            </div>

            <div className="form-group">
              <label>Target Replicas</label>
              <input type="number" value={envs[activeEnv].replica} onChange={(e) => handleInputChange('replica', e.target.value)} />
            </div>
          </div>

          <button className="main-deploy-btn" style={{ backgroundColor: envs[activeEnv].color }} onClick={handleDeploy}>
            DEPLOY TO {activeEnv.toUpperCase()}
          </button>

          {/* 추가된 기능: 다운로드 버튼 (성공 시 노출) */}
          {downloadUrl && (
            <a href={downloadUrl} className="download-btn-link" style={{ 
              display: 'block', 
              marginTop: '10px', 
              padding: '12px', 
              backgroundColor: '#28a745', 
              color: 'white', 
              textAlign: 'center', 
              textDecoration: 'none', 
              borderRadius: '6px',
              fontWeight: 'bold',
              fontSize: '14px'
            }}>
              📦 DOWNLOAD IAC PACKAGE
            </a>
          )}

          <div className="sidebar-footer-status">
              <div className="status-item"><span className="status-dot green"></span> Argo CD: Connected</div>
              <div className="status-item"><span className="status-dot green"></span> CF Tunnel: Active</div>
          </div>
        </aside>

        <main className="main-view">
          <div className="view-header">
            <h3>Infrastructure Topology</h3>
            <span className="live-badge">LIVE PREVIEW</span>
          </div>
          <div className="mermaid-wrapper">
            <MermaidViewer chartCode={getDiagramCode()} />
          </div>

          {/* 추가된 기능: 실시간 시스템 콘솔 */}
          <div className="console-wrapper" style={{
            marginTop: '20px',
            backgroundColor: '#1e1e1e',
            borderRadius: '8px',
            border: '1px solid #333',
            overflow: 'hidden'
          }}>
            <div style={{ backgroundColor: '#333', padding: '5px 15px', color: '#aaa', fontSize: '12px', fontFamily: 'monospace' }}>
              SYSTEM_LOG_STREAM
            </div>
            <div className="console-content" style={{
              height: '150px',
              padding: '15px',
              color: '#00ff00',
              fontFamily: 'monospace',
              fontSize: '13px',
              overflowY: 'auto',
              textAlign: 'left',
              lineHeight: '1.6'
            }}>
              {logs.length === 0 && <span style={{color: '#555'}}>Waiting for deployment signal...</span>}
              {logs.map((log, i) => (
                <div key={i}><span style={{color: '#888'}}>>>></span> {log}</div>
              ))}
            </div>
          </div>
          
          <div className="status-bar">
            <p>● Status: <span style={{color: envs[activeEnv].color}}>Active</span></p>
            <p>● URL: <a href={`https://${activeEnv === 'prod' ? 'www' : activeEnv}.${projectInfo.baseDomain}`} target="_blank" rel="noreferrer" style={{color: envs[activeEnv].color, fontWeight: 'bold'}}>{activeEnv === 'prod' ? 'www' : activeEnv}.{projectInfo.baseDomain} ↗</a></p>
            {activeEnv === 'prod' && <p>● Active Slot: <strong style={{color: prodActiveColor === 'blue' ? '#3b82f6' : '#10b981'}}>{prodActiveColor.toUpperCase()}</strong></p>}
          </div>
        </main>
      </div>
    </div>
  );
}

export default App;
