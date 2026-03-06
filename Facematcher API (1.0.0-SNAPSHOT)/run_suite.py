#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_suite.py — Run the full test suite N times in a row.

Usage:
    python run_suite.py              # runs 10 times (default)
    python run_suite.py --count 3   # runs 3 times
    python run_suite.py --count 1 --verbose   # 1 run with full pytest output
"""
import subprocess
import sys
import argparse
import time
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description='Run the test suite multiple times.')
    parser.add_argument('--count',   type=int, default=10, help='Number of times to run (default: 10)')
    parser.add_argument('--verbose', action='store_true',  help='Show full pytest output for every run')
    return parser.parse_args()


def run_once(run_number, total, verbose):
    print(f'\n{"=" * 65}')
    print(f'  RUN {run_number}/{total}  —  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'{"=" * 65}')

    cmd = [sys.executable, '-m', 'pytest', 'requests/', '-v', '--tb=short', '--no-header']

    if verbose:
        result = subprocess.run(cmd)
    else:
        result = subprocess.run(cmd, capture_output=True, text=True)

        # Always print the last 30 lines (summary + failures)
        lines = (result.stdout + result.stderr).splitlines()
        for line in lines[-30:]:
            print(line)

    return result.returncode


def main():
    args  = parse_args()
    count = args.count

    print(f'\nTest Suite Runner')
    print(f'Runs    : {count}')
    print(f'Suite   : requests/')
    print(f'Started : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    results  = []   # list of (run_number, returncode, duration_s)
    start_all = time.time()

    for i in range(1, count + 1):
        t0  = time.time()
        rc  = run_once(i, count, args.verbose)
        dur = time.time() - t0
        results.append((i, rc, dur))

    total_duration = time.time() - start_all

    # ── Summary table ──────────────────────────────────────────────────────
    print(f'\n{"=" * 65}')
    print(f'  SUMMARY  ({count} runs)')
    print(f'{"=" * 65}')
    print(f'  {"Run":<6} {"Status":<10} {"Duration":>10}')
    print(f'  {"-"*6} {"-"*10} {"-"*10}')

    passed_runs = 0
    for run_num, rc, dur in results:
        status = 'PASSED' if rc == 0 else 'FAILED'
        marker = '' if rc == 0 else '  <-- FAILED'
        print(f'  {run_num:<6} {status:<10} {dur:>9.1f}s{marker}')
        if rc == 0:
            passed_runs += 1

    failed_runs = count - passed_runs
    print(f'{"=" * 65}')
    print(f'  Passed : {passed_runs}/{count}')
    if failed_runs:
        print(f'  Failed : {failed_runs}/{count}')
    print(f'  Total  : {total_duration:.1f}s')
    print(f'{"=" * 65}\n')

    # Exit with error if any run failed
    sys.exit(0 if failed_runs == 0 else 1)


if __name__ == '__main__':
    main()
