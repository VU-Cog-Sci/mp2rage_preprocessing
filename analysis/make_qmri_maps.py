import argparse
import nipype.pipeline.engine as pe
import nipype.interfaces.utility as niu
from utils import get_mp2rage_pars, fit_mp2rage, _pickone, get_inv
from fmriprep.interfaces import DerivativesDataSink

def main(sourcedata,
         derivatives,
         tmp_dir,
         subject,
         session=None,
         acquisition=None):


    wf_name = 'qmri_mp2rage_{}'.format(subject)
    wf = init_qmri_wf(sourcedata,
                      derivatives,
                      acquisition,
                      wf_name)
    wf.base_dir = tmp_dir

    wf.inputs.inputnode.subject = subject
    wf.inputs.inputnode.session = session
    wf.inputs.inputnode.acquisition = acquisition

    wf.run()


def init_qmri_wf(sourcedata,
                         derivatives,
                         acquisition='memp2rage',
                         name='qmri_mp2rage'):

    wf = pe.Workflow(name=name)

    inputnode = pe.Node(niu.IdentityInterface(fields=['sourcedata',
                                                      'derivatives',
                                                      'subject',
                                                      'session',
                                                      'acquisition']),
                        name='inputnode')

    inputnode.inputs.sourcedata = sourcedata
    inputnode.inputs.derivatives = derivatives

    
    get_parameters = pe.Node(niu.Function(function=get_mp2rage_pars,
                                               input_names=['sourcedata',
                                                            'subject',
                                                            'session',
                                                            'acquisition'],
                                               output_names=['mp2rage_parameters']),
                                  name='get_mp2rage_pars')

    wf.connect([(inputnode, get_parameters,
                 [('sourcedata', 'sourcedata'),
                  ('subject', 'subject'),
                  ('session', 'session'),
                  ('acquisition', 'acquisition')])])

    get_qmri = pe.Node(niu.Function(function=fit_mp2rage,
                                       input_names=['mp2rage_parameters',
                                                    'return_images'],
                                       output_names=['S0map', 't2starw', 't2starmap']),
                          name='get_qmri')

    get_qmri.inputs.return_images = ['S0map', 't2starw', 't2starmap']

    wf.connect([ (get_parameters, get_qmri, [('mp2rage_parameters', 'mp2rage_parameters')]) ])


    get_first_inversion = pe.MapNode(niu.Function(function=get_inv,
                                                  input_names=['mp2rage_parameters', 'inv', 'echo'],
                                                  output_names='inv1'),
                                     iterfield=['mp2rage_parameters'],
                                     name='get_first_inversion')

    get_first_inversion.inputs.inv = 1
    get_first_inversion.inputs.echo = 1
    wf.connect(get_parameters, 'mp2rage_parameters', get_first_inversion, 'mp2rage_parameters')

    rename = pe.Node(niu.Rename(use_fullpath=True), name='rename')
    rename.inputs.format_string = '%(path)s/sub-%(subject_id)s_ses-%(session)s_MPRAGE.nii.gz'
    rename.inputs.parse_string = '(?P<path>.+)/sub-(?P<subject_id>.+)_ses-(?P<session>.+)_acq-.+_MPRAGE.nii(.gz)?'


    ds_S0 = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='qmri_memp2rages',
                                         suffix='S0',
                                         space='average'),
                                         name='ds_S0')
    wf.connect(get_first_inversion, ('inv1', _pickone), rename, 'in_file')
    wf.connect(rename, 'out_file', ds_S0, 'source_file')
    wf.connect(get_qmri, 'S0map', ds_S0, 'in_file')

    ds_t2starmap = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='qmri_memp2rages',
                                         suffix='t2starmap',
                                         space='average'),
                                         name='ds_t2starmap')
    wf.connect(rename, 'out_file', ds_t2starmap, 'source_file')
    wf.connect(get_qmri, 't2starmap', ds_t2starmap, 'in_file')

    ds_t2starw = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='qmri_memp2rages',
                                         suffix='t2starw',
                                         space='average'),
                                         name='ds_t2starw')
    wf.connect(rename, 'out_file', ds_t2starw, 'source_file')
    wf.connect(get_qmri, 't2starw', ds_t2starw, 'in_file')

    return wf

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("subject", 
                        type=str,
                        help="subject to process")
    parser.add_argument('session', 
                        nargs='?', 
                        default=None,
                        help="subject to process")

    parser.add_argument('acquisition', 
                        nargs=1, 
                        default='memp2rage',
                        help="Acquisition to process")

    args = parser.parse_args()

    main('/sourcedata', 
         '/derivatives',
         tmp_dir='/workflow_folders',
         subject=args.subject,
         session=args.session,
         acquisition=args.acquisition)

