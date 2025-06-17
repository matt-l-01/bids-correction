import os
import json


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

            session_key = f"{subject}_{session}"
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
                                json_data_list.append(json_data)
                        except Exception as e:
                            print(f"Failed to read {file_path}: {e}")

            # Store all json data in the dictionary
            data_by_session[session_key] = json_data_list

    return data_by_session


# Example usage:
root_directory = "test_rawdata"
all_data = read_all_json_by_session(root_directory)
print(len(all_data))
