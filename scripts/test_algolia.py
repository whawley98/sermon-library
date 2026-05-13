import requests
r = requests.post("https://a4149apl2c.algolia.net/1/indexes/sermons", headers={"X-Algolia-Application-Id":"A4149APL2C","X-Algolia-API-Key":"3c79ff84634df740423519749e1c94a8","Content-Type":"application/json"}, json={"objectID":"test_001","title":"Test"})
print(r.status_code, r.text)