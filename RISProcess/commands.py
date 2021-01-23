#!/usr/bin/env python3

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime

import pandas as pd
from tqdm import tqdm

from RISProcess.io import config
from RISProcess import workflows
from RISProcess.processing import SignalProcessing


def process():
    """This command line function, processes, and saves raw MSEED seismic data.
    Functions available allow for filtering, decimation, and instrument
    response removal. Single- and multi-core processing are available.
    Parameters are passed to the function through a config file.

    Parameters
    ----------
    path : command line input
        This command-line function requires as input the path to the saved
        configuration file.
    """
    tic = datetime.now()
    parser = argparse.ArgumentParser(
        description="Command-line tool for processing RIS seismic data."
    )
    parser.add_argument("path", help="Path to config file")
    args = parser.parse_args()
    params = SignalProcessing(**config("r", path=args.path))
    print("=" * 79)
    print(f"Processing data.  Workers: {params.num_workers}")
    start_search = params.start.floor('D')
    stop_search = params.stop.floor('D')
    dts = pd.date_range(start_search, stop_search)[:-1]
    A = list()
    for dt in dts:
        params_copy = deepcopy(params)
        params_copy.update_times(dt, dt + pd.Timedelta(1, "D"))
        A.append(dict(params=params_copy))
    count = 0
    pbargs = {
        'total': int(len(dts)),
        'unit_scale': True,
        'bar_format': '{l_bar}{bar:20}{r_bar}{bar:-20b}',
        'leave': True
    }
    if (params.mode == "preprocess") or (params.mode == "detect"):
        if params.num_workers == 1:
            for a in tqdm(A, **pbargs):
                count += workflows.process_data(**a)
        else:
            with ProcessPoolExecutor(max_workers=params.num_workers) as exec:
                futures = [exec.submit(workflows.process_data, **a) for a in A]
                for future in tqdm(as_completed(futures), **pbargs):
                    count += future.result()

        print(f"Processing complete.")
        if params.mode == "preprocess":
            print(f"{count} files saved to {params.writepath}")
        elif params.mode == "detect":
            print(f"{count} detections; catalogue saved to {params.writepath}")
    elif params.mode == "cat2h5":
        io.init_h5datasets(params)
        if params.num_workers == 1:
            for a in tqdm(A, **pbargs):
                count += workflows.build_h5(**a)
        else:
            with ProcessPoolExecutor(max_workers=params.num_workers) as exec:
                MAX_JOBS_IN_QUEUE = params.num_workers
                jobs = {}
                days_left = len(A)
                days_iter = iter(A)

                while days_left:
                    for a in days_iter:
                        job = exec.submit(workflows.build_h5, **a)
                        jobs[job] = a
                        if len(jobs) > MAX_JOBS_IN_QUEUE:
                            break
                    for job in as_completed(jobs):
                        days_left -= 1
                        count += job.result()
                        a = jobs[job]
                        del jobs[job]
                        print(
                            f"{len(dts) - days_left}/{len(dts)} days ",
                            f"({100*(len(dts) - days_left)/len(dts):.1f}%) ",
                            f"processed.",
                            flush=True,
                            end="\r"
                        )
                        break
        print(f"\n{count} samples saved.")
    time_elapsed = str(datetime.now() - tic)[:-7]
    print(f"{time_elapsed} elapsed.")
    print("=" * 79)
