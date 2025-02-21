#!/usr/bin/env python3

"""Seismic signal processing workflows.

William Jenkins, wjenkins [at] ucsd [dot] edu
Scripps Institution of Oceanography, UC San Diego
January 2021
"""
from copy import deepcopy
import os

import numpy as np
import obspy
from obspy.signal import trigger
import pandas as pd

from RISProcess.io import write_h5datasets
from RISProcess import processing

"""
This function works with hank coles detection catalogue which has some slightly different parameters
only single core for now, not intended for use witht he process utility yet


"""
def build_h5_hank_catalogue(params,srate=0.02):
    catalogue = pd.read_csv(params.catalogue, parse_dates=[4,5,6], index_col=0)
    mask_start = params.start.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    mask_stop = params.stop.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    mask = (catalogue['pick_time'] >= mask_start) & (catalogue['pick_time'] < mask_stop)
    catalogue = catalogue.loc[mask]
    
    
    if params.station == "*":
        station_list = catalogue["station"].unique()
    else:
        station_list = [params.station]
    count = 0
    

    
    for station in station_list:
        try:
            mask = catalogue["station"] == station
            subcatalogue = catalogue.loc[mask]
            #I am actually working on the subcatalogue object
            M = len(subcatalogue)
            #this is a bit of a hack, its meant to deal with the fact that Jenkins coded this to opperate with 4 second intervals
            #it should be dynamic now
            tr_arr = np.zeros((M, int(params.T_seg/(params.dt))-1))
            #S_arr = []           
            S_arr = np.zeros((M, 98, int(params.T_seg/(params.dt*2))+1))
            metadata = []
            dt_prev = subcatalogue["pick_time"].iloc[0]
            for i, row in enumerate(subcatalogue.itertuples()):
                dt = row.pick_time
                if (i > 1) and (dt < dt_prev + pd.Timedelta(params.det_window, "sec")):
                    continue
                else:
                    start = pd.Timestamp(row.body_ta) - pd.Timedelta(params.det_window, "sec")
                    stop = pd.Timestamp(row.body_ta) + pd.Timedelta(params.det_window, "sec")
                    params_copy = deepcopy(params)
                    params_copy.update_times(start, stop)
                    params_copy.station = row.station
                    #I am not sure why the specturm (S) has 3 parameters here?
                    tr = processing.pipeline(params_copy)[0]
                    _, _, _, S_arr[i], dt0, dt1 = processing.centered_spectrogram(tr, params_copy)
                    
                    tr_arr[i, :] = tr.trim(
                        starttime=obspy.core.UTCDateTime(dt0),
                        endtime=obspy.core.UTCDateTime(dt1)
                    ).data

                    entry = row._asdict()
                    entry["spec_start"] = dt0
                    entry["spec_stop"] = dt1
                    entry.update((k, v.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]) for k, v in entry.items() if isinstance(v, pd.Timestamp))
                    metadata.append(entry)
                    dt_prev = dt
                    
            not_zeros = [tr_arr[i,:].any() for i in range(M)]
            tr_arr = tr_arr[not_zeros]
            S_arr = S_arr[not_zeros]
            
            try:
                count += write_h5datasets(tr_arr, S_arr, metadata, params)
                
            except OSError:
                raise OSError("Unable to write data; check write path.")
        except OSError:
            print("os error in processing module")
            raise
            
        except KeyError:
            print("Did you forget to initialize the hdf5 object?")
            raise
        """
        except Exception as e:
            print(repr(e))
            break
        """
        
    return count
    
    

def build_h5(params):
    catalogue = pd.read_csv(params.catalogue, parse_dates=[4,5,6], index_col=0)
    mask_start = params.start.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    mask_stop = params.stop.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    mask = (catalogue['dt_on'] >= mask_start) & (catalogue['dt_on'] < mask_stop)
    catalogue = catalogue.loc[mask]

    if catalogue["dt_on"].empty:
        print("the catalogue was empty")
        return 0
    else:
        if params.station == "*":
            station_list = catalogue["station"].unique()
        else:
            station_list = [params.station]
        count = 0
        for station in station_list:
            try:
                mask = catalogue["station"] == station
                subcatalogue = catalogue.loc[mask]
                M = len(subcatalogue)
                tr_arr = np.zeros((M, 199))
                S_arr = np.zeros((M, 88, 101))
                metadata = []
                dt_prev = subcatalogue["dt_on"].iloc[0]
                for i, row in enumerate(subcatalogue.itertuples()):
                    dt = row.dt_on
                    if (i > 1) and (dt < dt_prev + pd.Timedelta(params.det_window, "sec")):
                        continue
                    else:
                        start = row.dt_peak - pd.Timedelta(params.det_window, "sec")
                        stop = row.dt_peak + pd.Timedelta(params.det_window, "sec")
                        params_copy = deepcopy(params)
                        params_copy.update_times(start, stop)
                        params_copy.station = row.station
                        tr = processing.pipeline(params_copy)[0]
                        _, _, _, S_arr[i], dt0, dt1 = processing.centered_spectrogram(tr, params_copy)
                        tr_arr[i, :] = tr.trim(
                            starttime=obspy.core.UTCDateTime(dt0),
                            endtime=obspy.core.UTCDateTime(dt1)
                        ).data
                        entry = row._asdict()
                        entry["spec_start"] = dt0
                        entry["spec_stop"] = dt1
                        entry.update((k, v.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]) for k, v in entry.items() if isinstance(v, pd.Timestamp))
                        metadata.append(entry)
                        dt_prev = dt

                not_zeros = [tr_arr[i,:].any() for i in range(M)]
                tr_arr = tr_arr[not_zeros]
                S_arr = S_arr[not_zeros]
                try:
                    count += write_h5datasets(tr_arr, S_arr, metadata, params)
                except OSError:
                    raise OSError("Unable to write data; check write path.")
            except OSError:
                raise
            except:
                continue
        return count


def process_data(params):
    """Provides end-to-end signal processing, including reading, detrending,
    tapering, filtering, instrument response removal, and saving.

    Parameters
    ----------
    params : SignalProcessing object
        Object containing signal processing parameters passed.

    Returns
    -------
    int
        Number of files saved to disk.
    """
    st = processing.pipeline(params)
    if st == 0:
        return 0

    if params.mode == "preprocess":
        if params.verbose:
            print("Trimming.")
        st.trim(
            starttime=obspy.core.UTCDateTime(params.start),
            endtime=obspy.core.UTCDateTime(params.stop)
        )
        count = 0
        for tr in st:
            path = f"{params.writepath}/MSEED/{tr.stats.network}/{tr.stats.station}"
            if not os.path.exists(path):
                os.makedirs(path)
            fname = f"{tr.stats.network}.{tr.stats.station}.{tr.stats.channel}.{params.start.year}.{params.start.dayofyear:03d}.mseed"
            tr.data = tr.data.astype("float32")
            tr.write(f"{path}/{fname}", format="MSEED", encoding=4)
            count += 1
        return count

    else:
        count = 0
        if params.verbose:
            print("Running detector.")
        path = params.writepath
        if not os.path.exists(path):
            os.makedirs(path)
        for tr in st:
            fs = tr.stats.sampling_rate
            catalogue = pd.DataFrame(columns=["network", "station", "channel", "dt_on", "dt_off", "dt_peak", "peak", "unit", "fs", "delta", "npts", "STA", "LTA", "on", "off"])
            if not os.path.exists(f"{path}/catalogue.csv"):
                catalogue.to_csv(f"{path}/catalogue.csv", mode="a", index=False)
            secs = np.arange(0, tr.stats.npts * tr.stats.delta, tr.stats.delta)
            time = params.start_processing + pd.to_timedelta(secs, unit="sec")
            if params.verbose:
                print("Calculating CFT.")
            if params.detector == "classic":
                cft = trigger.classic_sta_lta(tr.data, int(fs * params.STA), int(fs * params.LTA))
            elif params.detector == "recursive":
                cft = trigger.recursive_sta_lta(tr, int(fs * params.STA), int(fs * params.LTA))
            elif params.detector == "z":
                cft = trigger.z_detect(tr.data, int(fs * 3))
            if params.verbose:
                print("Locating triggers.")
            on_off = trigger.trigger_onset(cft, params.on, params.off)
            if isinstance(on_off, list):
                del catalogue
                continue
            on_off = on_off[(time[on_off[:,0]] >= params.start) & (time[on_off[:,0]] < params.stop), :]
            nrows = on_off.shape[0]
            catalogue["network"] = [tr.stats.network for i in range(nrows)]
            catalogue["station"] = [tr.stats.station for i in range(nrows)]
            catalogue["channel"] = [tr.stats.channel for i in range(nrows)]
            catalogue["dt_on"] = time[on_off[:,0]]
            catalogue["dt_off"] = time[on_off[:,1]]
            i_max = [(on_off[i,0] + np.argmax(abs(tr.data[on_off[i,0]:on_off[i,1]]))) for i in range(on_off.shape[0])]
            catalogue["dt_peak"] = time[i_max]
            catalogue["peak"] = tr.data[i_max]
            catalogue["unit"] = [params.output for i in range(nrows)]
            catalogue["fs"] = [fs for i in range(nrows)]
            catalogue["delta"] = [tr.stats.delta for i in range(nrows)]
            catalogue["npts"] = [tr.stats.npts for i in range(nrows)]
            catalogue["STA"] = [params.STA for i in range(nrows)]
            catalogue["LTA"] = [params.LTA for i in range(nrows)]
            catalogue["on"] = [params.on for i in range(nrows)]
            catalogue["off"] = [params.off for i in range(nrows)]
            catalogue.to_csv(f"{path}/catalogue.csv", mode="a", index=False, header=False)
            if params.verbose:
                print("Catalogue built.")
            del catalogue
            count += on_off.shape[0]
        return count
