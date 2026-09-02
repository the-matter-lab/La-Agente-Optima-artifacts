#!/usr/bin/env python3
"""Run RoboChemFlex campaign one successful experiment at a time and inspect results.

Stops early on repeated zero/no-peak NMR results or runtime failure.
"""
from __future__ import annotations

import json, os, re, select, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path.cwd()
STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
LOG_DIR = ROOT / 'logs' / f'real_robochemflex_yield_bo_{STAMP}'
ART_DIR = ROOT / 'artifacts' / f'real_robochemflex_yield_bo_{STAMP}'
LOG_DIR.mkdir(parents=True, exist_ok=True)
ART_DIR.mkdir(parents=True, exist_ok=True)

TOTAL = int(os.environ.get('ROBOCHEMFLEX_TOTAL_SUCCESS_BUDGET', '20'))
ZERO_STOP_N = int(os.environ.get('ROBOCHEMFLEX_ZERO_STOP_N', '5'))
POLL_S = float(os.environ.get('ROBOCHEMFLEX_STATUS_POLL_S', '120'))
RUN_TIMEOUT_S = float(os.environ.get('ROBOCHEMFLEX_RUN_TIMEOUT_S', '10800'))
CAMPAIGN_NAME = os.environ.get('ROBOCHEMFLEX_BO_CAMPAIGN_NAME', f'robochemflex_yield_baybe_real_{STAMP}')
RB_CAMPAIGN_NAME = os.environ.get('ROBOCHEMFLEX_RB_CAMPAIGN_NAME', f'robochemflex_yield_bo_{STAMP}')
ADAPTER = str(ROOT / 'scripts' / 'robridge_post_adapter.py')

os.environ['ROBRIDGE_POST_ADAPTER'] = ADAPTER

bo_campaign_id: str | None = os.environ.get('ROBOCHEMFLEX_EXISTING_BO_CAMPAIGN_ID') or None
zero_streak = 0
success_count = 0

summary_path = ART_DIR / 'supervision_summary.jsonl'


def now(): return datetime.now(timezone.utc).isoformat()

def append_summary(row):
    with summary_path.open('a') as f: f.write(json.dumps(row, sort_keys=True) + '\n')

def fetch_json(path: str) -> dict:
    base = os.environ['ROBOFLEX_BASE_URL'].rstrip('/')
    key = os.environ.get('ROBOFLEX_API_KEY', '').strip()
    req = Request(f"{base}/{path.lstrip('/')}", headers={
        'Accept': 'application/json, text/plain',
        'User-Agent': 'roboflex-agent-tools/0.1',
        'X-API-Key': key,
    })
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))

def post_json(path: str, payload: dict | None = None) -> dict:
    proc = subprocess.run([ADAPTER, 'POST', path], input=json.dumps(payload or {}), text=True, capture_output=True, timeout=120)
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout or '{}')

def concise_status() -> str:
    try:
        s = fetch_json('/v1/status')
        p = s.get('progress') or {}
        return (f"phase={s.get('phase')} state={p.get('state')} blocked_on={p.get('blocked_on')} "
                f"busy={p.get('busy')} elapsed_s={p.get('elapsed_s')} overdue={p.get('overdue')} "
                f"queued={s.get('runs_queued')} running={s.get('runs_running')} completed={s.get('runs_completed')} "
                f"failed={s.get('runs_failed')} active={p.get('active_run_ids')} msg={p.get('message')}")
    except Exception as exc:
        return f'status_poll_error={exc}'

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
    # Flag classic no-peak zero: peak position null or integral/width/concentration all zero.
    text = json.dumps(result_obj).lower()
    no_peak_position = '"peak position": null' in text or '"peak_position": null' in text
    zero_peak = ('"peak integral": 0' in text or '"peak_integral": 0' in text) and ('"peak width": 0' in text or '"peak_width": 0' in text)
    zero_conc = '"concentration": 0' in text
    return no_peak_position or zero_peak or zero_conc

def run_one(invocation: int) -> tuple[int, str]:
    global bo_campaign_id
    log_path = LOG_DIR / f'invocation_{invocation:02d}.log'
    cmd = [
        'uv', 'run', 'python', '-u', 'run_robochemflex_yield_bo.py',
        '--mode', 'robridge-real', '--allow-real-roboflex',
        '--max-successes', '1', '--no-pause-bo-on-exit',
        '--campaign-name', CAMPAIGN_NAME,
        '--robridge-campaign-name', RB_CAMPAIGN_NAME,
        '--artifact-dir', str(ART_DIR),
        '--run-timeout-s', str(RUN_TIMEOUT_S),
    ]
    if bo_campaign_id:
        cmd += ['--campaign-id', bo_campaign_id]
    print(f"[{now()}] INVOCATION {invocation} START: {' '.join(cmd)}", flush=True)
    print(f"[{now()}] initial status: {concise_status()}", flush=True)
    with log_path.open('w') as lf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=os.environ.copy())
        out_parts=[]; next_poll=time.monotonic()+POLL_S
        fd = proc.stdout.fileno() if proc.stdout else None
        while proc.poll() is None:
            if fd is not None:
                r,_,_=select.select([fd], [], [], 1.0)
                if r:
                    line = proc.stdout.readline()
                    if line:
                        out_parts.append(line); lf.write(line); lf.flush(); print(line, end='', flush=True)
                        m = re.search(r'BO campaign:\s*([0-9a-fA-F-]{36})', line)
                        if m: bo_campaign_id = m.group(1)
            if time.monotonic() >= next_poll:
                st = f"[{now()}] status: {concise_status()}\n"
                lf.write(st); lf.flush(); print(st, end='', flush=True)
                next_poll = time.monotonic()+POLL_S
        # drain remaining
        if proc.stdout:
            rem=proc.stdout.read()
            if rem:
                out_parts.append(rem); lf.write(rem); print(rem, end='', flush=True)
        rc=proc.returncode
    return rc, ''.join(out_parts)

print(f"[{now()}] Supervised real campaign started. target_successes={TOTAL}, zero_stop_n={ZERO_STOP_N}", flush=True)
print(f"[{now()}] logs={LOG_DIR}", flush=True)
print(f"[{now()}] artifacts={ART_DIR}", flush=True)
print(f"[{now()}] preflight status: {concise_status()}", flush=True)

try:
    for i in range(1, TOTAL+1):
        rc, out = run_one(i)
        if rc != 0:
            print(f"[{now()}] Invocation {i} failed with exit code {rc}; stopping supervised campaign.", flush=True)
            append_summary({'time': now(), 'invocation': i, 'event': 'invocation_failed', 'returncode': rc, 'bo_campaign_id': bo_campaign_id})
            break
        success_count += 1
        raw = latest_jsonl(ART_DIR / 'robridge_results.jsonl')
        sub = latest_jsonl(ART_DIR / 'submitted_results.jsonl')
        result_obj = (raw or {}).get('result', {}).get('result') if raw else None
        y = find_yield(result_obj)
        green = (sub or {}).get('objective_values', {}).get('green_score') if sub else None
        bad = nmr_bad_zero(result_obj)
        zero_streak = zero_streak + 1 if bad else 0
        run_id = (raw or {}).get('run_id')
        label = (raw or {}).get('label')
        print(f"[{now()}] ANALYSIS after experiment {success_count}: run_id={run_id} label={label} yield={y} green_score={green} bad_zero_or_no_peak={bad} zero_streak={zero_streak}", flush=True)
        append_summary({'time': now(), 'invocation': i, 'event': 'experiment_analyzed', 'success_count': success_count, 'bo_campaign_id': bo_campaign_id, 'run_id': run_id, 'label': label, 'yield_percent': y, 'green_score': green, 'bad_zero_or_no_peak': bad, 'zero_streak': zero_streak})
        if zero_streak >= ZERO_STOP_N:
            print(f"[{now()}] STOPPING EARLY: {zero_streak} consecutive zero/no-peak-like NMR results.", flush=True)
            append_summary({'time': now(), 'event': 'early_stop_zero_streak', 'zero_streak': zero_streak, 'bo_campaign_id': bo_campaign_id})
            try:
                print(f"[{now()}] Requesting RoboFlex campaign stop...", flush=True)
                print(json.dumps(post_json('/v1/campaigns/current/stop', {}), sort_keys=True), flush=True)
            except Exception as exc:
                print(f"[{now()}] RoboFlex stop request failed: {exc}", flush=True)
            break
    print(f"[{now()}] Supervised campaign loop finished. successes_this_run={success_count}, bo_campaign_id={bo_campaign_id}", flush=True)
    print(f"[{now()}] final status: {concise_status()}", flush=True)
except KeyboardInterrupt:
    print(f"[{now()}] Interrupted by operator. bo_campaign_id={bo_campaign_id}", flush=True)
    raise
