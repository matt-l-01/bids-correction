#!/usr/bin/env python3
from collections import defaultdict
import shutil
import os
import json
import argparse
import re
import pandas as pd


def rename_all_files(root_directory="rawdata", modify_in_place=False):
    parent_dir = os.path.dirname(os.path.abspath(root_directory.rstrip("/")))
    csv_path = os.path.join(parent_dir, 'update_log.csv')

    if not os.path.exists(csv_path):
        print(f"CSV log not found: {csv_path}")
        return
    
    updates_df = pd.read_csv(csv_path)

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


def update_dmap_intendedfor(root_directory='rawdata', modify_in_place=False):
    parent_dir = os.path.dirname(os.path.abspath(root_directory.rstrip("/")))
    csv_path = os.path.join(parent_dir, 'update_log.csv')

    if not os.path.exists(csv_path):
        print(f"CSV log not found: {csv_path}")
        return
    
    updates_df = pd.read_csv(csv_path)

    # Group updates by subject
    subject_updates = defaultdict(list)
    for _, row in updates_df.iterrows():
        before_rel = os.path.relpath(row['before_path'].replace(
            '.json', '.nii.gz'), start=root_directory)
        after_rel = os.path.relpath(row['after_path'].replace(
            '.json', '.nii.gz'), start=root_directory)

        # Extract subject
        subject = row['subject']
        session = row['session']
        subject_updates[(subject, session)].append((before_rel, after_rel))

    for sub_ses, changes in subject_updates.items():
        subject_dir = os.path.join(root_directory, sub_ses[0])
        fmap_dir = os.path.join(root_directory, sub_ses[0], sub_ses[1], 'fmap')

        if not os.path.exists(fmap_dir):
            continue

        for fname in os.listdir(fmap_dir):
            if fname.endswith('.json'):
                json_path = os.path.join(fmap_dir, fname)

                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    intended_for = data.get('IntendedFor', [])
                    if not isinstance(intended_for, list):
                        continue

                    updated = False
                    new_intended_for = []
                    for entry in intended_for:
                        clean_entry = entry.replace('bids::', '')
                        new_entry = clean_entry

                        for old_rel, new_rel in changes:
                            if clean_entry == old_rel:
                                print(
                                    f"[JSON] Updating {fname}: {clean_entry} > {new_rel}")
                                new_entry = new_rel
                                updated = True
                                break  # Avoid double replacements

                        new_intended_for.append(new_entry)

                    if updated:
                        data['IntendedFor'] = new_intended_for

                        if modify_in_place:
                            out_path = json_path
                        else:
                            # Place copy in 'changes' subdir within fmap_dir
                            changes_dir = os.path.join(fmap_dir, "changes")
                            os.makedirs(changes_dir, exist_ok=True)
                            out_path = os.path.join(changes_dir, os.path.basename(
                                json_path).replace('.json', '_copy.json'))

                        with open(out_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2)

                except Exception as e:
                    print(f"Error processing {json_path}: {e}")


def read_all_json_by_session(root_dir):
    data_by_session = {}

    # Iterate through all subject folders
    for subject in os.listdir(root_dir):
        subject_path = os.path.join(root_dir, subject)
        if not os.path.isdir(subject_path):
            continue

        # Iterate through session folders in each subject folder
        for session in os.listdir(subject_path):
            session_path = os.path.join(subject_path, session)
            if not os.path.isdir(session_path):
                continue

            session_key = (subject, session)
            json_data_list = []

            # Iterate through the 4 folders inside each session
            for subfolder in os.listdir(session_path):
                subfolder_path = os.path.join(session_path, subfolder)
                if not os.path.isdir(subfolder_path):
                    continue

                # Read all JSON files in the current subfolder
                for file_name in os.listdir(subfolder_path):
                    if file_name.endswith(".json"):
                        file_path = os.path.join(subfolder_path, file_name)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                json_data = json.load(f)
                                json_data_list.append((file_path, json_data))
                        except Exception as e:
                            print(f"Failed to read {file_path}: {e}")

            # Store all json data in the dictionary
            data_by_session[session_key] = json_data_list

    return data_by_session


def generate_excel(root_directory="rawdata"):
    all_data = read_all_json_by_session(root_directory)
    updates = []

    for sub_ses, series_lst in all_data.items():
        # Sort by series number
        series_lst = sorted(series_lst, key=lambda x: x[1].get("SeriesNumber"))

        print('subject_session : series number : before run # : after run # : series description')

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
    print(f"\nUpdates exported to CSV at: {output_csv_path}")

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
            new_file_name = f"{base2}_new{ext2}{ext}"
        else:
            new_file_name = f"{base}_new{ext}"
        new_path = os.path.join(changes_dir, new_file_name)
        shutil.copy2(file_path, new_path)
        print(f"Copied {file_path} > {new_path}")

def add_opposite_intended(root_directory="rawdata", modify_in_place=False):
    pass


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
    parser.add_argument("--rename", action="store_true", default=False,
                        help="Edit file names to correct BIDS format.")
    parser.add_argument("--intendedfor", action="store_true", default=False,
                        help="Edit IntendedFor field in JSON fmaps.")
    parser.add_argument("--modify-in-place", action="store_true", default=False,
                        help="Instead of copying by default, this will (!) MODIFY (!) current files.")

    args = parser.parse_args()

    if not args.log and not args.rename and not args.intendedfor:
        print('At least one action must be specified. Try running with any of the following flags: --log, --rename, --intendedfor')
        exit(1)
        return

    if args.modify_in_place:
        confirm = input(
            "\n(!!!) This will modify files. To continue, type 'modify': ").strip().lower()
        if confirm not in "modify":
            print("Aborting script.")
            exit(0)
            return

    if args.log:
        generate_excel(args.path)

    if args.rename:
        rename_all_files(root_directory=args.path, modify_in_place=args.modify_in_place)
        update_dmap_intendedfor(
            root_directory=args.path, modify_in_place=args.modify_in_place)

    if args.intendedfor:
        add_opposite_intended(root_directory=args.path, modify_in_place=args.modify_in_place)


if __name__ == "__main__":
    main()
