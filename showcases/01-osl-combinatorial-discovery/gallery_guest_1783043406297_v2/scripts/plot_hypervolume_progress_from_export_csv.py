from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def rect_union_area(rects: list[tuple[float, float, float, float]]) -> float:
    ys = sorted({y1 for y1, y2, z1, z2 in rects} | {y2 for y1, y2, z1, z2 in rects})
    area = 0.0
    for a, b in zip(ys[:-1], ys[1:]):
        z_intervals: list[tuple[float, float]] = []
        for y1, y2, z1, z2 in rects:
            if y1 < b and y2 > a:
                z_intervals.append((z1, z2))
        if not z_intervals:
            continue
        z_intervals.sort()
        cur_s, cur_e = z_intervals[0]
        covered = 0.0
        for s, e in z_intervals[1:]:
            if s <= cur_e:
                cur_e = max(cur_e, e)
            else:
                covered += cur_e - cur_s
                cur_s, cur_e = s, e
        covered += cur_e - cur_s
        area += (b - a) * covered
    return area


def hv3(points: list[tuple[float, float, float]], ref: tuple[float, float, float]) -> float:
    boxes = [(x, y, z) for x, y, z in points if x > ref[0] and y > ref[1] and z > ref[2]]
    if not boxes:
        return 0.0
    xcuts = sorted({ref[0]} | {x for x, _, _ in boxes})
    hv = 0.0
    for x0, x1 in zip(xcuts[:-1], xcuts[1:]):
        active = [(ref[1], y, ref[2], z) for x, y, z in boxes if x >= x1 and y > ref[1] and z > ref[2]]
        if active:
            hv += (x1 - x0) * rect_union_area(active)
    return hv


def margin(vals: list[float]) -> float:
    span = max(vals) - min(vals)
    return max(1e-9, 0.05 * span)


def load_rows(export_csv: Path) -> list[dict]:
    with export_csv.open(newline='') as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r['created_at'])
    pts = []
    for i, r in enumerate(rows, 1):
        bright = float(r['obj_bright_osc_strength'])
        color = float(r['obj_color_error_ev'])
        amb = float(r['obj_ambiguity_penalty'])
        candidate = f"{r['param_cap_id']}{r['param_bridge_id']}{r['param_core_id']}"
        phase = 'import' if not (r.get('suggestion_id') or '').strip() else 'bo'
        pts.append({
            'step': i,
            'candidate': candidate,
            'phase': phase,
            'created_at': r['created_at'],
            'raw': (bright, color, amb),
            'vec': (bright, -color, -amb),
        })
    return pts


def main() -> None:
    ap = argparse.ArgumentParser(description='Plot campaign-local hypervolume progress from a BO export CSV.')
    ap.add_argument('--export-csv', type=Path, required=True, help='CSV from bo_export_campaign or campaign_export.csv artifact.')
    ap.add_argument('--out-dir', type=Path, default=None, help='Output directory. Defaults to export CSV parent.')
    ap.add_argument('--title', type=str, default='Hypervolume improvement curve', help='Plot title.')
    ap.add_argument('--prefix', type=str, default='hypervolume_progress', help='Filename prefix for outputs.')
    args = ap.parse_args()

    pts = load_rows(args.export_csv)
    if not pts:
        raise SystemExit('No rows found in export CSV.')

    out_dir = args.out_dir or args.export_csv.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    progress_csv_path = out_dir / f'{args.prefix}.csv'
    plot_path = out_dir / f'{args.prefix}.png'
    summary_json_path = out_dir / f'{args.prefix}_summary.json'

    xs = [p['vec'][0] for p in pts]
    ys = [p['vec'][1] for p in pts]
    zs = [p['vec'][2] for p in pts]
    ref = (min(xs) - margin(xs), min(ys) - margin(ys), min(zs) - margin(zs))

    hvs: list[float] = []
    for k in range(1, len(pts) + 1):
        hvs.append(hv3([p['vec'] for p in pts[:k]], ref))
    inc = [hvs[0]] + [hvs[i] - hvs[i - 1] for i in range(1, len(hvs))]

    with progress_csv_path.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['step', 'candidate_id', 'phase', 'created_at', 'hypervolume', 'hv_improvement', 'bright_osc_strength', 'color_error_ev', 'ambiguity_penalty'])
        for p, hv, d in zip(pts, hvs, inc):
            w.writerow([p['step'], p['candidate'], p['phase'], p['created_at'], hv, d, *p['raw']])

    fig, ax1 = plt.subplots(figsize=(10, 5.5), dpi=160)
    steps = [p['step'] for p in pts]
    ax1.plot(steps, hvs, marker='o', linewidth=2, color='#1f77b4')
    ax1.set_xlabel('Observation index')
    ax1.set_ylabel('Hypervolume (campaign-local units)')
    if len(steps) <= 16:
        tick_steps = steps
    else:
        tick_steps = sorted(set([1, 4, 8, 12, 16] + list(range(20, len(steps) + 1, 4)) + [len(steps)]))
    ax1.set_xticks([s for s in tick_steps if 1 <= s <= len(steps)])
    ax1.grid(True, alpha=0.25)

    n_import = sum(1 for p in pts if p['phase'] == 'import')
    n_bo = len(pts) - n_import
    if n_import and n_bo:
        ax1.axvline(n_import + 0.5, color='gray', linestyle='--', linewidth=1)
        ax1.text(max(1, n_import / 2), max(hvs) * 1.01, 'Imported observations', ha='center', fontsize=9)
        ax1.text(n_import + max(1, n_bo / 2), max(hvs) * 1.01, 'New BO observations', ha='center', fontsize=9)

    ax2 = ax1.twinx()
    colors = ['#4C78A8' if p['phase'] == 'import' else '#F58518' for p in pts]
    ax2.bar(steps, inc, color=colors, alpha=0.28)
    ax2.set_ylabel('Incremental HV improvement')

    plt.title(args.title)
    plt.tight_layout()
    fig.savefig(plot_path, bbox_inches='tight')

    summary = {
        'export_csv': str(args.export_csv),
        'plot': str(plot_path),
        'progress_csv': str(progress_csv_path),
        'n_observations': len(pts),
        'n_imported': n_import,
        'n_new_bo': n_bo,
        'final_local_hv': hvs[-1],
        'import_hv_gain': sum(d for p, d in zip(pts, inc) if p['phase'] == 'import'),
        'new_bo_hv_gain': sum(d for p, d in zip(pts, inc) if p['phase'] == 'bo'),
        'reference_point_transformed_max_space': ref,
    }
    summary_json_path.write_text(json.dumps(summary, indent=2))
    print(f'Wrote {plot_path}')
    print(f'Wrote {progress_csv_path}')
    print(f'Wrote {summary_json_path}')


if __name__ == '__main__':
    main()
