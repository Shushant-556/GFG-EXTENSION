import re
def slugify(s):
    s=re.sub(r"[^a-zA-Z0-9]+","-",s.strip()).strip("-").lower()
    return s[:100] or "daily-problem"
def test_slug():
    assert slugify("Two Sum!")=="two-sum"
    assert slugify("!!!")=="daily-problem"
