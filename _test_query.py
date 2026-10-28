import sys; sys.path.insert(0,'.')
import json, urllib.request

data = json.dumps({"question": "Quelles sont les conditions de capital minimum pour les banques ?"}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/chat",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=30) as resp:
    result = json.loads(resp.read())

print("=== REPONSE ===")
print("Type:", result["answer_type"])
print("Answer:", result["answer"][:300])
print("\n=== CITATIONS ===")
for i, cit in enumerate(result["citations"][:3], 1):
    ref = cit["citation"]
    print(f"[{i}] {ref.get('title','?')} | {ref.get('article','?')} | p.{ref.get('page','?')}")
    print(f"    Extrait: {cit['excerpt'][:100]}...")
print("\n=== WARNINGS ===")
for w in result["warnings"]:
    print(" -", w[:100])
print("\nMéthode:", result["search_method"])
print("Sources utilisées:", result["relevant_used"])
