import React, { useEffect, useRef } from 'react';
import mermaid from 'mermaid';

// 보안 설정 및 기본 테마 초기화
mermaid.initialize({
  startOnLoad: true,
  securityLevel: 'loose', 
  theme: 'default',
  flowchart: {
    useMaxWidth: true, // CSS 컨테이너 크기에 맞춰 자연스럽게 꽉 차도록 설정
    htmlLabels: true, 
    curve: 'basis'
  },
  fontFamily: 'Pretendard Variable, Pretendard, SUIT Variable, SUIT, Noto Sans KR, sans-serif'
});

const MermaidViewer = ({ chartCode }) => {
  const mermaidRef = useRef(null);

  useEffect(() => {
    if (mermaidRef.current && chartCode) {
      // 렌더링 시 보안 설정 재확인 및 다이어그램 새로고침
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
      // 다이어그램이 중앙에 예쁘게 배치되도록 스타일 유지
      style={{ width: '100%', height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center' }}
    >
      {chartCode}
    </div>
  );
};

export default MermaidViewer;
