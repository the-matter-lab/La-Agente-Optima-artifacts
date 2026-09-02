#!/usr/bin/env python3
"""Quiet supervised RoboChemFlex BO run: one successful experiment per child invocation.

- Starts a fresh BO-MCP + RoboFlex campaign unless ROBOCHEMFLEX_EXISTING_BO_CAMPAIGN_ID is set.
- Lets run_robochemflex_yield_bo.py do one successful measurement at a time.
- Prints only meaningful events/alerts plus child heartbeats.
- Stops after repeated zero/no-peak-like NMR results.
- Full child output is written to per-invocation logs.
"""
from __future__ import annotations

import json, os, re, select, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path.cwd()
STAMP = os.environ.get('ROBOCHEMFLEX_RUN_STAMP') or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
TOTAL = int(os.environ.get('ROBOCHEMFLEX_TOTAL_SUCCESS_BUDGET', '20'))
ZERO_STOP_N = int(os.environ.get('ROBOCHEMFLEX_ZERO_STOP_N', '5'))
RUN_TIMEOUT_S = float(os.environ.get('ROBOCHEMFLEX_RUN_TIMEOUT_S', '21600'))
CAMPAIGN_NAME = os.environ.get('ROBOCHEMFLEX_BO_CAMPAIGN_NAME', f'robochemflex_yield_baybe_fresh_{STAMP}')
RB_CAMPAIGN_NAME = os.environ.get('ROBOCHEMFLEX_RB_CAMPAIGN_NAME', f'robochemflex_yield_bo_fresh_{STAMP}')
ART_DIR = Path(os.environ.get('ROBOCHEMFLEX_ARTIFACT_DIR', str(ROOT / 'artifacts' / f'real_robochemflex_yield_bo_fresh_{STAMP}')))
LOG_DIR = Path(os.environ.get('ROBOCHEMFLEX_LOG_DIR', str(ROOT / 'logs' / f'real_robochemflex_yield_bo_fresh_{STAMP}')))
ADAPTER = str(ROOT / 'scripts' / 'robridge_post_adapter.py')
BO_ID_FILE = ART_DIR / 'bo_campaign_id.txt'
SUMMARY = ART_DIR / 'quiet_supervision_summary.jsonl'
ART_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
os.environ['ROBRIDGE_POST_ADAPTER'] = ADAPTER

bo_campaign_id = os.environ.get('ROBOCHEMFLEX_EXISTING_BO_CAMPAIGN_ID') or None
success_count = 0
zero_streak = 0
last_submitted_lines = 0

IMPORTANT_PATTERNS = [
    'BO campaign:', 'Started RoboFlex campaign', 'Using current RoboFlex campaign',
    'RoboFlex run submitted:', 'RoboFlex run ', 'RoboFlex platform:',
    'Submitted ', 'ALERT:', 'Stopped after', 'Completed ', 'Artifacts:',
]

def now(): return datetime.now(timezone.utc).isoformat()

def append(row):
    with SUMMARY.open('a') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')

def count_lines(path: Path) -> int:
    if not path.exists(): return 0
    return sum(1 for ln in path.open() if ln.strip())

def latest_jsonl(path: Path):
    if not path.exists(): return None
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None

def find_yield(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if 'yield' in str(k).lower() and isinstance(v, (int, float)):
                return float(v)
        for v in obj.values():
            out = find_yield(v)
            if out is not None: return out
    elif isinstance(obj, list):
        for v in obj:
            out = find_yield(v)
            if out is not None: return out
    return None

def nmr_bad_zero(result_obj) -> bool:
    y = find_yield(result_obj)
    if y is None or abs(y) > 1e-12:
        return False
    text = json.dumps(result_obj).lower()
    no_peak_position = '"peak position": null' in text or '"peak_position": null' in text
    zero_peak = ('"peak integral": 0' in text or '"peak_integral": 0' in text) and ('"peak width": 0' in text or '"peak_width": 0' in text)
    zero_conc = '"concentration": 0' in text
    return bool(no_peak_position or zero_peak or zero_conc)

def post_json(path: str, payload: dict | None = None):
    proc = subprocess.run([ADAPTER, 'POST', path], input=json.dumps(payload or {}), text=True, capture_output=True, timeout=120)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout or '{}')

def fetch_status():
    base = os.environ['ROBOFLEX_BASE_URL'].rstrip('/'); key = os.environ.get('ROBOFLEX_API_KEY','').strip()
    req = Request(f"{base}/v1/status", headers={'Accept':'application/json','User-Agent':'roboflex-agent-tools/0.1','X-API-Key':key})
    with urlopen(req, timeout=30) as r: return json.loads(r.read().decode())

def print_if_important(line: str):
    if any(p in line for p in IMPORTANT_PATTERNS):
        print(line, end='' if line.endswith('\n') else '\n', flush=True)

def run_one(i: int) -> int:
    global bo_campaign_id
    log_path = LOG_DIR / f'invocation_{i:02d}.log'
    cmd = [
        'uv','run','python','-u','run_robochemflex_yield_bo.py',
        '--mode','robridge-real','--allow-real-roboflex',
        '--max-successes','1','--no-pause-bo-on-exit',
        '--campaign-name', CAMPAIGN_NAME,
        '--robridge-campaign-name', RB_CAMPAIGN_NAME,
        '--artifact-dir', str(ART_DIR),
        '--run-timeout-s', str(RUN_TIMEOUT_S),
    ]
    if bo_campaign_id:
        cmd += ['--campaign-id', bo_campaign_id]
    print(f"[{now()}] EVENT invocation_start index={i} bo_campaign_id={bo_campaign_id or 'NEW'}", flush=True)
    with log_path.open('w') as lf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=os.environ.copy())
        fd = proc.stdout.fileno()
        while proc.poll() is None:
            r,_,_ = select.select([fd], [], [], 1.0)
            if r:
                line = proc.stdout.readline()
                if line:
                    lf.write(line); lf.flush(); print_if_important(line)
                    m = re.search(r'BO campaign:\s*([0-9a-fA-F-]{36})', line)
                    if m:
                        bo_campaign_id = m.group(1); BO_ID_FILE.write_text(bo_campaign_id+'\n')
        rem = proc.stdout.read() if proc.stdout else ''
        if rem:
            lf.write(rem); lf.flush()
            for line in rem.splitlines(True):
                print_if_important(line)
        return int(proc.returncode or 0)

print(f"[{now()}] QUIET_SUPERVISOR_START target_successes={TOTAL} zero_stop_n={ZERO_STOP_N}", flush=True)
print(f"[{now()}] artifacts={ART_DIR}", flush=True)
print(f"[{now()}] logs={LOG_DIR}", flush=True)
try:
    s=fetch_status(); p=s.get('progress') or {}
    print(f"[{now()}] PREFLIGHT phase={s.get('phase')} state={p.get('state')} queued={s.get('runs_queued')} running={s.get('runs_running')} campaign={bool(s.get('campaign'))}", flush=True)
except Exception as e:
    print(f"[{now()}] ALERT preflight_status_failed={e}", flush=True)

for i in range(1, TOTAL+1):
    before = count_lines(ART_DIR / 'submitted_results.jsonl')
    rc = run_one(i)
    after = count_lines(ART_DIR / 'submitted_results.jsonl')
    if rc != 0:
        print(f"[{now()}] ALERT invocation_failed index={i} exit_code={rc}; stopping supervision", flush=True)
        append({'time':now(),'event':'invocation_failed','index':i,'exit_code':rc,'bo_campaign_id':bo_campaign_id})
        break
    if after <= before:
        print(f"[{now()}] ALERT no_new_submitted_result index={i}; stopping supervision", flush=True)
        append({'time':now(),'event':'no_new_submitted_result','index':i,'bo_campaign_id':bo_campaign_id})
        break
    success_count += (after-before)
    raw = latest_jsonl(ART_DIR / 'robridge_results.jsonl')
    sub = latest_jsonl(ART_DIR / 'submitted_results.jsonl')
    result_obj = (raw or {}).get('result', {}).get('result') if raw else None
    y = find_yield(result_obj)
    green = (sub or {}).get('objective_values', {}).get('green_score') if sub else None
    run_id = (raw or {}).get('run_id')
    label = (raw or {}).get('label')
    bad = nmr_bad_zero(result_obj)
    zero_streak = zero_streak + 1 if bad else 0
    print(f"[{now()}] ANALYSIS experiment={success_count} run_id={run_id} label={label} yield={y} green_score={green} bad_zero_or_no_peak={bad} zero_streak={zero_streak}", flush=True)
    append({'time':now(),'event':'experiment_analyzed','experiment':success_count,'bo_campaign_id':bo_campaign_id,'run_id':run_id,'label':label,'yield_percent':y,'green_score':green,'bad_zero_or_no_peak':bad,'zero_streak':zero_streak})
    if zero_streak >= ZERO_STOP_N:
        print(f"[{now()}] ALERT early_stop_zero_streak={zero_streak}; requesting RoboFlex stop", flush=True)
        append({'time':now(),'event':'early_stop_zero_streak','zero_streak':zero_streak,'bo_campaign_id':bo_campaign_id})
        try:
            print(json.dumps(post_json('/v1/campaigns/current/stop', {}), sort_keys=True), flush=True)
        except Exception as e:
            print(f"[{now()}] ALERT roboflex_stop_failed={e}", flush=True)
        break
    if success_count >= TOTAL:
        break
print(f"[{now()}] QUIET_SUPERVISOR_DONE successes={success_count} bo_campaign_id={bo_campaign_id}", flush=True)
