import argparse
from bids import BIDSLayout
import re
import pandas as pd
import os
import glob
import json
import numpy as np
import pymp2rage


def get_mp2rage_pars(data, acquisition):

    MPRAGE_tr = data.loc[(acquisition, 1, 1, 'mag'), 'InversionRepetitionTime']
    invtimesAB = data.loc[(acquisition, 1, 1, 'mag'), 'InversionTime'], data.loc[(acquisition, 2, 1, 'mag'), 'InversionTime']
    nZslices = np.array([data.loc[(acquisition, 1, 1, 'mag'), 'NumberShots'], data.loc[(acquisition, 2, 1, 'mag'), 'NumberShots']])
    nZslices = nZslices.astype(float)
    nZslices *= np.array([.5, .5])
    inv1 = data.loc[(acquisition, 1, 1, 'mag')].filename
    inv1ph = data.loc[(acquisition, 1, 1, 'phase')].filename
    inv2 = data.loc[(acquisition, 2, 1, 'mag')].filename
    inv2ph = data.loc[(acquisition, 2, 1, 'phase')].filename

    return {'MPRAGE_tr':MPRAGE_tr,
            'invtimesAB':invtimesAB,
            'nZslices':nZslices,
            'inv1':inv1,
            'inv1ph':inv1ph,
            'inv2':inv2,
            'inv2ph':inv2}


def main(sourcedata,
         derivatives,
         tmp_dir,
         subject,
         session=None):

    if session is None:
        session = '.*'

    layout = BIDSLayout(sourcedata)
    data = get_metadata(layout, subject, session)
       
    mp2rage = pymp2rage.MP2RAGE(**get_mp2rage_pars(data, 'mp2rage'))

def get_metadata(layout, subject, session):
    mp2rage_files = layout.get(subject=subject, session=session, suffix='MPRAGE', extensions=['.nii', '.nii.gz'])
    reg = re.compile('.*/sub-(?P<subject>.+)_ses-(?P<session>.+)_acq-(?P<acquisition>.+)_inv-(?P<inv>[0-9]+)(_echo-(?P<echo>[0-9]+))?(_part-(?P<part>.+))?_MPRAGE.(?P<extension>nii|nii\.gz|json)')

    df = []
    for file in mp2rage_files:
        df.append(reg.match(file.filename).groupdict())
        df[-1]['filename'] = file.filename
    df = pd.DataFrame(df)

    folder = os.path.dirname(df.iloc[0].filename)
    json_files = glob.glob(os.path.join(folder, '*.json'))

    json_df = []
    for file in json_files:
        json_df.append(reg.match(file).groupdict())
        with open(file) as f:
            json_df[-1].update(json.load(f))

    json_df = pd.DataFrame(json_df)
    json_df.drop(columns=['part', 'extension'], inplace=True)
    df = df.merge(json_df, on=['subject', 'session', 'acquisition', 'inv', 'echo'])
    
    df.drop(columns=['subject', 'session'])
    df['inv'] = df.inv.astype(int)
    df['echo'] = df.echo.fillna(1)
    df.set_index(['acquisition', 'inv', 'echo', 'part'], inplace=True) 

    return df

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
