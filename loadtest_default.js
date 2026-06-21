import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  scenarios: {
    predictive_hpa_evaluation: {
      executor: 'ramping-arrival-rate',
      startRate: 10,                 // Start with a low baseline workload
      timeUnit: '1s',
      preAllocatedVUs: 100,          // Pre-allocate VUs to avoid k6 internal initialization lag
      maxVUs: 500,                   // Upper limit safety buffer for extreme traffic spikes
      stages: [
        // --- CYCLE 1: FIRST TRAFFIC PEAK ---
        { target: 500, duration: '1m' },  // Ramp-up: Rapid load increase to induce stress
        { target: 500, duration: '3m' },  // Peak Hold: Maintain maximum load to observe system saturation
        { target: 0, duration: '1m' },  // Ramp-down: Traffic drops sharply

        // --- STABILIZATION WINDOW (CRITICAL FOR DEFAULT HPA) ---
        { target: 0, duration: '6m' },  // Sustained Low Load: Kept > 5 minutes to force K8s default HPA to scale down to minReplicas

        // --- CYCLE 2: SECOND TRAFFIC PEAK (THE ULTIMATE TEST) ---
        { target: 500, duration: '1m' },  // Sudden Spike: Sudden traffic resurgence to evaluate scaling responsiveness
        { target: 500, duration: '3m' },  // Peak Hold 2: Maintain state for data collection
        { target: 0, duration: '1m' },  // Final Ramp-down
      ],
    },
  },
};

export default function () {
  // IP of the targeted nginx
  http.get('http://34.55.189.54');
  sleep(1); 
}