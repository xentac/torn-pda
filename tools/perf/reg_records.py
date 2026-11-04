# Joins the PDA-PERF-REG records of run folders and prints them per run, in order.
import json, re, sys
LINE = re.compile(r"\[PDA-PERF-REG\] (\d+) (\d+)/(\d+) (.*)$")
for d in sys.argv[1:]:
    parts = {}
    order = []
    for l in open(d + "/logcat.txt", errors="replace"):
        m = LINE.search(l.rstrip("\n"))
        if not m: continue
        i = m.group(1)
        if i not in parts: parts[i] = {}; order.append(i)
        parts[i][int(m.group(2))] = m.group(4)
    print("==", d.split("/")[-1])
    for i in order:
        r = json.loads("".join(parts[i][k] for k in sorted(parts[i])))
        per = r.pop("per", None)
        if per: r["per"] = " ".join(f"{b//1024}K:{ms}" for b, ms in per)
        print(" ", json.dumps(r))
