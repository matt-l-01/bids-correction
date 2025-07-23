# BIDS Correction Tool for AMPSCZ NDA-3 (Release 3.0)

This tool automates the correction of file and metadata inconsistencies in the AMP-SCZ Release 3.0 BIDS-formatted dataset. It is designed specifically for this release, addressing issues that can prevent compatibility with downstream tools like [fMRIPrep](https://fmriprep.org/), which can fail when fields like `run` numbers or `IntendedFor` paths are misaligned or incomplete.

## Purpose

AMP-SCZ Release 3.0 BIDS datasets often accumulate inconsistencies due to re-scans and scanner naming conventions. This script:

* **Standardizes `run-XX` numbers** in file names to follow a consistent order.
* **Renames JSON/NIfTI files** accordingly.
* **Fixes inadequate `IntendedFor` information** in `fmap/` JSON files, reconstructing the correct references for each scan. This is a critical fix for Release 3.0, where the original "IntendedFor" fields are often missing or incorrect.
* Prevents breaking tools like **fMRIPrep**, which can crash on mismatches.

## Usage

To automatically fix all run numbers and *IntendedFor* fields in your AMP-SCZ Release 3.0 BIDS dataset, simply run:

```bash
python update_bids.py --fix
```

- This will process the `rawdata` folder in the same directory as the script.
- Original files from the folder in which patches are made are moved to an `orig/` subfolder for backup. Then, updates are made to files in the correct BIDs location.
- For updates that JUST involve the run number, a hard link is created to the original files.
- For updates that modify the file contents (fmaps), a copy is created.
- The command will apply all corrections in one step.
    - Generate log of run # issues
    - Fix run numbers in filenames
    - **Fix the inadequate IntendedFor information in fMaps for AMP-SCZ Release 3.0, reconstructing the correct references from scratch**
    - Update all fMap files

## Example: Fix and Discard Original Files with Caching

To run all corrections, modify files in place, and use caching to resume interrupted runs:

```bash
python update_bids.py --fix --discard-orig --cache
```

- (! ! !) This will apply all fixes directly to your files without creating backups.
- The `--cache` flag ensures that already processed subjects/sessions are skipped if the script is interrupted and restarted.
- For use on systems that have trouble with computationally intensive tasks (...Amazon Workspace). This will save the step of pulling all json data and also save which sessions were complete, and skip them if re-run with cache again.
- The cache is stored locally in the bids-correction folder and automatically managed by the script.

You can specify a custom AMP-SCZ Release 3.0 BIDS directory with:

```bash
python update_bids.py --path /path/to/bids_data --fix
```

## Description
```bash
usage: update_bids.py [-h] [--fix] [--path PATH] [--discard-orig] [--cache] [--log] [--skip-log] [--only-intendedfor]

AMPSCZ NDA-3 BIDS re-format tool for Release 3.0. Please run this script in the same parent folder with your rawdata folder, or specify another path using the flag.
By default, this script will keep original files in a subfolder orig/. Run with the fix flag to run all sequences. If you run with --discard-orig, the
original files will be overwritten.

options:
  -h, --help          show this help message and exit
  --fix               Run the appropriate scripts to fix the run numbers and to *fix* the inadequate IntendedFor information in fmaps for AMP-SCZ Release 3.0. (default: False)
  --path PATH         Specify a path to the rawdata folder containing subject files. (default: rawdata)
  --discard-orig      Instead of copying the original file into an orig folder, this will (!) DELETE (!) old files. (default: False)
  --cache             This will store already processed subjects if the script is interrupted on a large set. (default: False)
  --log               Generate just the update log for run-# changes (for testing) (default: False)
  --skip-log          This will not generate the log by default (only useful if log already generated) (default: False)
  --only-intendedfor  This will ONLY run the IntendedFor fix functions (default: False)
  --no-links          This will NOT create hard links for run-# fixes and copy full files. (default: False)
```
## Parameters

| Functionality         | Description                                                           |
| --------------------- | --------------------------------------------------------------------- |
| `--fix`               | Runs all corrections (log, renaming, IntendedFor fix) in one step.    |
| `--log`               | Generates `update_log.xlsx`, logging files that need renaming.        |
| `--skip-log`          | Skips log generation if already present.                              |
| `--only-intendedfor`  | Only *fixes* the inadequate IntendedFor information in fmap JSON files for AMP-SCZ Release 3.0. |
| `--discard-orig`      | Applies changes directly (⚠️ WARNING: irreversible if not backed up). |
| `--cache`             | Uses diskcache to resume interrupted runs and skip processed items.    |
| `--no-links`          | Disables creation of hard links; files are copied instead.             |
| `--path`              | Modify the default root path for the BIDS file (default: rawdata)     |

## Requirements

This program was written on `Python 3.13.3`. Install required dependencies via pip:

```bash
pip install -r requirements.txt
```

## Important Notes

* **Backup your data** before running with `--discard-orig`.
* This tool assumes a consistent BIDS directory structure.
* Only BIDS fields related to `run-XX` and `IntendedFor` are modified.
* This tool is specifically designed for AMP-SCZ Release 3.0 and *fixes* the inadequate IntendedFor information in the fmaps of this release.

## File Structure Example (with orig folder)

```
bids-correction/
    rawdata/
        sub-001/
            ses-01/
                anat/
                    orig/
                        sub-001_ses-01_run-4_T1w.nii.gz
                        sub-001_ses-01_run-4_T1w.json
                    sub-001_ses-01_run-1_T1w.nii.gz
                    sub-001_ses-01_run-1_T1w.json
                fmap/
                    orig/
                        sub-001_ses-01_dir-AP_epi.json 
                    sub-001_ses-01_dir-AP_epi.json # IntendedFor field fixed for AMP-SCZ Release 3.0
```
