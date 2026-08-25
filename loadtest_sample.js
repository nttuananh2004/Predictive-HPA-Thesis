import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  scenarios: {
    predictive_proactive_demo: {
      executor: 'ramping-arrival-rate',
      startRate: 10,             // Start low
      timeUnit: '1s',
      preAllocatedVUs: 100,      // Pre-allocate to ensure stability
      maxVUs: 1000,              // Safety buffer
      stages: [
        // --- PHASE 1: THE PREDICTIVE RAMP-UP (The most important part) ---
        // 4 minutes is the "Sweet Spot". It's slow enough for your LSTM model 
        // to detect the trend and scale BEFORE the CPU hits the critical threshold.
        { target: 600, duration: '4m' }, 

        // --- PHASE 2: PEAK PERFORMANCE ---
        // Maintain the load to show that the system has successfully scaled 
        // to handle the volume without latency spikes.
        { target: 600, duration: '4m' }, 

        // --- PHASE 3: GRACEFUL COOL-DOWN ---
        // Predictive HPA should ideally anticipate the drop and scale down.
        { target: 100, duration: '2m' }, 

        // --- PHASE 4: IDLE ---
        { target: 0, duration: '1m' },
      ],
    },
  },
};

export default function () {
  // Replace with your actual Load Balancer IPs
  http.get('http://136.112.171.228');
  
  // A small sleep helps keep the VU active without overwhelming the local machine
  sleep(0.5); 
}
