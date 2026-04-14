import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || '/api';

export const generateInfra = async (formData) => {
  try {
    const response = await axios.post(`${API_BASE_URL}/deploy`, formData);
    const downloadUrl = response.data?.download_url;

    if (downloadUrl) {
      window.location.assign(downloadUrl);
    }

    return response.data;
  } catch (error) {
    console.error("API 요청 실패:", error);
    alert("서버와 연결할 수 없습니다. 백엔드가 켜져 있는지 확인하세요!");
  }
};
