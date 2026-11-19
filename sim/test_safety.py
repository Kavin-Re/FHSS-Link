from safety import Guard
def check(n, c): print(("PASS " if c else "FAIL ") + n); assert c
K = b"owner-key"; g = Guard(K, allowed_channels={3, 4})
check("no token -> denied", g.request(0.0, 3, 0)[0] is False)
check("forged token rejected", g.accept_token(0.1, 1, b"12345678") is False)
c, tag = Guard.make_token(K, 1); check("valid token accepted", g.accept_token(0.2, c, tag))
check("replayed token rejected", g.accept_token(0.3, c, tag) is False)
check("allowed channel + low power allowed", g.request(0.4, 3, 0)[0])
check("foreign channel denied", g.request(0.5, 7, 0)[0] is False)
check("power above cap denied", g.request(0.6, 3, 2)[0] is False)
g2 = Guard(K, {3}); g2.accept_token(0.0, *Guard.make_token(K, 1))
allowed = sum(g2.request(0.1 * i, 3, 0)[0] for i in range(1, 51))   # asks to emit continuously for 5 s
check(f"duty cap: only {allowed} of 50 requests (0.1 s each) allowed in 5 s (limit 10%)", allowed <= 10 + 1)
g3 = Guard(K, {3}); g3.accept_token(0.0, *Guard.make_token(K, 1)); g3.kill(0.5)
check("kill switch blocks at once", g3.request(0.6, 3, 0)[0] is False)
g4 = Guard(K, {3}); g4.accept_token(0.0, *Guard.make_token(K, 1))
check("token expiry stops emission", g4.request(6.0, 3, 0)[0] is False)
print("ALL PASSED")
