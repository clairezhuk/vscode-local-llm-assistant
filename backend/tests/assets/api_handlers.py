import time

def process_request(data):
    start = time.time()
    time.sleep(0.1)
    print(f"Request processed: {data}")
    end = time.time()
    print(f"Execution time: {end - start}s")

def fetch_user_profile(user_id):
    start = time.time()
    time.sleep(0.05)
    print(f"User {user_id} fetched")
    end = time.time()
    print(f"Execution time: {end - start}s")