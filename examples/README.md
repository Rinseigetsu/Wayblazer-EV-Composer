# Example Output

This directory contains **no game artwork** (all rights remain with the rights holders).

After running the composer, output lands in `EV_output/` inside the game directory, named:

```
EV<id>_diff<recipe>_g<variant>.png
```

| Field | Meaning | Example |
|---|---|---|
| `EV<id>` | Event CG id | `EV126` |
| `diff<recipe>` | Which differential recipe of that event | `diff2` |
| `g<variant>` | Which parallel layer set within that recipe | `g0` |

For example:

```
EV126_diff1_g0.png    base + a single differential
EV126_diff2_g0.png    base + EV126_ABA + EV126_ABB   (expression variant A)
EV126_diff2_g1.png    base + EV126_ACA + EV126_ABB   (expression variant B)
EV126_diff3_g0.png    a different differential recipe
```

A typical full run:

```
python ev_compose.py --all
# -> 138 events / 1092 finished images, roughly 2 GB
```

To build your own examples, run this tool against **a copy of the game you own** and
respect the disclaimer in the repository README.
