"""Create the paired, two-seed result figure from the audited per-arm table."""

import csv
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
COLORS = {"1703": "#0a7467", "1709": "#75479b"}


def main():
    with (HERE / "results/metrics.tsv").open() as f:
        records = {
            (r["arm"], r["seed"]): r
            for r in csv.DictReader(f, delimiter="\t")
            if r["subset"] == "heldout_all" and r["split"] == "collision"
        }
    width, height = 1030, 350
    s = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><title>Single-row Bake holdout, second-run nonempty complete graphs</title><rect width="100%" height="100%" fill="#f5f8f7"/>'
    ]

    def text(x, y, label, size=15, color="#193443", weight=400, anchor="start"):
        s.append(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{color}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}">{escape(str(label))}</text>'
        )

    def line(x, y, xx, yy, color, width=1):
        s.append(
            f'<line x1="{x}" y1="{y}" x2="{xx}" y2="{yy}" stroke="{color}" stroke-width="{width}"/>'
        )

    text(24, 32, "SECOND RUN  /  COMPLETE NONEMPTY GRAPHS", 19, weight=700)
    for i, seed in enumerate(COLORS):
        x = 745 + 115 * i
        if i:
            s.append(f'<rect x="{x - 4}" y="20" width="9" height="9" fill="{COLORS[seed]}"/>')
        else:
            s.append(f'<circle cx="{x}" cy="25" r="5" fill="{COLORS[seed]}"/>')
        text(x + 12, 30, "seed " + seed, 14)
    mx = max(int(r["nonempty_complete_graphs"]) for r in records.values())
    axis = max(20, ((mx + 9) // 10) * 10)
    for left, w, title, arms, labels in [
        (
            14,
            414,
            "02   Rule-head sharing",
            ("private_roles", "shared_roles"),
            ("Private", "Shared"),
        ),
        (
            439,
            577,
            "01   Static template encoder",
            ("shared_id", "shared_roles", "shared_pooled", "shared_ports"),
            ("ID / UNK", "Roles", "Graph pool", "Per port"),
        ),
    ]:
        s.append(
            f'<rect x="{left}" y="46" width="{w}" height="272" rx="8" fill="white" stroke="#cad9da"/>'
        )
        text(left + 16, 74, title, 19, weight=700)
        for yv in (0, axis / 2, axis):
            y = 254 - 130 * yv / axis
            line(left + 44, y, left + w - 20, y, "#d6dfe1")
            text(left + 34, y + 4, f"{yv:g}", 12, anchor="end")
        for i, (arm, lab) in enumerate(zip(arms, labels)):
            x = left + 65 + (w - 108) * (i + 0.5) / len(arms)
            text(x, 281, lab, 14, anchor="middle")
            for seed, off in [("1703", -12), ("1709", 12)]:
                val = int(records[arm, seed]["nonempty_complete_graphs"])
                y = 254 - 130 * val / axis
                line(x + off, 254, x + off, y, COLORS[seed], 2)
                if seed == "1703":
                    s.append(f'<circle cx="{x + off}" cy="{y}" r="5" fill="{COLORS[seed]}"/>')
                else:
                    s.append(
                        f'<rect x="{x + off - 4.5}" y="{y - 4.5}" width="9" height="9" fill="{COLORS[seed]}"/>'
                    )
                text(x + off, y - 10, val, 13, COLORS[seed], 700, "middle")
    text(
        24,
        340,
        "448 nonempty graph instances per point  ·  224 counterfactual pairs  ·  two held-out composition families",
        14,
    )
    (HERE / "results/heads-and-encoders.svg").write_text("".join(s) + "</svg>\n")


if __name__ == "__main__":
    main()
