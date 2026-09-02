from __future__ import annotations

import csv
import io
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


def main() -> None:
    base = Path('artifacts/digital_osl_stage1b/20260703T140530Z_execute')
    export_csv_path = base / 'campaign_export_latest_38obs.csv'
    progress_csv_path = base / 'hypervolume_progress_38obs.csv'
    plot_path = base / 'hypervolume_improvement_curve_38obs.png'
    summary_json_path = base / 'hypervolume_improvement_curve_38obs_summary.json'

    # Snapshot of the 38-observation campaign export at generation time.
    csv_text = '''"param_cap_id","param_bridge_id","param_core_id","obj_bright_osc_strength","obj_color_error_ev","obj_ambiguity_penalty","result_id","suggestion_id","created_at"
"A014","B065","C069","0.2264114787674688","0.0343259105745348","5.987674659122443","af763638-6afe-4c4a-a455-bc597eee3ff6","","2026-07-03T04:57:49.749496+00:00"
"A031","B065","C025","0.337165095378781","0.2132798219209846","10.827044255505484","068425f4-be0c-4340-90bd-dcd63400960b","","2026-07-03T04:57:49.788805+00:00"
"A014","B056","C025","1.52862828589325","0.4732485808668563","18.07330047311408","2e2eb270-174e-4e17-86c9-2d10a3244b4c","","2026-07-03T04:57:49.820314+00:00"
"A031","B056","C069","0.4412643423176632","0.1753230690235532","16.157639428631818","d19c1291-0362-4a90-9bae-5c6369cda8df","","2026-07-03T04:57:49.853521+00:00"
"A014","B066","C115","0.3072201353768226","0.7162985449685446","11.104707779211305","59719e8b-ffb5-4989-be39-e68fbfab688f","","2026-07-03T04:57:49.888975+00:00"
"A014","B056","C100","1.2158883164612058","0.5367373452645343","10.59935152015193","d99a4582-029c-405a-b181-50ed4849e822","","2026-07-03T04:57:49.923302+00:00"
"A014","B056","C080","1.1464935953630842","0.5374257594011493","11.4705340141477","7fef1c4d-cad4-482c-b61a-4befdaa32dab","","2026-07-03T04:57:49.957837+00:00"
"A014","B056","C115","0.4317020300195663","0.345037988963679","17.42026341691305","ce0c02c2-3892-43ce-ad7d-f606c60baf82","","2026-07-03T04:57:49.991296+00:00"
"A014","B065","C078","0.689135594922242","0.2150733859059714","12.447329430493392","60aa9399-d601-4750-8add-7e6610be4539","","2026-07-03T04:57:50.022353+00:00"
"A014","B056","C070","0.2603992424370072","0.2869836746598286","17.992754983772137","745ed7e0-71e5-40b5-8cd3-8e8dd856422f","","2026-07-03T04:57:50.052673+00:00"
"A014","B065","C070","0.2652999243088541","0.0329482155603142","6.033717199295122","092cc5aa-2081-46f0-9df5-1ab3fdf605ec","","2026-07-03T04:57:50.084519+00:00"
"A014","B065","C025","0.3986490068525455","0.3551320040163634","9.485097174978522","3c8b2426-1b7a-448d-8047-52e2a9b7b8ce","","2026-07-03T04:57:50.115987+00:00"
"A014","B065","C041","0.9006996688654821","0.2702097554819285","8.194432460674758","1e068761-02e3-4ad7-a8a0-7a1595726290","","2026-07-03T04:57:50.152373+00:00"
"A014","B065","C036","1.2664611158928354","0.3021354010491413","16.04998035902419","fcb019b9-15bb-4018-8c09-2bb2600129ee","","2026-07-03T04:57:50.188853+00:00"
"A031","B065","C041","0.2132568106075093","0.3161105552899053","6.442509003223011","a8ab73a8-063e-43c9-b9d7-4b65e46fc85c","","2026-07-03T04:57:50.225956+00:00"
"A031","B065","C069","0.0818524659702343","0.2253624309151569","10.86444074729347","18287f03-22d9-4b9d-b5b4-fd936537bd16","","2026-07-03T04:57:50.263929+00:00"
"A014","B065","C071","1.508884956129463","0.3072115663046602","19.242367217506562","dc0babdd-92d6-45c3-b765-3db3ec5f641d","f3ba2754-0609-4e9d-8a2b-eb88cdd14253","2026-07-03T05:01:52.773826+00:00"
"A015","B065","C041","0.6717815495009947","0.0977740809758676","4.352168072865121","97a3c122-fb56-4a39-9e4e-4bed3b1782e2","cc64f72a-7e5f-4f3b-af3c-eea48f2911dc","2026-07-03T05:07:33.386125+00:00"
"A039","B065","C041","0.49142703557464573","0.33057187819866973","27.939282406466027","a19b7313-2a5a-4700-a5e2-710328e0ec0f","10b6d0e4-1713-414d-997d-19747cfe0a33","2026-07-03T05:14:05.795797+00:00"
"A015","B065","C036","0.9593035068022013","0.06839007106656503","11.490212717182551","fd225347-3793-4498-87d6-64400fc261d9","f3e895eb-780e-4d0c-8113-e5923e1e0116","2026-07-03T05:20:04.018850+00:00"
"A015","B065","C071","1.002028521525244","0.09376444003792228","28.675056338192903","64332462-7cff-4112-b713-67ed12bc35d5","629dbdc2-3755-430f-b71f-296f06e50182","2026-07-03T05:26:54.150522+00:00"
"A015","B065","C031","0.2869959445060722","0.24198908720608703","19.452794530034872","d8996500-83f7-4f65-9ed4-d639341251f2","8c93cdae-7c43-4616-bdb9-15a1f1ee6b4f","2026-07-03T05:33:31.938960+00:00"
"A031","B056","C080","0.9685476385571932","0.3051727911846953","15.780784039670674","fe3f8c76-d635-48c7-876d-c6da9ae9025b","88890e1e-22a9-4988-9e69-0adab5a1338d","2026-07-03T05:39:05.155213+00:00"
"A015","B056","C025","0.9929570931235411","0.7314781261129333","10.67569353483802","ca31e466-c6a8-499b-abf5-e32dafb3f380","189c651b-6591-4283-bc5d-b5cad9f1c68d","2026-07-03T05:46:15.464616+00:00"
"A031","B065","C071","0.2318970620155808","0.4670277125461779","11.65028899160311","cb227a4d-1acb-41f2-94f4-ed9ba5c90750","f91e8a66-7ff0-4d25-b969-a08dbadbac1d","2026-07-03T05:51:19.162105+00:00"
"A015","B065","C070","0.13533186032155087","0.07598123065424112","20.4162492480185","5e2d1f00-e35f-471f-bc36-b543de063608","248a31f6-35a3-4ee0-93ff-108cc7c65662","2026-07-03T05:59:10.750783+00:00"
"A015","B065","C023","1.020078040002554","0.6706185738232102","18.32537323787547","1bc45465-3afd-4caa-bb0e-84a0b45fc722","a88decb3-b30c-4eff-9698-d6fd4cf3d9da","2026-07-03T06:06:01.956977+00:00"
"A042","B065","C036","0.5114365610914453","0.6057781462875171","26.620794165892338","41e31aed-9d1f-4330-8bbe-f113da1fc256","dd4228dd-8821-4cab-bd35-719d8017847d","2026-07-03T14:15:22.585106+00:00"
"A015","B056","C078","1.0857262165871677","0.23601105921574783","10.795355507136378","b48f8c52-7083-4ee5-9041-bae85cc3bcc7","2e0a0fff-6a92-491b-9119-e07e40a2b48d","2026-07-03T14:27:38.879048+00:00"
"A015","B057","C080","0.01946266794734569","0.3225296129898201","25.44547131291986","aaae58d5-36b3-42e3-b679-650512ba51ba","7da32d33-080e-4c3a-baf1-e300c7fd60d4","2026-07-03T14:41:10.414272+00:00"
"A015","B049","C078","0.010842979794302314","0.3179083963268563","4.784866506363129","7a73c223-2caa-42cb-9fda-68d2c4d27285","26604cef-aded-46a1-ba92-c5bb6f3c3be2","2026-07-03T14:55:11.958070+00:00"
"A015","B065","C069","0.1341859246580746","0.03461102543560868","10.714829119495807","29c6c940-a92d-48e2-93fd-b7914522b92c","8553d196-9b2a-4ae9-9916-2e7e57be651c","2026-07-03T15:07:19.846109+00:00"
"A039","B056","C078","0.9238816503371653","0.09934657658049861","43.25421324085797","670a256a-bd8d-4555-9832-fb0c920653c2","3376563f-36e2-4f96-aad2-5f0c783e2a74","2026-07-03T15:20:11.686456+00:00"
"A015","B049","C098","0.04616276780538785","0.2025778213989753","22.39570440070787","1e635caa-f7df-4623-9f15-f264e3732177","76eba47e-1fe7-403e-aed8-1168ffd4bc4b","2026-07-03T15:33:31.941477+00:00"
"A031","B057","C078","0.00492612882679905","0.9556961174745218","5.524644643378839","b46e0b24-96be-4f81-8f3e-9c48e96da9e7","111fbb27-98fa-4e54-9911-92c558cdd36b","2026-07-03T15:45:31.935616+00:00"
"A014","B056","C031","1.330161373847764","0.4649350588083365","10.178992603957237","f278ab01-3d6a-41b8-9731-59c8738dc27f","faaf20bc-c8ac-4d67-920f-fe827298790f","2026-07-03T15:56:05.704600+00:00"
"A014","B057","C078","0.0013246985048551746","0.5842811883829047","1.4000942734048742","3adc9bc0-c5f0-4f02-ba33-433b29d58791","cc0786f5-e8cd-4c80-aa13-8c853df47629","2026-07-03T16:08:23.409739+00:00"
"A014","B056","C078","0.8992877695609836","0.062181349418556575","10.880756126341527","6705071e-69dc-48f6-8384-10726bd23377","303036b4-ae25-4655-8aab-236fa19523c9","2026-07-03T16:18:47.113090+00:00"'''

    export_csv_path.write_text(csv_text)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    rows.sort(key=lambda r: r['created_at'])

    pts: list[dict] = []
    for i, r in enumerate(rows, 1):
        bright = float(r['obj_bright_osc_strength'])
        color = float(r['obj_color_error_ev'])
        amb = float(r['obj_ambiguity_penalty'])
        candidate = f"{r['param_cap_id']}{r['param_bridge_id']}{r['param_core_id']}"
        phase = 'import' if r['suggestion_id'] == '' else 'bo'
        pts.append({
            'step': i,
            'candidate': candidate,
            'phase': phase,
            'raw': (bright, color, amb),
            'vec': (bright, -color, -amb),
        })

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
        w.writerow(['step', 'candidate_id', 'phase', 'hypervolume', 'hv_improvement', 'bright_osc_strength', 'color_error_ev', 'ambiguity_penalty'])
        for p, hv, d in zip(pts, hvs, inc):
            w.writerow([p['step'], p['candidate'], p['phase'], hv, d, *p['raw']])

    fig, ax1 = plt.subplots(figsize=(10, 5.5), dpi=160)
    steps = [p['step'] for p in pts]
    ax1.plot(steps, hvs, marker='o', linewidth=2, color='#1f77b4')
    ax1.set_xlabel('Observation index')
    ax1.set_ylabel('Hypervolume (campaign-local units)')
    ax1.set_xticks([1, 4, 8, 12, 16, 20, 24, 28, 32, 36, 38])
    ax1.grid(True, alpha=0.25)
    ax1.axvline(16.5, color='gray', linestyle='--', linewidth=1)
    ax1.text(8.5, max(hvs) * 1.01, 'Imported Stage 1 observations', ha='center', fontsize=9)
    ax1.text(27, max(hvs) * 1.01, 'New Stage 1b BO observations', ha='center', fontsize=9)

    ax2 = ax1.twinx()
    colors = ['#4C78A8' if p['phase'] == 'import' else '#F58518' for p in pts]
    ax2.bar(steps, inc, color=colors, alpha=0.28)
    ax2.set_ylabel('Incremental HV improvement')

    plt.title('Stage 1b hypervolume improvement (38 observations so far)')
    plt.tight_layout()
    fig.savefig(plot_path, bbox_inches='tight')

    summary = {
        'plot': str(plot_path),
        'progress_csv': str(progress_csv_path),
        'n_observations': len(pts),
        'n_imported': sum(1 for p in pts if p['phase'] == 'import'),
        'n_new_bo': sum(1 for p in pts if p['phase'] == 'bo'),
        'final_local_hv': hvs[-1],
        'import_hv_gain': sum(inc[:16]),
        'new_bo_hv_gain': sum(inc[16:]),
        'best_post_import_gain_step': max(range(16, len(inc)), key=lambda i: inc[i]) + 1,
        'best_post_import_gain': max(inc[16:]),
    }
    summary_json_path.write_text(json.dumps(summary, indent=2))

    print(f'Wrote {export_csv_path}')
    print(f'Wrote {progress_csv_path}')
    print(f'Wrote {plot_path}')
    print(f'Wrote {summary_json_path}')


if __name__ == '__main__':
    main()
