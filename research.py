# Free research runner (GitHub Actions + GitHub Models free tier, auth = the job's own GITHUB_TOKEN; no stored keys).
# Reads topic.json: {"topic", "question", "queries": [repo search terms], "urls": [public pages]}.
# For each source: fetch public text -> ask the model for concrete, sourced techniques -> notes; then one synthesis.
import json, os, re, time, urllib.request, html
T = json.load(open("topic.json")); TOK = os.environ["GITHUB_TOKEN"]; MODEL = os.environ.get("MODEL", "openai/gpt-4o-mini")
H = {"Authorization": f"Bearer {TOK}", "User-Agent": "research-lab", "Accept": "application/vnd.github+json"}
def get(url, headers=None, n=200000):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 research-lab"}), timeout=25)
        return r.read(n).decode("utf-8", "ignore")
    except Exception as e: return ""
def text(h):
    h = re.sub(r"(?is)<(script|style|nav|footer|svg)[^>]*>.*?</\1>", " ", h); h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()
def ask(prompt, maxtok=900):
    body = json.dumps({"model": MODEL, "temperature": 0.2, "max_tokens": maxtok, "messages": [
        {"role": "system", "content": "You extract concrete, actionable, verifiable techniques from public sources. Bullet points, specific numbers/settings/names, no fluff, no invented facts. If the source has nothing relevant, answer NOTHING."},
        {"role": "user", "content": prompt}]}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request("https://models.github.ai/inference/chat/completions", data=body,
                                         headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=90))["choices"][0]["message"]["content"]
        except Exception as e:
            time.sleep(20 * (attempt + 1))
    return "(model unavailable)"
sources = []
for q in T.get("queries", []):
    s = get(f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort=stars&per_page=4", H)
    for it in (json.loads(s).get("items", []) if s else []):
        rd = get(f"https://api.github.com/repos/{it['full_name']}/readme", {**H, "Accept": "application/vnd.github.raw"})
        if rd: sources.append((f"https://github.com/{it['full_name']} ({it.get('license') and it['license'].get('spdx_id')}, {it['stargazers_count']}★)", rd))
for u in T.get("urls", []):
    t = text(get(u))
    if len(t) > 400: sources.append((u, t))
seen, notes = set(), []
for src, body in sources:
    if src in seen: continue
    seen.add(src)
    out = ask(f"Question: {T['question']}\n\nSource: {src}\n\n{body[:11000]}")
    if out.strip() and not out.strip().startswith("NOTHING"): notes.append(f"### {src}\n{out}\n")
    time.sleep(7)  # stay well under the free per-minute limit
syn = ask(f"Question: {T['question']}\n\nCombine these sourced notes into a practical playbook: numbered steps, exact settings, what to avoid, and which open-source tools (with licences) to use. Keep every claim tied to its source in brackets.\n\n" + "\n".join(notes)[:60000], 2500)
os.makedirs("out", exist_ok=True)
open("out/REPORT.md", "w").write(f"# {T['topic']}\n\nQuestion: {T['question']}\n\nSources read: {len(seen)} (public only). Model: {MODEL} via GitHub Models free tier.\n\n## Playbook\n\n{syn}\n\n## Notes per source\n\n" + "\n".join(notes))
print("sources", len(seen), "notes", len(notes))
