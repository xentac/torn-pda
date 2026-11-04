# Appends a new pda_userScriptsList record to a sembast preferences file.
#   add_scripts.py DB EXPORT MODE   (MODE: user = the enabled start scripts as they are,
#   stress = the other enabled scripts as start scripts that match no Torn page)
# Custom keys and update URLs are removed. The last record of a key wins in sembast.
import base64, json, sys
db, export, mode = sys.argv[1:4]
lines = open(db).read().splitlines()
current = None
for l in lines[1:]:
    r = json.loads(l)
    if r.get("key") == "pda_userScriptsList" and r.get("store") == "app_preferences":
        current = r.get("value")
if current and current.startswith("PDA_B64:"):
    current = base64.b64decode(current[8:]).decode("utf-8")
scripts = json.loads(current) if current else []
have = {s["storageId"] for s in scripts}
added = 0
for s in json.load(open(export)):
    if not s.get("enabled") or s["storageId"] in have:
        continue
    is_start = s.get("time") == "start"
    if (mode == "user") != is_start:
        continue
    s = dict(s, customApiKey="", customApiKeyCandidate=False, url=None, updateUrl=None,
             updateStatus="noRemote", isExample=False, alwaysActive=False)
    if mode == "stress":
        s["time"] = "start"
        s["matches"] = ["https://pda-replay.invalid/never/*"]
        s["name"] = s["name"] + " (stress)"
    scripts.append(s)
    added += 1
lines.append(json.dumps({"key": "pda_userScriptsList", "store": "app_preferences", "value": "PDA_B64:" + base64.b64encode(json.dumps(scripts).encode("utf-8")).decode()}))
open(db, "w").write("\n".join(lines) + "\n")
print(f"{mode}: added {added}, now {len(scripts)} scripts")
