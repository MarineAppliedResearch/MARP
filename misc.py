import random
N = 10_00000
TP = 0
FP = 0
for _ in range(N):
    has_disease = (random.random() < 0.01)  # 1% prevalence
    if has_disease:
        if random.random() < 0.99:         # sensitivity 80%
            TP += 1
    else:
        if random.random() < 0.05:         # false positive 1%
            FP += 1
ppv = TP / (TP + FP)
print(ppv)  # ~0.50 (≈50%)