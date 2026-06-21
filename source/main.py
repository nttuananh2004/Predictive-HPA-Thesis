import os
import time
import numpy as np
import joblib
from tensorflow.keras.models import load_model
from dotenv import load_dotenv
from datadog_api_client import Configuration, ApiClient
from datadog_api_client.v1.api.metrics_api import MetricsApi
from datadog_api_client.v1.model.series import Series
from datadog_api_client.v1.model.point import Point

# 1. Load environment variables for local testing
load_dotenv()

# 2. Initialize Datadog API configuration using environment variables
configuration = Configuration()
configuration.api_key['apiKeyAuth'] = os.environ.get("DD_API_KEY")
configuration.api_key['appKeyAuth'] = os.environ.get("DD_APP_KEY")
configuration.server_variables['site'] = os.environ.get("DD_SITE", "us5.datadoghq.com")

# 3. Dynamically resolve paths for the model and scaler
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, '..', 'model')) 

MODEL_PATH = os.path.join(MODEL_DIR, 'predictive_model.h5')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')

print(f"[INIT] Resolved Model Path: {MODEL_PATH}")
print(f"[INIT] Resolved Scaler Path: {SCALER_PATH}")

# Load the trained LSTM model and data scaler
try:
    model = load_model(MODEL_PATH, compile=False)
    scaler = joblib.load(SCALER_PATH)
    print("[INFO] Model and scaler loaded successfully.")
except Exception as e:
    print(f"[ERROR] Failed to load model/scaler: {e}")
    model, scaler = None, None

def fetch_real_traffic_from_datadog():
    """Fetches the last 10 minutes of aggregated CPU usage data from Datadog."""
    query = "avg:kubernetes.cpu.usage.total{kube_deployment:nginx-web}.rollup(avg, 60)"
    now = int(time.time())
    start_time = now - (10 * 60) 
    
    try:
        with ApiClient(configuration) as api_client:
            api_instance = MetricsApi(api_client)
            response = api_instance.query_metrics(_from=start_time, to=now, query=query)
            
            if not response.series or not response.series[0].pointlist:
                return []
            
            # BULLETPROOF FIX: Safely parse Datadog SDK point format
            values = []
            for p in response.series[0].pointlist:
                try:
                    val = p.value if hasattr(p, 'value') else p[1]
                    if isinstance(val, (list, tuple)):
                        val = val[1]
                    values.append(float(val))
                except Exception:
                    continue
            return values
    except Exception as e:
        print(f"[ERROR] Datadog Fetch Error: {e}")
        return []

def get_prediction():
    """Performs inference using the LSTM model with fallback handling for cold starts."""
    if model is None or scaler is None:
        return 0.0
        
    recent_traffic = fetch_real_traffic_from_datadog()
    
    # --- COLD START HANDLING ---
    if len(recent_traffic) < 10:
        print(f"[COLD START] Accumulating data ({len(recent_traffic)}/10 points). Running in Reactive mode.")
        return recent_traffic[-1] if len(recent_traffic) > 0 else 0.0
    
    # --- PREDICTIVE MODE ---
    print("[PREDICTIVE MODE] Sufficient data collected. Forecasting future traffic...")
    input_data = np.array(recent_traffic[-10:]).reshape(1, 10, 1)
    scaled_pred = model.predict(input_data, verbose=0)
    real_value = scaler.inverse_transform(scaled_pred)
    
    # Apply a 20% safety buffer for proactive capacity scaling
    final_prediction = float(real_value[0][0]) * 1.2 
    return final_prediction

# 4. Main execution loop
if __name__ == "__main__":
    print("[START] Predictive Autoscaler Bot initialized.")
    with ApiClient(configuration) as api_client:
        api_instance = MetricsApi(api_client)
        
        while True:
            try:
                pred_val = get_prediction()
                print(f"[INFO] Pushing predicted traffic metric: {pred_val:.4f}")
                
                # Submit the predicted metric back to Datadog for HPA consumption
                series = Series(
                    metric="k8s.app.predicted_traffic",
                    type="gauge",
                    points=[Point([int(time.time()), pred_val])],
                    tags=["kube_deployment:nginx-web"]
                )
                api_instance.submit_metrics(body={"series": [series]})
                
            except Exception as e:
                print(f"[ERROR] Main loop exception: {e}")
            
            # Polling interval: wait 10 seconds before fetching the next data point
            time.sleep(10)