import requests

url = "http://www.streamvortex.com:11300/stream.pls"

response = requests.get(url)
if response.status_code == 200:
    content = response.text
    print("PLS File Content:\n", content)
else:
    print(f"Failed to fetch PLS file. Status code: {response.status_code}")
