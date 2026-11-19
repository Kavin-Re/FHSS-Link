o = J("b21_maxent")
if o:
    rw = o["rows"]; P, Pn, Pu = rw["max-entropy (Parry)"], rw["naive redraw"], rw["max-entropy, uniform occupancy"]
    check("B21 Parry entropy rate equals log2 of Perron eigenvalue (1e-6)", abs(P["H"] - o["log2_lambda"]) < 1e-6)
    check("B21 brute-force sequence-count growth matches eigenvalue (1e-3), small M=7 D=2", abs(o["brute_growth"] - o["eig_growth"]) < 1e-3, f'{o["brute_growth"]:.4f}')
    check("B21 ordering naive <= Parry <= log2(#allowed)", Pn["H"] <= P["H"] + 1e-9 and P["H"] < o["bound"])
    check("B21 uniform-occupancy chain is no better than Parry but has occupancy ratio ~1", Pu["H"] <= P["H"] + 1e-9 and Pu["occ_ratio"] < 1.01)
    check("B21 all transition rows sum to 1", max(v["rowsum_err"] for v in rw.values()) < 1e-9)
    check("B21 measured attacker accuracy within 0.003 of sum_i pi_i max_j P_ij", all(abs(v["pred_meas"][0] - v["pred_theory"]) < 0.003 for v in rw.values()))
    sw = o["sweep"]; ds = sorted(map(int, sw))
    check("B21 entropy falls monotonically as guard separation D grows", all(sw[str(a)]["parry"] >= sw[str(b)]["parry"] for a, b in zip(ds, ds[1:])))
    check("B21 Parry occupancy is non-uniform at D=10 (ratio>2): a regulatory uniform-use rule costs entropy", sw["10"]["occ_ratio"] > 2 and sw["10"]["uniform"] < sw["10"]["parry"])
    check("B21 >=20 seeds", o["nseeds"] >= 20)
