# mp2rage_preprocessing

This is the preprocessing workflow of the Knapen lab at the Spinoza Centre for
Neuroimaging in Amsterdam, to get Freesurfer and CBS-tools segmentations of a combined
 MP2RAGE and MEMP2RAGE protocol.

# Installation
1) Install Docker
2) Install docker-compose
3) Clone this repository

# Running
Set environment variables 
 * `$SOURCEDATA` to your folder with data
 * `$DERIVATIVES` to the folder where you want the output of the pipeline to go
 * `$FREESURFER_HOME` to the Freesurfer folder with a license.txt-file

Then go to the folder where you cloned the repo and just run
`./go`

You will now be in an virtual environment with ZSH, where you can run all the scripts.

# Step 1: combining the two scans

`python /src/combine_scans.py <SUBJECT> <SESSION>`

 * Calculates UNI, T1map, T2\*-map, S0-map.
 * Registers the T1w-images of the mp2rage to the me-mp2rage space
 * Makes average images in this common space
	 * `/derivatives/average_space`

# Step 2: masking the image

`python /src/mask_averages <SUBJECT> <SESSION>`

 * Makes a brain mask using
   * Inhomogeniety-corrected average INV2 and BET
   * Dura filters of CBS-tools
   * Manual mask, of non-brain matter (sagital sinus)
     * Should be stored in `/derivatives/manual_nonbrainmask/sub-<SUBJECT>/ses-<SESSION>/sub-<SUBJECT>_ses-<SESSION>_manual_nonbrainmask.nii.gz`
 * Outputs to `/derivatives/masked_averages` and `/derivatives/sourcedata_fmriprep`

# Step 3: fmriprep
To be implemented (inside this docker or outside this docker?)

3 experiments to run:
 * Only average T1w
 * Average T1w and average INV2 as FLAIR
 * Average T1w and average T1map as T2w
