"""Idea 25: adversarial test of the interference classifier. An evasive jammer switches on and off (duty cycle) to hide its pattern.
Classifier trained only on full-duty jammers (the model from classify.py) vs the same model trained with duty-cycle augmentation,
tested on windows of 150 and 600 slots. Also reports damage (loss rate) so the trade-off is visible: low duty = less harm."""
import numpy as np
from classify import CLASSES, sim_window, softmax_train, softmax_predict, rule

def make(n, off, duties, W=150):
    X, y, d = [], [], []
    for i in range(n):
        for ci, c in enumerate(CLASSES):
            du = duties[(i + ci) % len(duties)]
            X.append(sim_window(c, W=W, seed=off + i * 7 + ci, duty=du)); y.append(ci); d.append(du)
    return np.array(X), np.array(y), np.array(d)

if __name__ == "__main__":
    import json; res = {}
    Xa, ya, _ = make(120, 0, [1.0]); plain = softmax_train(Xa, ya, 5)
    Xb, yb, _ = make(120, 5000, [1.0, 0.5, 0.3, 0.15]); aug = softmax_train(Xb, yb, 5)
    print("accuracy by jammer duty cycle (rows) for the plain-trained and the augmentation-trained classifier; 150-slot windows; 5 classes")
    for du in (1.0, 0.5, 0.3, 0.15):
        X, y, _ = make(80, 10**6, [du]); r = {}
        r["plain"] = float((softmax_predict(plain, X) == y).mean()); r["augmented"] = float((softmax_predict(aug, X) == y).mean())
        r["mean_loss_rate_when_jammed"] = float(X[y > 0][:, 0].mean()); res[str(du)] = r
        print(f"duty {du:4.2f}: plain {r['plain']:.2f}  augmented {r['augmented']:.2f}  (loss rate caused {r['mean_loss_rate_when_jammed']:.3f})")
    X, y, _ = make(60, 2 * 10**6, [0.15], W=600); r = float((softmax_predict(aug, X) == y).mean()); print(f"duty 0.15, 600-slot windows, augmented classifier: {r:.2f}"); res["duty0.15_W600"] = r
    json.dump(res, open("figures/advclass.json", "w"), indent=1)
