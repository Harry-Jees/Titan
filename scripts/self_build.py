# Bounded model-assisted code improvement. Never executes model-generated shell commands.
import json, os, re, subprocess, sys, urllib.request

BASE = os.environ.get("TITAN_API_BASE", "").rstrip("/")
KEY = os.environ.get("TITAN_API_KEY", "")
MODEL = os.environ.get("TITAN_MODEL", "")
TASK = os.environ.get("TITAN_TASK", "").strip()
MAX = max(1, min(3, int(os.environ.get("TITAN_MAX_ITERATIONS", "3"))))
ALLOWED = ("src/", "tests/", "README.md", "docs/")
FORBIDDEN = (".github/", "package.json", "package-lock.json", "wrangler.toml", "migrations/", ".env")

def run(cmd):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

def ask(messages):
    if not (BASE and KEY and MODEL):
        raise RuntimeError("Configure TITAN_API_BASE, TITAN_API_KEY and TITAN_MODEL repository secrets.")
    req = urllib.request.Request(BASE + "/chat/completions",
        data=json.dumps({"model":MODEL,"messages":messages,"temperature":0.1}).encode(),
        headers={"Content-Type":"application/json","Authorization":"Bearer "+KEY}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read())["choices"][0]["message"]["content"]

def patch_from(text):
    m = re.search(r"```diff\s*(.*?)```", text, re.S)
    if m: return m.group(1).strip() + "\n"
    if text.lstrip().startswith("diff --git "): return text.strip() + "\n"
    raise RuntimeError("Model did not return a unified diff in a diff code block.")

def validate(patch):
    if len(patch.encode("utf-8")) > 100_000:
        raise RuntimeError("Patch exceeds the 100 KB limit.")
    if "GIT binary patch" in patch or "new file mode 120000" in patch or "old mode 120000" in patch:
        raise RuntimeError("Binary and symlink changes are not allowed.")
    if "deleted file mode" in patch or "+++ /dev/null" in patch:
        raise RuntimeError("File deletion is not allowed in a self-build patch.")
    secret_patterns = [
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"(?i)\b(?:gh[pousr]_|sk-)[A-Za-z0-9]{20,}\b",
        r"(?i)api[_ -]?key\s*[:=]\s*\S{20,}",
    ]
    if any(re.search(pattern, patch) for pattern in secret_patterns):
        raise RuntimeError("Patch contains a secret-shaped value; refusing it.")

    paths = []
    for line in patch.splitlines():
        if line.startswith(("+++ b/", "--- a/")):
            path = line[6:]
            if path != "/dev/null":
                paths.append(path)
        elif line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            paths.append(line.split(" ", 2)[2])
    if not paths:
        raise RuntimeError("No patch paths found.")
    if len(set(paths)) > 12:
        raise RuntimeError("Patch touches more than 12 files; split the task into smaller PRs.")
    for path in paths:
        if path.startswith("/") or "\\" in path or ".." in path.split("/") or path.startswith(FORBIDDEN):
            raise RuntimeError("Forbidden patch path: " + path)
        if not (path == "README.md" or path.startswith(("src/", "tests/", "docs/"))):
            raise RuntimeError("Path outside allowed source/docs: " + path)

def main():
    if not TASK: sys.exit("TITAN_TASK is required.")
    if len(TASK) > 2000: sys.exit("TITAN_TASK must be at most 2,000 characters.")
    if run(["git","status","--porcelain"]).stdout.strip(): sys.exit("Working tree must be clean.")
    names = run(["git","ls-files","src","tests","README.md","docs"]).stdout.splitlines()[:80]
    context = []
    for name in names:
        if os.path.isfile(name):
            try:
                with open(name, encoding="utf-8") as f: context.append("\n--- "+name+" ---\n"+f.read()[:7000])
            except OSError: pass
    system = ("Act as a senior software engineer. Return ONLY a complete unified git diff in a diff block. "
      "Patch only src/, tests/, README.md, or docs/. Never edit workflows, dependencies, secrets, deployment config, "
      "or migrations. Never add credential access, exfiltration, destructive behavior, or hidden behavior.")
    messages = [{"role":"system","content":system},
      {"role":"user","content":"TASK:\n"+TASK+"\nREPOSITORY CONTEXT:\n"+"\n".join(context)}]
    for _ in range(MAX):
        answer = ask(messages); patch = patch_from(answer); validate(patch)
        check = subprocess.run(["git","apply","--check","-"],input=patch,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if check.returncode:
            messages += [{"role":"assistant","content":answer},{"role":"user","content":"Patch check failed:\n"+check.stdout+"Return a corrected complete diff only."}]
            continue
        applied = subprocess.run(["git","apply","--index","-"],input=patch,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if applied.returncode:
            messages += [{"role":"assistant","content":answer},{"role":"user","content":"Patch application failed:\n"+applied.stdout+"Return a corrected complete diff only."}]
            continue
        checks = run(["npm","run","typecheck"])
        if checks.returncode == 0: checks = run(["npm","test"])
        if checks.returncode == 0:
            print("Patch passed checks."); print(run(["git","diff","--cached","--stat"]).stdout); return
        failure = checks.stdout[-10000:]
        subprocess.run(["git","reset","--hard","HEAD"],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        messages += [{"role":"assistant","content":answer},{"role":"user","content":"Checks failed:\n"+failure+"Repair the task and return a complete corrected diff only."}]
    sys.exit("Bounded repair attempts exhausted; no PR created.")

if __name__ == "__main__": main()
