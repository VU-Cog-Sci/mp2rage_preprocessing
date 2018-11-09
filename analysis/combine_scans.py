import argparse
from bids import BIDSLayout
import re
import pandas as pd
import os
import glob
import json
import numpy as np
import pymp2rage
import nipype.pipeline.engine as pe
import nipype.interfaces.utility as niu
from nipype.interfaces import fsl

def main(sourcedata,
         derivatives,
         tmp_dir,
         subject,
         session=None):

    if session is None:
        session = '.*'

    wf = init_combine_mp2rage_wf()
    wf.base_dir = '/workflow_folders'


    wf.inputs.inputnode.sourcedata = sourcedata
    wf.inputs.inputnode.subject = subject
    wf.inputs.inputnode.session = session
    wf.inputs.inputnode.acquisition = ['memp2rage', 'mp2rage']

    wf.run()

def init_combine_mp2rage_wf(name='combine_mp2rages',
                            n_mp2rages=2):
    wf = pe.Workflow(name=name)

    inputnode = pe.Node(niu.IdentityInterface(fields=['sourcedata',
                                                      'subject',
                                                      'session',
                                                      'acquisition']),
                        name='inputnode')

    
    get_parameters = pe.MapNode(niu.Function(function=get_mp2rage_pars,
                                               input_names=['sourcedata',
                                                            'subject',
                                                            'session',
                                                            'acquisition'],
                                               output_names=['mp2rage_parameters']),
                                  iterfield=['acquisition'],
                                  name='get_mp2rage_pars')

    wf.connect([(inputnode, get_parameters,
                 [('sourcedata', 'sourcedata'),
                  ('subject', 'subject'),
                  ('session', 'session'),
                  ('acquisition', 'acquisition')])])

    make_t1w = pe.MapNode(niu.Function(function=fit_mp2rage,
                                       input_names=['mp2rage_parameters'],
                                       output_names=['t1w_uni', 't1map']),
                          iterfield=['mp2rage_parameters'],
                          name='make_t1w')

    wf.connect([ (get_parameters, make_t1w, [('mp2rage_parameters', 'mp2rage_parameters')]) ])

    split = pe.Node(niu.Split(splits=[1, n_mp2rages-1]),
                    name='split')

    wf.connect(make_t1w, 't1w_uni', split, 'inlist')

    flirt = pe.MapNode(fsl.FLIRT(dof=6),
                       iterfield=['in_file'],
                       name='flirt')

    wf.connect(split, ('out1', _pickone), flirt, 'reference')
    wf.connect(split, 'out2', flirt, 'in_file')

    merge_t1w_lists = pe.Node(niu.Merge(2),
                              name='merge_t1w_lists')
    wf.connect(split, 'out1', merge_t1w_lists, 'in1')
    wf.connect(flirt, 'out_file', merge_t1w_lists, 'in2')

    merge_t1w_niftis = pe.Node(fsl.Merge(dimension='t'),
                               name='merge_t1w_niftis')
    wf.connect(merge_t1w_lists, 'out', merge_t1w_niftis, 'in_files')

    mean_t1w = pe.Node(fsl.MeanImage(dimension='T'),
                       name='mean_t1w')
    wf.connect(merge_t1w_niftis, 'merged_file', mean_t1w, 'in_file')

    get_invs2 = pe.Node(niu.Function(function=get_inv2,
                                     input_names=['mp2rage_parameters'],
                                     ouput_names=['inv2']),
                        iterfield=['mp2rage_parameters'],
                        name='get_invs2')


    return wf

def _pickone(input):
    return input[0]

def get_inv2(mp2rage_parameters):
    inv2 = mp2rage_parameters['inv2']

    if type() is list:
        return inv2[0]
    else:
        return inv2

def fit_mp2rage(mp2rage_parameters):
    import pymp2rage
    import os

    if 'echo_times' in mp2rage_parameters:
        mp2rage = pymp2rage.MEMP2RAGE(**mp2rage_parameters)
    else: 
        mp2rage = pymp2rage.MP2RAGE(**mp2rage_parameters)

    
    files = mp2rage.write_files(path=os.getcwd())

    return files['t1w_uni'], files['t1map']


def get_mp2rage_pars(sourcedata, subject, session, acquisition):
    import pandas as pd
    from bids import BIDSLayout
    import re
    import os
    import glob
    import json
    import numpy as np

    layout = BIDSLayout(sourcedata)

    mp2rage_files = layout.get(subject=subject, 
                               session=session, 
                               acquisition=acquisition,
                               suffix='MPRAGE', 
                               extensions=['.nii', '.nii.gz'])

    reg = re.compile('.*/sub-(?P<subject>.+)_ses-(?P<session>.+)_acq-(?P<acquisition>.+)_inv-(?P<inv>[0-9]+)(_echo-(?P<echo>[0-9]+))?(_part-(?P<part>.+))?_MPRAGE.(?P<extension>nii|nii\.gz|json)')

    data = []
    for file in mp2rage_files:
        data.append(reg.match(file.filename).groupdict())
        data[-1]['filename'] = file.filename
    data = pd.DataFrame(data)

    folder = os.path.dirname(data.iloc[0].filename)
    json_files = glob.glob(os.path.join(folder, '*.json'))

    json_data = []
    for file in json_files:
        json_data.append(reg.match(file).groupdict())
        with open(file) as f:
            json_data[-1].update(json.load(f))

    json_data = pd.DataFrame(json_data)
    json_data.drop(columns=['part', 'extension'], inplace=True)
    data = data.merge(json_data, on=['subject', 'session', 'acquisition', 'inv', 'echo'])
    
    data.drop(columns=['subject', 'session'])
    data['inv'] = data.inv.astype(int)
    data['echo'] = data.echo.fillna(1)
    data['echo'] = data.echo.astype(int)
    data.set_index(['acquisition', 'inv', 'echo', 'part'], inplace=True) 

    B1map = layout.get(subject=subject, session=session, suffix='B1map', extensions=['.nii', '.nii.gz'])
    
    if len(B1map) > 0:
        B1map = B1map[0].filename
        data['B1map'] = B1map

    multi_echo_bool = len(data.loc[acquisition,2, :, 'mag']) > 2

    ix = pd.IndexSlice

    MPRAGE_tr = data.loc[(acquisition, 1, 1, 'mag'), 'InversionRepetitionTime']
    invtimesAB = data.loc[(acquisition, 1, 1, 'mag'), 'InversionTime'], data.loc[(acquisition, 2, 1, 'mag'), 'InversionTime']
    nZslices = np.array([data.loc[(acquisition, 1, 1, 'mag'), 'NumberShots'], data.loc[(acquisition, 2, 1, 'mag'), 'NumberShots']])
    nZslices = nZslices.astype(float)
    nZslices *= np.array([.5, .5])
    nZslices = nZslices.astype(int)

    flipangleABdegree = data.loc[(acquisition, 1, 1, 'mag'), 'FlipAngle'], data.loc[(acquisition, 2, 1, 'mag'), 'FlipAngle']

    FLASH_tr = data.loc[(acquisition, 1, 1, 'mag'), 'ExcitationRepetitionTime'], data.loc[(acquisition, 2, 1, 'mag'), 'ExcitationRepetitionTime']

    inv1 = data.loc[(acquisition, 1, 1, 'mag')].filename
    inv1ph = data.loc[(acquisition, 1, 1, 'phase')].filename

    if multi_echo_bool:
        inv2 = data.loc[(ix[acquisition, 2, :, 'mag'])].filename.tolist()
        inv2ph = data.loc[(ix[acquisition, 2, :, 'phase'])].filename.tolist()
        echo_times = data.loc[(ix[acquisition, 2, :, 'mag'])].EchoTime.tolist()
    else:
        inv2 = data.loc[(acquisition, 2, 1, 'mag')].filename
        inv2ph = data.loc[(acquisition, 2, 1, 'phase')].filename

    pars = {'MPRAGE_tr':MPRAGE_tr,
            'invtimesAB':invtimesAB,
            'flipangleABdegree':flipangleABdegree,
            'FLASH_tr':FLASH_tr,
            'nZslices':nZslices,
            'inv1':inv1,
            'inv1ph':inv1ph,
            'inv2':inv2,
            'inv2ph':inv2ph}
    
    if multi_echo_bool:
        pars['echo_times'] = echo_times

    if 'B1map' in data.columns:
        pars['B1_fieldmap'] = data.B1map.loc[acquisition].iloc[0]

    return pars





if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("subject", 
                        type=str,
                        help="subject to process")
    parser.add_argument('session', 
                        nargs='?', 
                        default=None,
                        help="subject to process")

    args = parser.parse_args()

    main('/sourcedata', 
         '/derivatives',
         tmp_dir='/workflow_folders',
         subject=args.subject,
         session=args.session)
