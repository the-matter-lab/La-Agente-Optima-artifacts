from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401


def read_ids_csv(path: Path, field: str = 'hid') -> list[str]:
    with path.open(newline='') as f:
        return [row[field] for row in csv.DictReader(f)]


def ordered_full(stage1b_ids: list[str], full_raw_ids: list[str]) -> list[str]:
    rest = [x for x in full_raw_ids if x not in stage1b_ids]
    return list(stage1b_ids) + rest


def norm(i: int, n: int) -> float:
    return 0.0 if n <= 1 else i / (n - 1)


def draw_box(ax, xmax: float, ymax: float, zmax: float, color: str, lw: float, alpha: float = 1.0, label: str | None = None) -> None:
    corners = [
        (0, 0, 0), (xmax, 0, 0), (xmax, ymax, 0), (0, ymax, 0),
        (0, 0, zmax), (xmax, 0, zmax), (xmax, ymax, zmax), (0, ymax, zmax),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    for i, j in edges:
        ax.plot(
            [corners[i][0], corners[j][0]],
            [corners[i][1], corners[j][1]],
            [corners[i][2], corners[j][2]],
            color=color,
            lw=lw,
            alpha=alpha,
        )
    if label:
        ax.plot([], [], [], color=color, lw=lw, label=label)


def main() -> None:
    base_old = Path('artifacts/digital_osl_stage1/20260703T021037Z_preview')
    base_mid = Path('artifacts/digital_osl_stage1b/20260703T140530Z_execute')
    out_png = base_mid / 'search_space_cube_theoretical_vs_stage1_vs_stage1b_numeric_ticks.png'
    out_json = base_mid / 'search_space_cube_theoretical_vs_stage1_vs_stage1b_numeric_ticks.json'

    full_caps_raw = read_ids_csv(Path('adk9227_data_s1.csv'))
    full_bridges_raw = read_ids_csv(Path('adk9227_data_s2.csv'))
    full_cores_raw = read_ids_csv(Path('adk9227_data_s3.csv'))

    stage1_caps = read_ids_csv(base_old / 'active_caps.csv')
    stage1_bridges = read_ids_csv(base_old / 'active_bridges.csv')
    stage1_cores = read_ids_csv(base_old / 'active_cores.csv')

    stage1b_caps = read_ids_csv(base_mid / 'active_caps.csv')
    stage1b_bridges = read_ids_csv(base_mid / 'active_bridges.csv')
    stage1b_cores = read_ids_csv(base_mid / 'active_cores.csv')

    full_caps = ordered_full(stage1b_caps, full_caps_raw)
    full_bridges = ordered_full(stage1b_bridges, full_bridges_raw)
    full_cores = ordered_full(stage1b_cores, full_cores_raw)

    cap_idx = {hid: i for i, hid in enumerate(full_caps)}
    bridge_idx = {hid: i for i, hid in enumerate(full_bridges)}
    core_idx = {hid: i for i, hid in enumerate(full_cores)}

    # Coarse schematic points for the full theoretical space.
    cap_sample = list(range(0, len(full_caps), 2))
    if cap_sample[-1] != len(full_caps) - 1:
        cap_sample.append(len(full_caps) - 1)
    bridge_sample = list(range(0, len(full_bridges), 3))
    if bridge_sample[-1] != len(full_bridges) - 1:
        bridge_sample.append(len(full_bridges) - 1)
    core_sample = list(range(0, len(full_cores), 6))
    if core_sample[-1] != len(full_cores) - 1:
        core_sample.append(len(full_cores) - 1)

    full_pts = [
        (norm(i, len(full_caps)), norm(j, len(full_bridges)), norm(k, len(full_cores)))
        for i in cap_sample
        for j in bridge_sample
        for k in core_sample
    ]
    stage1b_pts = [
        (norm(cap_idx[a], len(full_caps)), norm(bridge_idx[b], len(full_bridges)), norm(core_idx[c], len(full_cores)))
        for a, b, c in itertools.product(stage1b_caps, stage1b_bridges, stage1b_cores)
    ]
    stage1_pts = [
        (norm(cap_idx[a], len(full_caps)), norm(bridge_idx[b], len(full_bridges)), norm(core_idx[c], len(full_cores)))
        for a, b, c in itertools.product(stage1_caps, stage1_bridges, stage1_cores)
    ]

    fig = plt.figure(figsize=(10.2, 8.2), dpi=180)
    ax = fig.add_subplot(111, projection='3d')
    ax.set_proj_type('ortho')
    ax.set_box_aspect((1, 1, 1))

    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        try:
            axis.pane.fill = False
            axis.pane.set_edgecolor((0.85, 0.85, 0.85, 0.5))
        except Exception:
            pass

    fx, fy, fz = zip(*full_pts)
    ax.scatter(fx, fy, fz, s=4, c='#B0B0B0', alpha=0.10, depthshade=False, label='Theoretical full catalog space')

    mx, my, mz = zip(*stage1b_pts)
    ax.scatter(mx, my, mz, s=5, c='#F4A261', alpha=0.08, depthshade=False, label='Extended Stage 1b space')

    sx, sy, sz = zip(*stage1_pts)
    ax.scatter(sx, sy, sz, s=8, c='#4C78A8', alpha=0.28, depthshade=False, label='Initial Stage 1 space')

    stage1_box = (
        norm(len(stage1_caps) - 1, len(full_caps)),
        norm(len(stage1_bridges) - 1, len(full_bridges)),
        norm(len(stage1_cores) - 1, len(full_cores)),
    )
    stage1b_box = (
        norm(len(stage1b_caps) - 1, len(full_caps)),
        norm(len(stage1b_bridges) - 1, len(full_bridges)),
        norm(len(stage1b_cores) - 1, len(full_cores)),
    )

    draw_box(ax, 1, 1, 1, '#7A7A7A', 1.8, 0.95, f'Theoretical full catalog ({len(full_caps)}×{len(full_bridges)}×{len(full_cores)})')
    draw_box(ax, *stage1b_box, '#E76F51', 2.0, 0.95, f'Extended Stage 1b ({len(stage1b_caps)}×{len(stage1b_bridges)}×{len(stage1b_cores)})')
    draw_box(ax, *stage1_box, '#1D4E89', 2.2, 0.98, f'Initial Stage 1 ({len(stage1_caps)}×{len(stage1_bridges)}×{len(stage1_cores)})')

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_zlim(0, 1)
    ax.set_xlabel('Cap building block', labelpad=12)
    ax.set_ylabel('Bridge building block', labelpad=12)
    ax.set_zlabel('Core building block', labelpad=10)
    ax.set_title('Theoretical vs Stage 1b vs Stage 1 search spaces', pad=16)

    cap_ticks = [0, len(stage1_caps) - 1, len(stage1b_caps) - 1, len(full_caps) - 1]
    bridge_ticks = [0, len(stage1_bridges) - 1, len(stage1b_bridges) - 1, len(full_bridges) - 1]
    core_ticks = [0, len(stage1_cores) - 1, len(stage1b_cores) - 1, len(full_cores) - 1]

    ax.set_xticks([norm(t, len(full_caps)) for t in cap_ticks])
    ax.set_yticks([norm(t, len(full_bridges)) for t in bridge_ticks])
    ax.set_zticks([norm(t, len(full_cores)) for t in core_ticks])

    ax.set_xticklabels(['0\nstart', f'{cap_ticks[1]}\nStage 1 limit', f'{cap_ticks[2]}\nStage 1b limit', f'{cap_ticks[3]}\nfull limit'], fontsize=8)
    ax.set_yticklabels(['0\nstart', f'{bridge_ticks[1]}\nStage 1 limit', f'{bridge_ticks[2]}\nStage 1b limit', f'{bridge_ticks[3]}\nfull limit'], fontsize=8)
    ax.set_zticklabels(['0\nstart', f'{core_ticks[1]}\nStage 1 limit', f'{core_ticks[2]}\nStage 1b limit', f'{core_ticks[3]}\nfull limit'], fontsize=8)

    ax.grid(False)
    ax.view_init(elev=21, azim=-58)
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), borderaxespad=0.0)
    plt.subplots_adjust(right=0.77)
    fig.savefig(out_png, bbox_inches='tight')

    out_json.write_text(json.dumps({
        'figure': str(out_png),
        'full_catalog_counts': {'caps': len(full_caps), 'bridges': len(full_bridges), 'cores': len(full_cores)},
        'stage1_counts': {'caps': len(stage1_caps), 'bridges': len(stage1_bridges), 'cores': len(stage1_cores)},
        'stage1b_counts': {'caps': len(stage1b_caps), 'bridges': len(stage1b_bridges), 'cores': len(stage1b_cores)},
    }, indent=2))

    print(f'Wrote {out_png}')
    print(f'Wrote {out_json}')


if __name__ == '__main__':
    main()
