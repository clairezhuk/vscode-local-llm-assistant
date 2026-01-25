import requests

url = "http://127.0.0.1:8000/generate"

data = {
    "command": "Create a function to filter even numbers from a list",
    "context": "import numpy as np"
}

response = requests.post(url, json=data)
print(response.json()['response'])