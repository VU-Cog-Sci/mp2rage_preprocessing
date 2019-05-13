import os

def _pickone(input):
    return input[0]

def get_inv(mp2rage_parameters, inv=1, echo=1):
    print(mp2rage_parameters)
    inv = mp2rage_parameters['inv{}'.format(inv)]

    if type(inv) is list:
        return inv[echo-1]
    else:
        return inv

def fit_mp2rage(mp2rage_parameters, return_images=['t1w_uni', 't1map']):
    import pymp2rage
    import os
    print(mp2rage_parameters)

    if 'echo_times' in mp2rage_parameters:
        mp2rage = pymp2rage.MEMP2RAGE(**mp2rage_parameters)
    else: 
        mp2rage = pymp2rage.MP2RAGE(**mp2rage_parameters)

    files = mp2rage.write_files(path=os.getcwd())
    print(files)

    result = [files[key] for key in return_images]
    return tuple(result)


def get_mp2rage_pars(sourcedata, subject, session, acquisition):
    import pandas as pd
    from bids import BIDSLayout
    import re
    import os
    import os.path as op
    import glob
    import json
    import numpy as np

    layout = BIDSLayout(sourcedata, 
		    validate=False)

    mp2rage_files = layout.get(subject=subject, 
                               session=session, 
                               acquisition=acquisition,
                               suffix='MPRAGE', 
                               extensions=['.nii', '.nii.gz'])
		
    print(mp2rage_files)

    reg = re.compile('.*/sub-(?P<subject>.+)_ses-(?P<session>.+)_acq-(?P<acquisition>.+)_inv-(?P<inv>[0-9]+)(_echo-(?P<echo>[0-9]+))?(_part-(?P<part>.+))?_MPRAGE.(?P<extension>nii|nii\.gz|json)')

    data = []
    for file in mp2rage_files:
        print(file.path)
        if not reg.match(file.path):
            print('ERROR WITH {}'.format(file.path))
        data.append(reg.match(file.path).groupdict())
        data[-1]['filename'] = file.path
    data = pd.DataFrame(data)
    print(data)

    folder = os.path.dirname(data.iloc[0].filename)
    json_files = glob.glob(os.path.join(folder, '*.json'))

    json_data = []
    for file in json_files:
        if reg.match(file):
            json_data.append(reg.match(file).groupdict())
            with open(file) as f:
                json_data[-1].update(json.load(f))

    json_data = pd.DataFrame(json_data)
    print(json_data)
    json_data.drop('part', axis=1, inplace=True)
    json_data.drop('extension', axis=1, inplace=True)
    data = data.merge(json_data, on=['subject', 'session', 'acquisition', 'inv', 'echo'])
    
    data.drop(columns=['subject', 'session'])
    data['inv'] = data.inv.astype(int)
    data['echo'] = data.echo.fillna(1)
    data['echo'] = data.echo.astype(int)
    data.set_index(['acquisition', 'inv', 'echo', 'part'], inplace=True) 

    print(data)

    B1map = layout.get(subject=subject, session=session, suffix='B1map', extensions=['.nii', '.nii.gz'])
    
    if len(B1map) > 0:
        B1map = B1map[0].path
        data['B1map'] = B1map

    multi_echo_bool = len(data.loc[acquisition,2, :, 'mag']) > 2

    ix = pd.IndexSlice

    MPRAGE_tr = data.loc[(acquisition, 1, 1, 'mag'), 'InversionRepetitionTime']
    invtimesAB = data.loc[(acquisition, 1, 1, 'mag'), 'InversionTime'], data.loc[(acquisition, 2, 1, 'mag'), 'InversionTime']
    nZslices = np.array([data.loc[(acquisition, 1, 1, 'mag'), 'NumberShots'], data.loc[(acquisition, 2, 1, 'mag'), 'NumberShots']])
    nZslices = nZslices.astype(float).ravel()
    nZslices *= np.array([.5, .5])
    nZslices = nZslices.astype(int)

    flipangleABdegree = data.loc[(acquisition, 1, 1, 'mag'), 'FlipAngle'], data.loc[(acquisition, 2, 1, 'mag'), 'FlipAngle']

    FLASH_tr = data.loc[(acquisition, 1, 1, 'mag'), 'ExcitationRepetitionTime'], data.loc[(acquisition, 2, 1, 'mag'), 'ExcitationRepetitionTime']

    inv1 = data.loc[(acquisition, 1, 1, 'mag'), 'filename']
    inv1ph = data.loc[(acquisition, 1, 1, 'phase'), 'filename']

    if multi_echo_bool:
        inv2 = data.loc[(ix[acquisition, 2, :, 'mag'])].filename.tolist()
        inv2ph = data.loc[(ix[acquisition, 2, :, 'phase'])].filename.tolist()
        echo_times = data.loc[(ix[acquisition, 2, :, 'mag'])].EchoTime.tolist()
    else:
        inv2 = data.loc[(acquisition, 2, 1, 'mag'), 'filename']
        inv2ph = data.loc[(acquisition, 2, 1, 'phase'), 'filename']

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

def get_derivative(derivatives_folder,
                   type,
                   modality,
                   subject,
                   suffix,
                   session=None,
                   space=None,
                   acquisition=None,
                   description=None,
                   label=None,
                   extension='nii.gz',
                   check_exists=True):

    folder = os.path.join(derivatives_folder, type)
    
    session_str = '_ses-{}'.format(session) if session else ''
    session_folder = 'ses-{}/'.format(session) if session else ''
    space_str = '_space-{}'.format(space) if space else ''
    desc_str = '_desc-{}'.format(description) if description else ''
    label_str = '_label-{}'.format(label) if label else ''
    acquisition_str = '_acq-{}'.format(acquisition) if acquisition else ''

    str = 'sub-{subject}/{session_folder}{modality}/sub-{subject}{session_str}{acquisition_str}{space_str}{label_str}{desc_str}_{suffix}.{extension}'.format(**locals())

    fn = os.path.join(folder, str)

    if not os.path.exists(fn):
        if check_exists:
            raise Exception('{} does not exists!'.format(fn))
        else:
            return None

    return fn
