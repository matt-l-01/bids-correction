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

cache = {}


def rename_run_num(root_directory="rawdata", modify_in_place=False):
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

    for _, row in updates_df.iterrows():
        old_json_path = row["before_path"]
        new_json_path = row["after_path"]

        # Rename JSON file
        rename_file(old_json_path, os.path.basename(
            new_json_path), modify=modify_in_place)

        # Handle the NIfTI file: replace .json with .nii.gz
        old_nii_path = old_json_path.replace(".json", ".nii.gz")
        new_nii_path = new_json_path.replace(".json", ".nii.gz")

        if os.path.exists(old_nii_path):
            rename_file(old_nii_path, os.path.basename(
                new_nii_path), modify=modify_in_place)
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


def pull_series_info(root_dir, partial=False):
    print('Pulling series info.')

    series_total = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
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
                                f"{session_key[0]}/{session_key[1]}")
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
                    cache.set(f'{session_key[0]}/{session_key[1]}', json_data)
                print(
                    f"({series_complete}/{series_total} : {percent_complete:.1f}%) Pulled {file_path}")

    session_data_final = {}

    # Add all the cached data first
    for key in all_keys:
        key_str = f"{key[0]}/{key[1]}"
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
    updates_df.to_csv(output_csv_path, index=False)
    print(f"\nUpdates exported to log at: {output_csv_path}")

    print(json.dumps(updates, indent=4))


# Rename a single file with the new file name
def rename_file(file_path: str, new_file_name: str, modify: bool = False):
    if not os.path.isfile(file_path):
        print(f"{file_path}: Not a file.")
        return
    dir_name = os.path.dirname(file_path)
    if modify:
        new_path = os.path.join(dir_name, new_file_name)
        os.rename(file_path, new_path)
        print(f"[RENAME] {file_path} > {new_path}")
    else:
        # Create 'changes' directory within the same folder if it doesn't exist
        changes_dir = os.path.join(dir_name, "changes")
        os.makedirs(changes_dir, exist_ok=True)

        base, ext = os.path.splitext(new_file_name)
        if ext == ".gz":  # handle .nii.gz
            base2, ext2 = os.path.splitext(base)
            new_file_name = f"{base2}{ext2}{ext}"
        else:
            new_file_name = f"{base}{ext}"
        new_path = os.path.join(changes_dir, new_file_name)
        shutil.copy2(file_path, new_path)
        print(f"Copied {file_path} > {new_path}")


def construct_intendedfor(all_data, root_directory="rawdata", modify_in_place=False, partial=False):
    '''
    Constructs the intended for from scratch, moving by series number.
    '''
    print('Constructing intendedfor.')
    # Get update log
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
        updates_df = pd.DataFrame(columns=[
                                  'subject', 'session', 'series_desc', 'before_run', 'after_run', 'before_path', 'after_path'])

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

            if modify_in_place:
                out_path = json_path
            else:
                # Place copy in 'changes' subdir within fmap_dir
                changes_dir = os.path.join(
                    os.path.dirname(json_path), "changes")
                os.makedirs(changes_dir, exist_ok=True)
                out_path = os.path.join(
                    changes_dir, os.path.basename(json_path))

            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            print(f"Error processing {json_path}: {e}")

    '''
    Loop through all subjects and construct intended for based on series received after
    the current fmaps but before the next pair of fmaps.
    '''
    total_ses = len(all_data)
    curr_ses = 0

    for sub_ses, series_lst in all_data.items():
        # Skip if this sub_ses is already finished, but only if partial is True
        sub_ses_str = f"IntendedFor({sub_ses[0]}/{sub_ses[1]})"
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
            "with your rawdata folder, or specify another path using the flags. By default, this "
            "script will NOT modify anything. FIRST: use the --log flag to output an xlxs files of the list of BIDS names "
            "that must be updated. Then, WITHOUT the --log flag, use the --rename and --intendedfor flags to copy the current files and make corrections. "
            "The --modify-in-place flag combined with the prior 2 flags will not make any copies and modify existing files."
        ),
        prog="update_bids.py",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.prog = "update_bids.py"
    parser.title = "BIDS Correction Tool"

    parser.add_argument("--path", default="rawdata", required=False,
                        help="Specify a path to the folder containing subject files (optional).")
    parser.add_argument("--log", action="store_true", default=False,
                        help="Generate the update log for fixes to be made (MUST BE DONE FIRST).")
    parser.add_argument("--fix", action="store_true", default=False,
                        help="Run the appropriate scripts to fix the run numbers and the intended for list.")
    parser.add_argument("--modify-in-place", action="store_true", default=False,
                        help="Instead of copying by default, this will (!) MODIFY (!) current files.")
    parser.add_argument("--skip-log", action="store_true", default=False,
                        help="This will not generate the log by default (useful when running a fix on large set)")
    parser.add_argument("--only-intendedfor", action="store_true", default=False,
                        help="This will ONLY run the intended for functions")
    parser.add_argument("--cache", action="store_true", default=False,
                        help="This will store processed subjects if the script is interrupted.")

    args = parser.parse_args()

    if not args.log and not args.fix and not args.only_intendedfor:
        print('At least one action must be specified. Try running with any of the following flags: --log or --fix')
        exit(1)
        return

    if args.modify_in_place:
        confirm = input(
            "\n(!!!) This will modify files. To continue, type 'modify': ").strip().lower()
        if confirm not in "modify":
            print("Aborting script.")
            exit(0)
            return

    if args.cache:
        global cache
        cache = dc.Cache('cache')

    all_data = pull_series_info(root_dir=args.path, partial=args.cache)

    if args.log:
        generate_log(all_data=all_data, root_directory=args.path)
        return

    if args.only_intendedfor:
        construct_intendedfor(
            all_data=all_data, root_directory=args.path, modify_in_place=args.modify_in_place, partial=args.cache)
        return

    if args.fix:
        if not args.skip_log:
            generate_log(all_data=all_data, root_directory=args.path)
        rename_run_num(root_directory=args.path,
                       modify_in_place=args.modify_in_place)
        construct_intendedfor(
            all_data=all_data, root_directory=args.path, modify_in_place=args.modify_in_place, partial=args.cache)
        return


if __name__ == "__main__":
    main()
