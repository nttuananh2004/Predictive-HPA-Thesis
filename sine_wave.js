import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  duration: '10m',
  vus: 50, // fake users
};

export default function () {
  // Tạo sóng sin theo thời gian (t)
  const t = new Date().getTime() / 1000; 
  const amplitude = 40; // Đỉnh sóng là 40 vus
  const offset = 50;    // Nền tối thiểu là 50
  
  // Pattern hình sin
  const load = Math.floor(Math.sin(t / 60) * amplitude + offset);
  
  http.get('http://34.55.189.54'); // Thay IP của ông vào
  sleep(1); 
}