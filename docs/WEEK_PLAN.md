# Software-only week (7-13 Oct). Hardware untouched.
| Day | Build | You decide |
|---|---|---|
| Tue 6 (today, done) | schedule.py, attack.py, adaptive jammer result | - |
| Wed 7 | Light day (ICE test 10 am): daily log only | - |
| Thu 8 (DONE 6 Oct) | Adaptive channel selection: blacklist, then UCB/Thompson; compare against blind hopping under static, sweeping, follower jammers | which jammers matter for the demo |
| Fri 9 (DONE 6 Oct) | Defender vs learning jammer game (Q-learning jammer); arms-race plots | whether to keep or cut it |
| Sat 10 (DONE 6 Oct) | Dashboard v1 (web page, simulator-fed): waterfall + PDR + jammer label | look and feel |
| Sun 11 (DONE 6 Oct) | FEC: Hamming, then convolutional + Viterbi; goodput vs overhead | how deep to go |
| Mon 12 (DONE 6 Oct) | Jammer classifier + emulated device + serial format spec | - |
| Tue 13 | Integration, tests, RESULTS rewrite, one-page viva sheet draft | confirm spec decisions 1-5 |
Each day ends with a proposed commit message and diff summary; you approve and push.

Thu-Mon were all built on 6 Oct in one sitting at Kavin's request; run `./run_tests.sh`. The remaining days are for review, real-data checks and anything you want changed.
