from fmriprep.workflows.anatomical import init_anat_template_wf
import os
from bids import BIDSLayout
from nipype.interfaces import ants
import nipype.pipeline.engine as pe
from fmriprep.interfaces import DerivativesDataSink

os.environ['SUBJECTS_DIR'] = '/derivatives/freesurfer'

layout = BIDSLayout('/sourcedata')

t1w = layout.get(suffix='T1w', subject='de', return_type='file',
                 acquisition=['mp2rage', 'memp2rage'])
inv2 = layout.get(suffix='MPRAGE', inversion=2, 
                  acquisition='mp2rage',return_type='file',
                  subject='de', part='mag')
inv2 += layout.get(suffix='MPRAGE', inversion=2, 
                  acquisition='memp2rage',return_type='file',
                  subject='de', echo=1, part='mag')

print(t1w)
print(inv2)

wf = init_anat_template_wf(False, 8, 2)
wf.inputs.inputnode.t1w = t1w

wf.base_dir = '/workflow_folders'

transformer = pe.MapNode(ants.ApplyTransforms(interpolation='LanczosWindowedSinc'),
                         iterfield=['input_image', 'transforms'],
                      name='transformer')
transformer.inputs.input_image = inv2

wf.connect(wf.get_node('outputnode'), 'template_transforms', transformer, 'transforms')
wf.connect(wf.get_node('outputnode'), 't1_template', transformer, 'reference_image')

ds_inv2 = pe.MapNode(DerivativesDataSink(base_directory='/derivatives',
                                         keep_dtype=False,
                                         out_path_base='inv2_in_t1w_space',
                                         suffix='MPRAGE',
                                         space='average'),
                     iterfield=['in_file', 'source_file'],
                     name='ds_inv2')
ds_inv2.inputs.source_file = inv2
wf.connect(transformer, 'output_image', ds_inv2, 'in_file')

ds_template = pe.Node(DerivativesDataSink(base_directory='/derivatives',
                                         keep_dtype=False,
                                         out_path_base='inv2_in_t1w_space',
                                         suffix='T1w',
                                         space='average'),
                     iterfield=['in_file', 'source_file'],
                     name='ds_template')
ds_template.inputs.source_file = t1w[0]
wf.connect(wf.get_node('outputnode'), 't1_template', ds_template, 'in_file')


wf.run()
