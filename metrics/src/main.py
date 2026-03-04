import time
from prometheus_client import start_http_server, Gauge

# Example Metric
DUMMY_METRIC = Gauge('gitweave_dummy_metric', 'A dummy metric for testing')

def main():
    print("Starting Metrics Observer...")
    # Start up the server to expose the metrics.
    start_http_server(8000)
    print("Metrics server running on port 8000")
    
    while True:
        DUMMY_METRIC.set_to_current_time()
        time.sleep(10)

if __name__ == '__main__':
    main()
