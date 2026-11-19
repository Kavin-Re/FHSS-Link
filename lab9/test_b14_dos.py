o = J("b14_dos")
if o:
    a = o["assumptions"]; cap = a["F_CPU"] / a["C_MAC"]; r = o["res"]; ix = {R: i for i, R in enumerate(o["rates"])}
    R = 6400; cf = cap / (a["LAM_L"] + R)
    check("B14 undefended goodput at R=6400 equals closed form MAC-capacity share cap/(lam+R) within 0.03", abs(r["none/junk"][ix[R]]["good"][0] - cf) < 0.03, f'{r["none/junk"][ix[R]]["good"][0]:.3f} vs {cf:.3f}')
    check("B14 no collapse below capacity (R=800 goodput>0.99, util ~ (lam+R)*C/F within 0.05)", r["none/junk"][ix[800]]["good"][0] > 0.99 and abs(r["none/junk"][ix[800]]["util"][0] - (a["LAM_L"] + 800) * a["C_MAC"] / a["F_CPU"]) < 0.05)
    check("B14 structural filter stops random junk (R=6400 goodput>0.99) ...", r["struct/junk"][ix[R]]["good"][0] > 0.99)
    check("B14 ... but not well-formed forgeries (within 0.03 of undefended)", abs(r["struct/wellformed"][ix[R]]["good"][0] - r["none/junk"][ix[R]]["good"][0]) < 0.03)
    check("B14 16-bit pre-tag restores goodput >0.99 vs well-formed flood at 6400", r["struct+pretag/wellformed"][ix[R]]["good"][0] > 0.99)
    check("B14 pre-tag CPU load at 6400 < half of MAC-per-packet load, by cost ratio", r["struct+pretag/wellformed"][ix[R]]["util"][0] < 0.5)
    check("B14 >=20 seeds", o["nseeds"] >= 20)
