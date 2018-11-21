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
    import glob
    import json
    import numpy as np

    layout = BIDSLayout(sourcedata)

    mp2rage_files = layout.get(subject=subject, 
                               session=session, 
                               acquisition=acquisition,
                               suffix='MPRAGE', 
                               extensions=['.nii', '.nii.gz'])
    print(mp2rage_files)

    reg = re.compile('.*/sub-(?P<subject>.+)_ses-(?P<session>.+)_acq-(?P<acquisition>.+)_inv-(?P<inv>[0-9]+)(_echo-(?P<echo>[0-9]+))?(_part-(?P<part>.+))?_MPRAGE.(?P<extension>nii|nii\.gz|json)')

    data = []
    for file in mp2rage_files:
        print(file.filename)
        if not reg.match(file.filename):
            print('ERROR WITH {}'.format(file))
        data.append(reg.match(file.filename).groupdict())
        data[-1]['filename'] = file.filename
    data = pd.DataFrame(data)

    folder = os.path.dirname(data.iloc[0].filename)
    json_files = glob.glob(os.path.join(folder, '*.json'))

    json_data = []
    for file in json_files:
        if reg.match(file):
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

    MPRAGE_tr = data.loc[(acquisition, 1, 1, 'mag'), 'InversionRepetitionTime'].values[0]
    invtimesAB = data.loc[(acquisition, 1, 1, 'mag'), 'InversionTime'].values[0], data.loc[(acquisition, 2, 1, 'mag'), 'InversionTime'].values[0]
    nZslices = np.array([data.loc[(acquisition, 1, 1, 'mag'), 'NumberShots'], data.loc[(acquisition, 2, 1, 'mag'), 'NumberShots']])
    nZslices = nZslices.astype(float).ravel()
    nZslices *= np.array([.5, .5])
    nZslices = nZslices.astype(int)

    flipangleABdegree = data.loc[(acquisition, 1, 1, 'mag'), 'FlipAngle'].values[0], data.loc[(acquisition, 2, 1, 'mag'), 'FlipAngle'].values[0]

    FLASH_tr = data.loc[(acquisition, 1, 1, 'mag'), 'ExcitationRepetitionTime'].values[0], data.loc[(acquisition, 2, 1, 'mag'), 'ExcitationRepetitionTime'].values[0]

    inv1 = data.loc[(acquisition, 1, 1, 'mag')].filename.values[0]
    inv1ph = data.loc[(acquisition, 1, 1, 'phase')].filename.values[0]

    if multi_echo_bool:
        inv2 = data.loc[(ix[acquisition, 2, :, 'mag'])].filename.tolist()
        inv2ph = data.loc[(ix[acquisition, 2, :, 'phase'])].filename.tolist()
        echo_times = data.loc[(ix[acquisition, 2, :, 'mag'])].EchoTime.tolist()
    else:
        inv2 = data.loc[(acquisition, 2, 1, 'mag')].filename.values[0]
        inv2ph = data.loc[(acquisition, 2, 1, 'phase')].filename.values[0]

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
