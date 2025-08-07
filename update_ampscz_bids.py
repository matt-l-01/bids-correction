#!/usr/bin/env python3
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import shutil
import os
import json
import argparse
import re
import pandas as pd
import diskcache as dc
import datetime

cache = {}


def rename_run_num(root_directory="rawdata", discard_orig=False, no_links=False):
    print('Fixing run numbers.')
    parent_dir = os.path.dirname(os.path.abspath(root_directory.rstrip("/")))
    csv_path = os.path.join(parent_dir, 'update_log.csv')

    if not os.path.exists(csv_path):
        print(f"Update log not found: {csv_path}")
        exit(1)
        return

    try:
        updates_df = pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        print(f"Update log is empty: {csv_path}")
        return

    if not discard_orig:
        print(
            'Making copies of every folder that will be modified. This may take a while...')
        # Make copies to modified dirs
        to_copy_dirs = set()
        for _, row in updates_df.iterrows():
            # Keep track of modified dirs and duplicate first
            to_copy_dirs.add(os.path.dirname(row["before_path"]))

        for path in sorted(to_copy_dirs):
            copy_entire_folder_to_orig(path, no_links)

    for _, row in updates_df.iterrows():
        old_json_path = row["before_path"]
        new_json_path = row["after_path"]

        # Rename JSON file
        rename_file(old_json_path, os.path.basename(new_json_path))

        # Handle the NIfTI file: replace .json with .nii.gz
        old_nii_path = old_json_path.replace(".json", ".nii.gz")
        new_nii_path = new_json_path.replace(".json", ".nii.gz")

        if os.path.exists(old_nii_path):
            rename_file(old_nii_path, os.path.basename(new_nii_path))
        else:
            print(f"Missing corresponding NIfTI file: {old_nii_path}")


def read_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
            return (file_path, json_data)
    except Exception as e:
        print(f"Failed to read {file_path}: {e}")
        return None


all_keys = set()


def pull_series_info(root_dir, partial=False, threads=8):
    print('Pulling series info.')

    series_total = 0
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {}  # maps future -> (subject, session)

        with os.scandir(root_dir) as subjects:
            for subject_entry in subjects:
                if not subject_entry.is_dir():
                    continue
                subject = subject_entry.name
                subject_path = subject_entry.path

                with os.scandir(subject_path) as sessions:
                    for session_entry in sessions:
                        if not session_entry.is_dir():
                            continue
                        session = session_entry.name
                        session_path = session_entry.path

                        session_key = (subject, session)

                        # Check cache before processing
                        all_keys.add(session_key)

                        if partial:
                            cached_value = cache.get(
                                f"{session_key[0]}/{session_key[1]}[{root_dir}]")
                            if isinstance(cached_value, dict):
                                print(
                                    f"Skipping cached pull {session_key}")
                                continue

                        with os.scandir(session_path) as subfolders:
                            for subfolder_entry in subfolders:
                                if not subfolder_entry.is_dir():
                                    continue
                                subfolder_path = subfolder_entry.path

                                with os.scandir(subfolder_path) as files:
                                    for file_entry in files:
                                        if file_entry.is_file() and file_entry.name.endswith(".json"):
                                            series_total += 1
                                            if series_total % 100 == 0:
                                                print(
                                                    f'{series_total} files scanned.')
                                            file_path = file_entry.path
                                            future = executor.submit(
                                                read_json_file, file_path)
                                            futures[future] = session_key

        # Collect results and group them by session
        session_data = defaultdict(list)
        series_complete = 0
        for future in as_completed(futures):
            result = future.result()
            if result:
                series_complete += 1
                file_path, json_data = result
                session_key = futures[future]
                session_data[session_key].append((file_path, json_data))
                percent_complete = (
                    series_complete / series_total) * 100 if series_total else 0
                if partial:
                    cache.set(
                        f'{session_key[0]}/{session_key[1]}[{root_dir}]', json_data)
                print(
                    f"({series_complete}/{series_total} : {percent_complete:.1f}%) Pulled {file_path}")

    session_data_final = {}

    # Add all the cached data first
    for key in all_keys:
        key_str = f"{key[0]}/{key[1]}[{root_dir}]"
        # Ignore keys not in cache
        if key_str not in cache:
            continue

        cached_dict = cache.get(key_str)

        if not isinstance(cached_dict, dict):
            print('ERROR: Cached item is not a dict')
            continue

        # Sort series within each session by SeriesNumber
        sorted_list = sorted(
            session_data[key], key=lambda x: x[1].get("SeriesNumber", 0))
        session_data_final[key] = sorted_list

    for session_key, file_json_list in session_data.items():
        # Add the data read from this execution
        sorted_list = sorted(
            file_json_list, key=lambda x: x[1].get("SeriesNumber", 0))
        session_data_final[session_key] = sorted_list

    return session_data_final


def generate_log(all_data, root_directory="rawdata"):
    print('Generating log.')
    updates = []

    for sub_ses, series_lst in all_data.items():
        session_run_count = {'DistortionMap_AP': 0, 'DistortionMap_PA': 0, 'T1w': 0, 'T2w': 0,
                             'dMRI_b0_AP_SBRef': 0, 'dMRI_b0_AP': 0,
                             'dMRI_PA_SBRef': 0, 'dMRI_PA': 0,
                             'rfMRI_REST_AP_SBRef': 0, 'rfMRI_REST_PA_SBRef': 0,
                             'rfMRI_REST_AP': 0, 'rfMRI_REST_PA': 0}

        def match_series_desc(s_desc):
            if s_desc.startswith('dMRI_dir') and s_desc.endswith('PA_SBRef'):
                return 'dMRI_PA_SBRef'
            if s_desc.startswith('dMRI_dir') and s_desc.endswith('PA'):
                return 'dMRI_PA'
            if s_desc.endswith('_Ref'):
                s_desc = f'{s_desc[:-4]}_SBRef'

            for key in session_run_count:
                if key in s_desc:
                    return key
            return None

        for s in series_lst:
            run_match = re.search(r'run-\d+', s[0])
            run_str = run_match.group(0) if run_match else s[0]

            s_num = s[1].get("SeriesNumber")
            s_desc = s[1].get("SeriesDescription")

            for key in session_run_count.keys():
                def update_run_if_needed(file_path, run_str, run_count, session_id):
                    current_run = int(re.search(r'\d+', run_str).group())
                    if current_run != run_count:
                        updated_fname = re.sub(
                            r'run-\d+', f'run-{run_count}', file_path)
                        updates.append({
                            'subject': session_id[0],
                            'session': session_id[1],
                            'series_desc': s_desc,
                            'before_run': current_run,
                            'after_run': run_count,
                            'before_path': file_path,
                            'after_path': updated_fname
                        })

                match_key = match_series_desc(s_desc)

                if match_key:
                    session_run_count[match_key] += 1

                    update_run_if_needed(
                        s[0], run_str, session_run_count[match_key], sub_ses)
                    break

            print(
                f'{sub_ses} : {s[1].get("SeriesNumber")} : {run_str} : {s[1].get("SeriesDescription")}')
        print(session_run_count)

    updates_df = pd.DataFrame(updates)

    # Save to CSV file
    parent_dir = os.path.dirname(os.path.abspath(root_directory.rstrip("/")))
    output_csv_path = os.path.join(parent_dir, 'update_log.csv')
    # If update_log.csv exists, archive it first
    if os.path.exists(output_csv_path):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archived_path = os.path.join(
            parent_dir, f'update_log_archived_{timestamp}.csv')
        os.rename(output_csv_path, archived_path)
        print(f"Existing update_log.csv archived as: {archived_path}")

    updates_df.sort_values(by=['subject', 'session'], inplace=True)
    updates_df.to_csv(output_csv_path, index=False)
    print(f"\nUpdates exported to log at: {output_csv_path}")

    print(json.dumps(updates, indent=4))


def copy_entire_folder_to_orig(folder_path, no_links=False):
    """
    Copy all files in folder_path to folder_path/orig using hard links.
    """
    orig_dir = os.path.join(folder_path, "orig")
    if os.path.exists(orig_dir):
        print(f"[WARNING] orig folder already exists...skipping: {orig_dir}")
        return

    os.makedirs(orig_dir, exist_ok=True)
    for entry in os.scandir(folder_path):
        if entry.is_file():
            orig_path = os.path.join(orig_dir, entry.name)
            if not os.path.exists(orig_path):
                try:
                    os.link(entry.path, orig_path) if not no_links else shutil.copy2(
                        entry.path, orig_path)
                except OSError as e:
                    print(e)
                    print(
                        f"[ERROR] Error creating hard link for {entry.path} -> {orig_path}: {e}")
                    print(
                        "If you see operation not supported or similar error, please run with --no-links to copy files instead of linking.")
                    exit(1)
    print(f"{'Copied' if no_links else 'Linked'} {folder_path}")


# Rename a single file with the new file name
def rename_file(file_path: str, new_file_name: str):
    if not os.path.isfile(file_path):
        print(f"{file_path}: Not a file.")
        return
    dir_name = os.path.dirname(file_path)
    new_path = os.path.join(dir_name, new_file_name)

    os.rename(file_path, new_path)
    print(f"[RENAME] {file_path} > {new_path}")


def construct_intendedfor(all_data, root_directory="rawdata", discard_orig=False, partial=False):
    '''
    Constructs the intended for from scratch, moving by series number.
    '''
    print('Constructing intendedfor.')
    # Get update log
    parent_dir = os.path.dirname(os.path.abspath(root_directory.rstrip("/")))
    csv_path = os.path.join(parent_dir, 'update_log.csv')

    if not os.path.exists(csv_path):
        print(f"Update log not found: {csv_path}")

    try:
        updates_df = pd.read_csv(csv_path)
    except Exception:
        print(f"Error reading log (empty or not present): {csv_path}")
        updates_df = pd.DataFrame(columns=[
                                  'subject', 'session', 'series_desc', 'before_run', 'after_run', 'before_path', 'after_path'])

    if not discard_orig:
        print(
            'Making copies of every fmap folder that will be modified (all of them).')
        to_copy_fmaps = set()
        # Copy ALL fmap folders to orig before modifying IntendedFor
        for sub_ses, series_lst in all_data.items():
            for s_path, s_data in series_lst:
                s_desc = s_data.get('SeriesDescription', '')
                if 'DistortionMap' in s_desc:
                    fmap_folder = os.path.dirname(s_path)
                    to_copy_fmaps.add(fmap_folder)

        for path in sorted(to_copy_fmaps):
            copy_entire_folder_to_orig(path, no_links=True)

    def modify_fmap(json_path, new_intended):
        '''
        Modify a single fmap intended for
        '''
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            intended_for = data.get('IntendedFor', [])

            if not isinstance(intended_for, list):
                print('ERROR: fmap_json does not have intendedFor at:', json_path)
                return

            data['IntendedFor'] = new_intended

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            print(f"Error processing {json_path}: {e}")

    '''
    Loop through all subjects and construct intended for based on series received after
    the current fmaps but before the next pair of fmaps.
    '''
    total_ses = len(all_data)
    curr_ses = 0

    # Construct intended fors
    for sub_ses, series_lst in all_data.items():
        # Skip if this sub_ses is already finished, but only if partial is True
        sub_ses_str = f"[{root_directory}]IntendedFor({sub_ses[0]}/{sub_ses[1]})"
        if partial:
            if sub_ses_str in cache and cache.get(sub_ses_str):
                print(f'Skipping {sub_ses_str}')
                continue

        # Stores the fmap pair in this session. Key is the pair/run number (1st pair, 2nd pair, etc.)
        # Val is a 3-tuple. First 2 entries are the series (path, data), 3rd entry is the range of series number
        # they apply to (series after them but not past the next pair of maps)
        # 1 -> ((path, data), (path, data), [range eg. 4-2])
        fmap_pairs = {}
        fmap_list = []
        # Collect all fmap (AP/PA) in order
        for s_path, s_data in series_lst:
            if s_data.get('SeriesDescription') in ['DistortionMap_AP', 'DistortionMap_PA']:
                fmap_list.append((s_path, s_data))

        # Pair up AP/PA fmaps (assuming they alternate) into fmap_pairs
        fmap_pair_count = 0
        i = 0
        while i < len(fmap_list) - 1:
            ap = fmap_list[i]
            pa = fmap_list[i + 1]
            if ap[1].get('SeriesDescription') == 'DistortionMap_AP' and pa[1].get('SeriesDescription') == 'DistortionMap_PA':
                fmap_pair_count += 1
                fmap_pairs[fmap_pair_count] = (
                    ap, pa, None)  # range to be filled below
                i += 2
            else:
                i += 1  # skip to next if not a valid pair

        # Determine the range of series numbers each pair applies to
        fmap_pair_keys = sorted(fmap_pairs.keys())
        for i, key in enumerate(fmap_pair_keys):
            ap, pa, _ = fmap_pairs[key]  # get the pair

            # Starting series # being 1 more than the fmaps
            start_series = max(ap[1].get('SeriesNumber', 0),
                               pa[1].get('SeriesNumber', 0))
            start_series += 1

            # Find next pair (if not to the end) and set upper range
            if i + 1 < len(fmap_pair_keys):
                next_ap, next_pa, _ = fmap_pairs[fmap_pair_keys[i + 1]]
                end_series = min(next_ap[1].get(
                    'SeriesNumber', 9999), next_pa[1].get('SeriesNumber', 9999)) - 1
            else:
                end_series = 9999  # until end
            fmap_pairs[key] = (ap, pa, (start_series, end_series))

        # Find any run # updates for fmap paths and make the changes internally
        for key, (ap, pa, range) in fmap_pairs.items():
            # Check for AP update
            ap_update = updates_df[updates_df['before_path'] == ap[0]]
            if not ap_update.empty:
                ap = (ap_update['after_path'].values[0], ap[1])

            # Check for PA update
            pa_update = updates_df[updates_df['before_path'] == pa[0]]
            if not pa_update.empty:
                pa = (pa_update['after_path'].values[0], pa[1])

            fmap_pairs[key] = (ap, pa, range)

        # For each fmap pair, find all series in the range and update IntendedFor
        for key, (ap, pa, range) in fmap_pairs.items():
            intended_for = []
            for s_path, s_data in series_lst:
                s_num = s_data.get('SeriesNumber', 0)
                s_desc = s_data.get('SeriesDescription', '')

                # If this series is within range and not an fmap, dwi, or SBRef
                if (
                    range[0] <= s_num <= range[1]
                    and not 'DistortionMap' in s_desc
                    and not 'dMRI' in s_desc
                    and not 'SBRef' in s_desc
                ):
                    rel_path = os.path.relpath(s_path, start=root_directory)

                    # Check update log and replace with run-X updated path if present
                    # Use only relative path for comparison
                    update_match = updates_df[updates_df['before_path'].apply(
                        lambda p: os.path.relpath(p, start=root_directory) == rel_path)]

                    if not update_match.empty:
                        updated_rel_path = os.path.relpath(
                            update_match['after_path'].values[0], start=root_directory)
                        rel_path = updated_rel_path

                    rel_path = rel_path.replace('.json', '.nii.gz')
                    intended_for.append(f'bids::{rel_path}')
            # Update both AP and PA fmap jsons
            modify_fmap(ap[0], intended_for)
            modify_fmap(pa[0], intended_for)

        curr_ses += 1
        percent_complete = (curr_ses / total_ses) * 100 if total_ses else 0
        print(
            f"({curr_ses}/{total_ses} : {percent_complete:.1f}%) Finished {sub_ses_str}")
        if partial:
            cache.set(sub_ses_str, True)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "AMPSCZ NDA-3 BIDS re-format tool. Please run this script in the same parent folder "
            "with your rawdata folder, or specify another path using the flag. By default, this "
            "script will keep original files in a subfolder orig/. Run with the --fix flag to run all sequences. "
            "If you run with --discard-orig, the original files will be overwritten."
        ),
        prog="update_bids.py",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.prog = "update_bids.py"
    parser.title = "BIDS Correction Tool"

    parser.add_argument("--fix", action="store_true", default=False,
                        help="Run all corrections: fix run numbers and fix IntendedFor fields in fMaps.")
    parser.add_argument("--path", default="rawdata", required=False,
                        help="Specify a path to the rawdata folder containing subject files.")
    parser.add_argument("--discard-orig", action="store_true", default=False,
                        help="Instead of copying the original file into an orig folder, this will (!) DELETE (!) old files.")
    parser.add_argument("--cache", action="store_true", default=False,
                        help="Store already processed subjects if the script is interrupted on a large set.")
    parser.add_argument("--log-only", action="store_true", default=False,
                        help="Generate only the update log for run-# changes (update_log.csv) and exit.")
    parser.add_argument("--skip-log", action="store_true", default=False,
                        help="Do not generate the log by default (only useful if log already generated).")
    parser.add_argument("--only-intendedfor", action="store_true", default=False,
                        help="Run ONLY the IntendedFor fix functions.")
    parser.add_argument("--no-links", action="store_true", default=False,
                        help="Do NOT create hard links for run-# fixes; copy full files instead.")
    parser.add_argument("--threads", type=int, default=8,
                        help="Number of threads to use for multi-threaded pulling operation. Only for pulling json data.")

    args = parser.parse_args()

    if not args.log_only and not args.fix and not args.only_intendedfor:
        parser.print_help()
        print('At least one action must be specified. Please see above for options.')
        exit(1)
        return

    if args.discard_orig:
        confirm = input(
            "\n(!!!) This will delete/modify files. To continue, type 'delete': ").strip().lower()
        if confirm != "delete":
            print("Aborting script.")
            exit(0)
            return

    if args.cache:
        global cache
        cache = dc.Cache('cache')

    all_data = pull_series_info(
        root_dir=args.path, partial=args.cache, threads=args.threads)
    # Sort all_data by key (sub_ses)
    all_data = dict(sorted(all_data.items(), key=lambda x: x[0]))

    if args.log_only:
        generate_log(all_data=all_data, root_directory=args.path)
        return

    if args.only_intendedfor:
        construct_intendedfor(
            all_data=all_data, root_directory=args.path, discard_orig=args.discard_orig, partial=args.cache)
        return

    if args.fix:
        if not args.skip_log:
            generate_log(all_data=all_data, root_directory=args.path)
        rename_run_num(root_directory=args.path,
                       discard_orig=args.discard_orig, no_links=args.no_links)
        construct_intendedfor(
            all_data=all_data, root_directory=args.path, discard_orig=args.discard_orig, partial=args.cache)
        return


if __name__ == "__main__":
    main()
