# BIDS Correction Tool for AMPSCZ NDA-3 (Release 3.0)

This tool automates the correction of file and metadata inconsistencies in the AMP-SCZ Release 3.0 BIDS-formatted dataset. It is designed specifically for this release, addressing issues that can prevent compatibility with downstream tools like [fMRIPrep](https://fmriprep.org/), which can fail when fields like `run` numbers or `IntendedFor` paths are misaligned or incomplete.

## Purpose

AMP-SCZ NDA Release 3.0 BIDS datasets often accumulate inconsistencies due to re-scans and scanner naming conventions. This script:

* **Standardizes `run-XX` numbers** in file names to follow a consistent order.
* **Renames JSON/NIfTI files** accordingly.
* **Fixes inadequate `IntendedFor` information** in the `fmap/` JSON files, reconstructing the correct references for each scan. This is a critical fix for Release 3.0, where the original "IntendedFor" fields are often missing or incorrect.
* Prevents breaking tools like **fMRIPrep**, which can crash on mismatches.

## Usage

* Specifically designed for **AMP-SCZ Release 3.0** only

To automatically fix all run numbers and *IntendedFor* fields in your AMP-SCZ Release 3.0 BIDS dataset, simply run:

```bash
python update_ampscz_bids.py --fix
```

- This will process the `rawdata` folder in the same directory as the script.
- By default, the original files from the folder in which patches are made are moved to an `orig/` subfolder for backup. Then, updates are made to files in the standard BIDs directories.
- For updates that JUST involve a change of the run number in the file name, a hard link is created to the original file.
- For updates that modify the file contents (i.e., fmap JSONs), a copy is created and then modified.
- The command will apply all corrections in one step.
    - Generate log (`update_log.csv`) of run # issues
    - Fix run numbers in file names (applies to `anat/`, `func/`, `fmap/`, and `dwi/` contents)
    - **Fix the inadequate IntendedFor information in fmap JSONs for AMP-SCZ Release 3.0, reconstructing the correct references from scratch**
    - Update all fmap JSONs

## Examples

### Fix and Discard Original Files with Caching

To run all corrections, discard the original files, and use caching to resume interrupted runs:

```bash
python update_ampscz_bids.py --fix --discard-orig --cache
```

- (! ! !) This will apply all fixes without creating backups.
- The `--cache` flag may be beneficial on systems that have trouble with computationally intensive tasks, in which the script might get interrupted and need to be restarted (e.g., Amazon Workspaces). It generates a file to keep track of which sessions were completed, and then skips those sessions if the script is re-run with the `--cache` flag again.
- The cache is stored locally in the bids-correction folder and automatically managed by the script.

### Data in a different location from the script

You can specify a custom AMP-SCZ Release 3.0 BIDS directory with:

```bash
python update_ampscz_bids.py --path /path/to/bids_data --fix
```

## Description
```bash
usage: update_ampscz_bids.py [-h] [--fix] [--path PATH] [--discard-orig] [--cache] [--log-only] [--skip-log] [--only-intendedfor] [--no-links]

AMPSCZ NDA-3 BIDS re-format tool. Please run this script in the same parent folder with your rawdata folder, or specify another path using the --path flag. By default, this script
will keep a copy of the original files in a subfolder named "orig/". Run with the --fix flag to run all corrections. If you run with --discard-orig, no copy of the original files will be preserved.

options:
  -h, --help          show this help message and exit
  --fix               Run all corrections: fix run numbers in file name and fix IntendedFor fields in fmap JSONs. (default: False)
  --path PATH         Specify a path to the rawdata folder containing subject files. (default: rawdata)
  --discard-orig      This will (!) DELETE (!) the original copy of the files that is otherwise created. (default: False)
  --cache             Keep a record of already processed sessions, in case the script is interrupted. (default: False)
  --log-only          Generate only the update log for run-# changes (update_log.csv) and exit. (default: False)
  --skip-log          Do not generate the log by default (only useful if log already generated). (default: False)
  --only-intendedfor  Run ONLY the IntendedFor fix functions. (default: False)
  --no-links          Do NOT create hard links for run-# fixes; copy full files instead. (default: False)
  --threads THREADS   Number of threads to use for multi-threaded pulling operation. Only for pulling json data. (default: 8)
```

## Requirements

This program was written on `Python 3.13.3`. Install required dependencies via pip:

```bash
pip install -r requirements.txt
```

## Important Notes

* This tool is specifically designed for **AMP-SCZ Release 3.0** only and *fixes* the inadequate IntendedFor information in the fmaps of this release.
* If you run with the `--discard-orig` flag, strongly consider **backing up your data** before running.
* This tool assumes a standard BIDS directory structure.

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
