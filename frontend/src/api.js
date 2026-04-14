import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000'; // 백엔드 주소

export const generateInfra = async (formData) => {
  try {
    const response = await axios.post(`${API_BASE_URL}/generate`, formData, {
      responseType: 'blob', // 파일 다운로드를 위해 반드시 설정
    });
    
    // 브라우저에서 파일을 즉시 다운로드하게 만드는 로직
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${formData.project_name}_${formData.env}.zip`);
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (error) {
    console.error("API 요청 실패:", error);
    alert("서버와 연결할 수 없습니다. 백엔드가 켜져 있는지 확인하세요!");
  }
};
