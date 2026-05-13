# paste into a quick test.py in scripts folder
import requests
headers = {
    "X-Algolia-Application-Id": "A4149APL2C",
    "X-Algolia-API-Key": "YOUR_ADMIN_KEY_HERE",
    "Content-Type": "application/json",
}
r = requests.post(
    "https://a4149apl2c.algolia.net/1/indexes/sermons/batch",
    headers=headers,
    json={"requests": [{"action": "addObject", "body": {"objectID": "test_001", "title": "Test"}}]},
    timeout=10
)
print(r.status_code, r.text[:200])