# BIDS Correction Tool for AMPSCZ NDA-3

This tool automates the correction of file and metadata inconsistencies in a BIDS-formatted dataset. It helps ensure compatibility with downstream tools like [fMRIPrep](https://fmriprep.org/), which can fail when fields like `run` numbers or `IntendedFor` paths are misaligned.

## Purpose

BIDS datasets often accumulate inconsistencies due to re-scans and scanner naming conventions. This script:

* **Standardizes `run-XX` numbers** in file names to follow a consistent order.
* **Renames JSON/NIfTI files** accordingly.
* **Updates `IntendedFor` fields** in `fmap/` JSON files to match the new paths.
* Prevents breaking tools like **fMRIPrep**, which can crash on mismatches.



## Paramaters

| Functionality       | Description                                                           |
| ------------------- | --------------------------------------------------------------------- |
| `--log`             | Generates `update_log.xlsx`, logging files that need renaming.        |
| `--rename`          | Renames all affected `.nii.gz` and `.json` files based on the log.    |
| `--intendedfor`     | Updates `IntendedFor` in fmap JSON files based on renames.            |
| `--modify-in-place` | Applies changes directly (⚠️ WARNING: irreversible if not backed up). |
| `--path`            | Modify the default root path for the BIDs file (default: rawdata)     |

## Requirements

Install required dependencies via pip:

```bash
pip install -r requirements.txt
```

## Usage

Run the tool from the root directory containing your `rawdata/` BIDS folder:

```bash
# Step 1: Generate update log for files with errors
python update_bids.py --log

# Step 2: Make changes after copying the files. Note: new files will be placed within a 'changed' directory inside the subfolder (anat, dwi, func, fmap)
python update_bids.py --rename --intendedfor

# Apply rename and intendfor fixes in-place. WARNING: this will not provide a backup of the old file names or intendedFor values.
python update_bids.py --rename --intendedfor --modify-in-place
```

You can specify a custom BIDS directory with:

```bash
python update_bids.py --path /path/to/bids_data
```



## Important Notes

* **Backup your data** before running with `--modify-in-place`.
* This tool assumes a consistent BIDS directory structure.
* Only BIDS fields related to `run-XX` and `IntendedFor` are modified.


## File Structure Example

```
parent_folder/
    rawdata/
        sub-001/
            ses-01/
            anat/
                sub-001_ses-01_T1w.nii.gz
                sub-001_ses-01_T1w.json
            fmap/
                sub-001_ses-01_dir-AP_epi.json
    update_bids.py
    update_log.xlsx

```