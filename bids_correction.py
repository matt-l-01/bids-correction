import os
import json
import re
import pandas as pd


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


root_directory = "test_rawdata"
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

            # if s_desc.startswith('dMRI_dir') and s_desc.endswith('PA_SBRef'):
            #     session_run_count['dMRI_PA_SBRef'] += 1
            #     update_run_if_needed(
            #         s[0], run_str, session_run_count['dMRI_PA_SBRef'], sub_ses)
            #     break
            # if s_desc.startswith('dMRI_dir') and s_desc.endswith('PA'):
            #     session_run_count['dMRI_PA'] += 1
            #     update_run_if_needed(
            #         s[0], run_str, session_run_count['dMRI_PA'], sub_ses)
            #     break
            # if key in s_desc:
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

# Save to Excel file
output_excel_path = 'update_log.xlsx'
updates_df.to_excel(output_excel_path, index=False)
print(f"\nUpdates exported to Excel at: {output_excel_path}")

print(json.dumps(updates, indent=4))
