from fmriprep.workflows.anatomical import init_anat_template_wf
import os
from bids import BIDSLayout

os.environ['SUBJECTS_DIR'] = '/derivatives/freesurfer'

layout = BIDSLayout('/sourcedata')

t1w = layout.get(suffix='T1w', subject='de', return_type='file')
inv2 = layout.get(suffix='MPRAGE', passing filter={ 'subject': 'sub-[12]'})

print(t1w)


wf = init_anat_template_wf(False, 8, 2)
wf.inputs.inputnode.t1w = t1w

wf.base_dir = '/workflow_folders'

wf.run()
