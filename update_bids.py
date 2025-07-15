#!/usr/bin/env python3
from collections import defaultdict
import shutil
import os
import json
import argparse
import re
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed


def read_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return (file_path, data)
    except Exception as e:
        print(f"Failed to read {file_path}: {e}")
        return None


def rename_run_num(root_directory="rawdata", modify_in_place=False):
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


def pull_series_info(root_dir):
    data_by_session = {}
    json_paths_by_session = defaultdict(list)

    # Step 1: Collect all JSON file paths grouped by (subject, session)
    for subject in os.listdir(root_dir):
        subject_path = os.path.join(root_dir, subject)
        if not os.path.isdir(subject_path):
            continue

        for session in os.listdir(subject_path):
            session_path = os.path.join(subject_path, session)
            if not os.path.isdir(session_path):
                continue

            session_key = (subject, session)

            for subfolder in os.listdir(session_path):
                subfolder_path = os.path.join(session_path, subfolder)
                if not os.path.isdir(subfolder_path):
                    continue

                for file_name in os.listdir(subfolder_path):
                    if file_name.endswith(".json"):
                        file_path = os.path.join(subfolder_path, file_name)
                        json_paths_by_session[session_key].append(file_path)

    # Step 2: Use multithreading to load JSON data
    with ThreadPoolExecutor(max_workers=16) as executor:
        future_to_key = {}
        for session_key, paths in json_paths_by_session.items():
            for path in paths:
                future = executor.submit(read_json_file, path)
                future_to_key[future] = session_key

        for future in as_completed(future_to_key):
            session_key = future_to_key[future]
            result = future.result()
            if result:
                data_by_session.setdefault(session_key, []).append(result)

    # Step 3: Sort by SeriesNumber
    for session_key in data_by_session:
        data_by_session[session_key].sort(
            key=lambda x: x[1].get("SeriesNumber"))

    return data_by_session


def generate_log(all_data, root_directory="rawdata"):
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


def construct_intendedfor(all_data, root_directory="rawdata", modify_in_place=False):
    '''
    Constructs the intended for from scratch, moving by series number.
    '''

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
    for sub_ses, series_lst in all_data.items():

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
                    # Relative path from root_directory
                    rel_path = os.path.relpath(
                        path=s_path, start=root_directory)

                    # Check update log and replace with run-X updated path if present
                    if updates_df['before_path'].str.contains(rel_path, na=False).any():
                        rel_path = updates_df.loc[updates_df['before_path'].str.contains(
                            f'{root_directory}/{rel_path}'), 'after_path'].values[0]
                        rel_path = os.path.join(
                            *rel_path.split(os.sep)[1:])  # remove rawdata

                    rel_path = rel_path.replace('.json', '.nii.gz')
                    print(rel_path)
                    intended_for.append(f'bids::{rel_path}')
                # Update both AP and PA fmap jsons
                modify_fmap(ap[0], intended_for)
                modify_fmap(pa[0], intended_for)


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

    args = parser.parse_args()

    if not args.log and not args.fix:
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

    all_data = pull_series_info(root_dir=args.path)

    if args.log:
        generate_log(all_data=all_data, root_directory=args.path)

    if args.fix:
        if not args.skip_log:
            generate_log(all_data=all_data, root_directory=args.path)
        rename_run_num(root_directory=args.path,
                       modify_in_place=args.modify_in_place)
        construct_intendedfor(
            all_data=all_data, root_directory=args.path, modify_in_place=args.modify_in_place)


if __name__ == "__main__":
    main()
