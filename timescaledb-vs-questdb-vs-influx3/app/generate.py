import math
import os
import random
from dataset import CSV, DEVICES, POINTS, SEED, START, STEP, STOP


def main():
    rng = random.Random(SEED)
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    names = [f"d{i:03d}" for i in range(DEVICES)]
    with open(CSV, "w") as f:
        f.write("device,ts,temperature,humidity\n")
        for ts in range(START, STOP, STEP):
            day = 2 * math.pi * (ts % 86400) / 86400
            lines = []
            for i, name in enumerate(names):
                temperature = round((15 + i % 20 * 0.5 + 5 * math.sin(day + i) + rng.uniform(-1, 1)) * 8) / 8
                humidity = round((40 + i % 30 + rng.uniform(-3, 3)) * 2) / 2
                lines.append(f"{name},{ts},{temperature!r},{humidity!r}\n")
            f.write("".join(lines))
    print(f"wrote {POINTS} readings for {DEVICES} devices to data/readings.csv")


if __name__ == "__main__":
    main()
