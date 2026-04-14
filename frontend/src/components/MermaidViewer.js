import React, { useEffect, useRef } from 'react';
import mermaid from 'mermaid';

// 보안 설정을 여기서 미리 초기화합니다.
mermaid.initialize({
  startOnLoad: true,
  securityLevel: 'loose', // ★매우 중요: 이게 있어야 외부 URL 이미지를 불러옵니다!
  theme: 'default',
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true, // HTML 태그(img 등) 사용 허용
    curve: 'basis'
  },
  fontFamily: 'Pretendard'
});

const MermaidViewer = ({ chartCode }) => {
  const mermaidRef = useRef(null);

  useEffect(() => {
    if (mermaidRef.current && chartCode) {
      // 매번 렌더링할 때마다 보안 설정을 다시 확인
      mermaid.initialize({ securityLevel: 'loose' });
      
      mermaidRef.current.removeAttribute('data-processed');
      mermaid.contentLoaded();
    }
  }, [chartCode]);

  return (
    <div 
      key={chartCode}
      className="mermaid" 
      ref={mermaidRef}
      style={{ width: '100%', height: '100%', display: 'flex', justifyContent: 'center' }}
    >
      {chartCode}
    </div>
  );
};

export default MermaidViewer;
