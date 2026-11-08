# SeamCut - backward-built promos with setup beats and diversity-aware ordering (Problem 1)
Idea: start from where a promo should END (a cliffhanger cut), search BACKWARD for the best hook start, add a short earlier "setup" beat if the clip would not make sense alone (a 2-segment promo), then order the list so the top picks cover different plot beats.
Run (no key): python seamcut.py "<folder with episode-*.txt>" --tag run [--top 15]
Outputs in raw_outputs/: <tag>.md (post order with hook, cliffhanger, why), .csv, .json, <tag>_metrics.md
review_sheet.csv: fill in your own y/n verdicts for the top 15 after you watch/read them; that is the real quality score.
Word lists are at the top of seamcut.py. Limits: English keywords, lexical scoring, setup beats come from the same episode only (no cross-episode joins), 11 of 50 episodes get no promo.
The input pack is Kuku's confidential content: do not publish it. Only code and outputs (short lines) belong in your repo.
