"""SeamCut: builds promos BACKWARD from cliffhanger cut points, adds a short setup segment when the clip would not stand alone,
and orders the final list with a diversity rule so the top picks cover different plot beats.
Usage: python seamcut.py "<folder of episode-*.txt>" --tag run [--top 15]
No model required. Output: raw_outputs/<tag>.md/.json/.csv and <tag>_metrics.md"""
import re, sys, os, glob, json, csv, random
STOPW = set("the a an and or but of to in on at for with is are was were be been it its this that his her their he she they you your i we my our me him them not no do does did have has had will would can could as by from so if then than who what why how when where which there here just only very".split())
def toks(s): return {w for w in re.findall(r"[a-z']+", s.lower()) if len(w) > 3 and w not in STOPW}
def tsec(mm, ss): return int(mm) * 60 + float(ss)

# ---------- parse: split into labelled chunks ----------
def parse(path):
    t = open(path, encoding="utf-8").read(); ev = []
    for ch in re.split(r"\n(?=\*\*[^\n]+:\*\*\n)", t):
        h = re.match(r"\*\*([^\n]+):\*\*\nStart: \((\d+):([\d.]+)\) \| End: \((\d+):([\d.]+)\)\n?(.*)", ch, re.S)
        if not h: continue
        base = re.sub(r"\s*\(.*\)", "", h[1]).strip(); emo = (re.search(r"\((.*)\)", h[1]) or [0, ""])[1]
        body = re.split(r"\n\n(?:SCENE|---)", h[6])[0].strip().strip('"')
        ev.append(dict(s=tsec(h[2], h[3]), e=tsec(h[4], h[5]), kind={"CAMERA": "camera", "ACTION": "action", "SOUND FX": "sfx"}.get(base, "dialogue"), who=base, emo=emo, text=body))
    ev.sort(key=lambda x: (x["s"], x["e"]))
    return dict(ep=int(re.search(r"EPISODE NUMBER:\s*Episode\s*(\d+)", t)[1]), logline=re.search(r"EPISODE LOGLINE:\s*(.*)", t)[1], ev=ev,
                scene_ends=[tsec(a, b) for a, b in re.findall(r"Scene end: (\d+):([\d.]+)", t)], end=max(x["e"] for x in ev))

# ---------- word lists ----------
UNRESOLVED_SHOCK = r"\b(?:dead|dies|died|alive|kill\w*|murder\w*|poison\w*|traitor|betray\w*|secret|truth|lie[sd]?|liar|pregnan\w*|baby|child|arrest\w*|dungeon|prison|banish\w*|disown\w*|blackmail\w*|confess\w*|witness\w*|caught|scandal\w*|forbidden|identity|ring|heir|proof|evidence|duke|vow|curse\w*)\b"
REVEAL_ACT = r"\b(?:reveal\w*|discover\w*|realiz\w*|gasp\w*|freez\w*|frozen|stunned|disbelief|horrif\w*|appears|steps out|enters|bursts?|storms?|draws? (?:a )?(?:sword|dagger|blade)|collaps\w*|faints?)\b"
SFX_CUE = r"cliffhanger|ominous|sting|swell|cut to black|abrupt|sudden silence"
CLOSURE = r"\b(?:thank you|at last|finally|farewell|goodbye|all is well|happily|i forgive you|it is over|it's over)\b"
CONFLICT_ACT = r"\b(?:slap\w*|strik\w*|shov\w*|grab\w*|snatch\w*|throws?|thrown|point\w* (?:at|a)|drag\w*|seiz\w*|restrain\w*|punch\w*|stab\w*|kneel\w*|spits?)\b"
ADDRESS = r"^(you|your|how dare|who|why|what|where|get |stop|do not|don't|listen|look|tell me|say it|answer|enough|guards?|release|take)\b"
RESPONSE = r"^(and|but|so|then|yes|no|well|because|that|it|he|she|they|him|her|okay|oh)\b"
RELATION = r"\b(?:husband|wife|fianc\w*|mother|father|sister|brother|marri\w*|wed\w*|betroth\w*|duke|duchess|lord|lady|soldier|maid|heir|family)\b"
def txt(evs, kinds=("dialogue", "action")): return " ".join(x["text"] for x in evs if x["kind"] in kinds)

# ---------- 1. cut points: where could a promo END? ----------
def cut_points(ep, mid_scene=True):
    hard = {round(c, 1) for c in ep["scene_ends"] + [ep["end"]]}
    cuts = sorted(hard | ({round(x["e"], 1) for x in ep["ev"] if x["kind"] == "dialogue" and x["e"] >= 20} if mid_scene else set())); out = []
    for c in cuts:
        tail = [x for x in ep["ev"] if x["e"] > c - 6 and x["s"] < c]; why = []; u = 0
        dl = [x for x in tail if x["kind"] == "dialogue"]
        if dl and re.search(r"(\?|--|…|\.\.\.|!)[\"']?$", dl[-1]["text"]): u += 2; why.append("last line is a question/interrupt/exclamation")
        sh = set(w.lower() for w in re.findall(UNRESOLVED_SHOCK, txt(tail), re.I))
        if sh: u += min(2, len(sh)); why.append("unresolved-stakes words: " + ", ".join(sorted(sh)[:3]))
        if re.search(REVEAL_ACT, txt(tail, ("action",)), re.I): u += 1; why.append("reveal/reaction action")
        if re.search(SFX_CUE, txt(tail, ("sfx",)) + " " + txt(tail, ("camera",)), re.I): u += 1; why.append("cut/sting cue")
        if dl and re.search(CLOSURE, dl[-1]["text"], re.I): u -= 3; why.append("closure wording")
        need = 2 if c in hard else 3          # a mid-scene cut must be clearly unresolved
        if u >= need: out.append(dict(cut=c, u=u, why=why, last=(dl[-1]["text"] if dl else (tail[-1]["text"] if tail else ""))))
    return out

# ---------- 2. hook start, searched BACKWARD from the cut ----------
def hook_at(ep, s0):
    first = [x for x in ep["ev"] if x["e"] > s0 and x["s"] < s0 + 3]; why = []; h = 0
    d = next((x for x in first if x["kind"] == "dialogue"), None)
    if d:
        h += 1
        if re.search(ADDRESS, d["text"], re.I): h += 1; why.append("direct address/command/question")
        if re.search(r"[?!]|--|…", d["text"]): h += 1; why.append("punchy delivery")
        if len(d["text"].split()) <= 3: h -= 1; why.append("fragment")
        if re.search(RESPONSE, d["text"], re.I): h -= 1; why.append("leans on a previous line")
        if re.search(r"furious|shock|scream|menac|cold|command|sobb|desperate|cruel|accus|panic|seeth|rage|defian", d["emo"], re.I): h += 1; why.append("intense delivery")
    if re.search(CONFLICT_ACT, txt(first, ("action", "camera")), re.I): h += 2; why.append("physical conflict in first 3s")
    if d and re.search(UNRESOLVED_SHOCK, d["text"], re.I): h += 1; why.append("shock word in opening line")
    return h, why, (d["text"] if d else (first[0]["text"] if first else ""))
def standalone_ok(ep, s0):
    d = next((x for x in ep["ev"] if x["kind"] == "dialogue" and x["e"] > s0), None)
    return bool(d) and len(d["text"].split()) >= 5 and not re.search(RESPONSE, d["text"], re.I) and not re.search(r"\b(this|that) (house|place|man|woman|thing)\b", d["text"], re.I)

# ---------- 3. setup segment: short earlier beat that explains who/what ----------
def setup_for(ep, s0, room):
    lg = toks(ep["logline"]); best = None
    starts = [x for x in ep["ev"] if x["kind"] == "dialogue" and x["e"] <= s0 - 1 and len(x["text"].split()) >= 5]
    for d in starts:
        a, b = d["s"], min(d["e"] + 2, s0 - 0.5)
        if not 3 <= b - a <= min(10, room): continue
        t = txt([x for x in ep["ev"] if x["e"] > a and x["s"] < b]); sc = len(toks(t) & lg) + 2 * bool(re.search(RELATION, t, re.I))
        if sc > 0 and (best is None or sc > best[0]): best = (sc, round(a, 1), round(b, 1), d["text"])
    return best

def build(ep):
    out = []
    for cp in cut_points(ep):
        c = cp["cut"]; cands = []
        for s0 in sorted({x["s"] for x in ep["ev"] if x["kind"] in ("dialogue", "action")}):
            if 16 <= c - s0 <= 52: h, hw, hl = hook_at(ep, s0); cands.append((h, -abs((c - s0) - 34), s0, hw, hl))
        if not cands: continue
        h, _, s0, hw, hl = max(cands); main = (round(s0, 1), round(c, 1)); segs = [main]; setup = None; sa = standalone_ok(ep, s0)
        if not sa and s0 > 10:
            setup = setup_for(ep, s0, 60 - (c - s0))
            if setup:
                segs = [(setup[1], setup[2]), main]
                if main[0] - setup[2] < 2.0: segs = [(setup[1], main[1])]; setup = None   # adjacent beats: merge into one continuous clip
        h, hw, hl = hook_at(ep, segs[0][0])   # the promo's real first 3 seconds (matters when a setup beat is placed first)
        total_dur = sum(b - a for a, b in segs)
        if not 20 <= total_dur <= 60: continue
        t = txt([x for x in ep["ev"] if any(x["e"] > a and x["s"] < b for a, b in segs)]); cov = len(toks(t) & toks(ep["logline"])) / max(1, len(toks(ep["logline"])))
        score = round(1.5 * cp["u"] + 1.5 * h + (1 if (sa or setup) else -1) + 4 * cov, 2)
        out.append(dict(ep=ep["ep"], segments=[list(s) for s in segs], dur=round(total_dur, 1), score=score, hook=hl[:140], cliff=cp["last"][:140], u=cp["u"], h=h, setup=bool(setup), coverage=round(cov, 2),
                        why="; ".join(hw[:2] + cp["why"][:2] + (["setup beat added so a new viewer knows who is who"] if setup else []))))
    return out

# ---------- 4. diversity-aware ordering ----------
def mmr(promos, eps, k, lam=0.7):
    lg = {e["ep"]: toks(e["logline"]) for e in eps}; mx = max(p["score"] for p in promos); left = list(promos); chosen = []
    sim = lambda a, b: (0.5 if a["ep"] == b["ep"] else 0) + 0.5 * len(lg[a["ep"]] & lg[b["ep"]]) / max(1, len(lg[a["ep"]] | lg[b["ep"]]))
    while left and len(chosen) < k:
        best = max(left, key=lambda p: lam * p["score"] / mx - (1 - lam) * max([sim(p, c) for c in chosen] or [0])); chosen.append(best); left.remove(best)
    return chosen
def fmt(t): return f"{int(t // 60):02d}:{t % 60:04.1f}"
def main():
    a = sys.argv; arg = lambda k, d: a[a.index(k) + 1] if k in a else d; tag = arg("--tag", "run"); top = int(arg("--top", 15))
    eps = [parse(p) for p in sorted(glob.glob(os.path.join(a[1], "episode-*.txt")))]; allp = []
    for ep in eps:
        ps = sorted(build(ep), key=lambda p: -p["score"]); kept = []
        for p in ps:
            if all(p["segments"][-1][1] <= q["segments"][-1][0] or p["segments"][-1][0] >= q["segments"][-1][1] for q in kept): kept.append(p)
            if len(kept) == 2: break
        allp += kept
    for i, p in enumerate(sorted(allp, key=lambda p: -p["score"]), 1): p["score_rank"] = i
    order = mmr(allp, eps, top)
    for i, p in enumerate(order, 1): p["post_order"] = i
    json.dump(allp, open(f"raw_outputs/{tag}.json", "w"), indent=1)
    with open(f"raw_outputs/{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["score_rank", "post_order", "episode", "segments", "total_s", "score", "hook", "cliffhanger", "why"])
        for p in sorted(allp, key=lambda p: p["score_rank"]): w.writerow([p["score_rank"], p.get("post_order", ""), p["ep"], " + ".join(f"{fmt(x)}-{fmt(y)}" for x, y in p["segments"]), p["dur"], p["score"], p["hook"], p["cliff"], p["why"]])
    md = [f"# SeamCut results ({tag})", f"{len(eps)} episodes -> {len(allp)} promos ({sum(p['setup'] for p in allp)} with a setup segment). **Post order (diversity-aware, top {top}):**\n"]
    for p in order: md.append(f"{p['post_order']}. **Ep {p['ep']}: " + " + ".join(f"{fmt(x)}-{fmt(y)}" for x, y in p["segments"]) + f"** ({p['dur']:.0f}s, score {p['score']}, score-rank {p['score_rank']})\n   - Hook: {p['hook']}\n   - Cliffhanger: {p['cliff']}\n   - Why: {p['why']}")
    open(f"raw_outputs/{tag}.md", "w", encoding="utf-8").write("\n".join(md))
    # ---- metrics: story coverage vs naive baselines (no human labels needed) ----
    random.seed(0); rnd = []; last = []
    for ep in eps:
        L = toks(ep["logline"])
        if not L: continue
        for _ in range(50):
            s0 = random.uniform(0, max(0.1, ep["end"] - 40)); rnd.append(len(toks(txt([x for x in ep["ev"] if x["e"] > s0 and x["s"] < s0 + 40])) & L) / len(L))
        last.append(len(toks(txt([x for x in ep["ev"] if x["e"] > ep["end"] - 40])) & L) / len(L))
    m = lambda v: sum(v) / len(v)
    ok = sum(20 <= p["dur"] <= 60 for p in allp)
    open(f"raw_outputs/{tag}_metrics.md", "w").write(f"# Metrics ({tag})\n- Promos: {len(allp)}; total duration within 20-60s: {ok}/{len(allp)}; with setup segment: {sum(p['setup'] for p in allp)}; per-episode count: 2 for {sum(1 for e in eps if sum(p['ep']==e['ep'] for p in allp)==2)} episodes\n- Share of the episode's logline words found in the promo (story coverage): SeamCut {m([p['coverage'] for p in allp]):.2f} vs random 40s window {m(rnd):.2f} vs last-40s {m(last):.2f}\n- Distinct episodes in the top {top} post order: {len({p['ep'] for p in order})}/{top}\n- Top {top} by score alone cover {len({p['ep'] for p in sorted(allp, key=lambda p: p['score_rank'])[:top]})} distinct episodes\n")
    print(open(f"raw_outputs/{tag}_metrics.md").read())
if __name__ == "__main__": main()
