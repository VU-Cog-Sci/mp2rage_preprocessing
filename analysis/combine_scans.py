import argparse
from fmriprep.interfaces import DerivativesDataSink
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
from nipype.interfaces import ants
from nipype.interfaces.c3 import C3dAffineTool
from utils import _pickone, get_mp2rage_pars, fit_mp2rage, get_inv

def main(sourcedata,
         derivatives,
         tmp_dir,
         subject,
         session=None):

    if session is None:
        session = '.*'

    wf_name = 'combine_mp2rages_{}'.format(subject)

    wf = init_combine_mp2rage_wf(name=wf_name,
                                 sourcedata=sourcedata,
                                 derivatives=derivatives)
    wf.base_dir = '/workflow_folders'



    wf.inputs.inputnode.subject = subject
    wf.inputs.inputnode.session = session
    wf.inputs.inputnode.acquisition = ['memp2rage', 'mp2rage']

    wf.run()

def init_combine_mp2rage_wf(sourcedata,
                            derivatives,
                            name='combine_mp2rages',
                            n_mp2rages=2):

    wf = pe.Workflow(name=name)

    inputnode = pe.Node(niu.IdentityInterface(fields=['sourcedata',
                                                      'derivatives',
                                                      'subject',
                                                      'session',
                                                      'acquisition']),
                        name='inputnode')

    inputnode.inputs.sourcedata = sourcedata
    inputnode.inputs.derivatives = derivatives

    
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

    get_first_inversion = pe.MapNode(niu.Function(function=get_inv,
                                                  input_names=['mp2rage_parameters', 'inv', 'echo'], output_names='inv1'),
                                     iterfield=['mp2rage_parameters'],
                                     name='get_first_inversion')

    get_first_inversion.inputs.inv = 1
    get_first_inversion.inputs.echo = 1
    wf.connect(get_parameters, 'mp2rage_parameters', get_first_inversion, 'mp2rage_parameters')

    split = pe.Node(niu.Split(splits=[1, n_mp2rages-1]),
                    name='split')
    wf.connect(get_first_inversion, 'inv1', split, 'inlist')

    flirt = pe.MapNode(fsl.FLIRT(dof=6),
                       iterfield=['in_file'],
                       name='flirt')



    wf.connect(split, ('out1', _pickone), flirt, 'reference')
    wf.connect(split, 'out2', flirt, 'in_file')

    convert2itk = pe.MapNode(C3dAffineTool(), iterfield=['source_file',
                                                         'transform_file'],
                             name='convert2itk')
    convert2itk.inputs.fsl2ras = True
    convert2itk.inputs.itk_transform = True


    wf.connect(flirt, 'out_matrix_file', convert2itk, 'transform_file')
    wf.connect(split, ('out1', _pickone), convert2itk, 'reference_file')
    wf.connect(split, 'out2', convert2itk, 'source_file')

    transform_t1w_wf = init_transform_to_first_image_wf('transforms_t1w',
                                                        n_images=n_mp2rages)

    wf.connect(make_t1w, 't1w_uni', transform_t1w_wf, 'inputnode.in_files')
    wf.connect(convert2itk, 'itk_transform', transform_t1w_wf, 'inputnode.transforms')


    get_second_inversion = pe.MapNode(niu.Function(function=get_inv, 
                                                   input_names=['mp2rage_parameters', 'inv', 'echo'],
                                                   output_names='inv2'),
                                     iterfield=['mp2rage_parameters'],
                                     name='get_second_inversion')
    get_second_inversion.inputs.inv = 2

    transform_inv2_wf = init_transform_to_first_image_wf('transforms_inv2',
                                                        n_images=n_mp2rages)
    wf.connect(get_parameters, 'mp2rage_parameters', get_second_inversion, 'mp2rage_parameters')
    wf.connect(get_second_inversion, 'inv2', transform_inv2_wf, 'inputnode.in_files')
    wf.connect(convert2itk, 'itk_transform', transform_inv2_wf, 'inputnode.transforms')


    transform_t1map_wf = init_transform_to_first_image_wf('transform_t1map',
                                                          n_images=n_mp2rages)


    wf.connect(make_t1w, 't1map', transform_t1map_wf, 'inputnode.in_files')
    wf.connect(convert2itk, 'itk_transform', transform_t1map_wf, 'inputnode.transforms')

    ds_t1w = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='averaged_mp2rages',
                                         suffix='T1w',
                                         space='average'),
                                         name='ds_t1w')

    rename = pe.Node(niu.Rename(use_fullpath=True), name='rename')
    rename.inputs.format_string = '%(path)s/sub-%(subject_id)s_ses-%(session)s_MPRAGE.nii.gz'
    rename.inputs.parse_string = '(?P<path>.+)/sub-(?P<subject_id>.+)_ses-(?P<session>.+)_acq-.+_MPRAGE.nii(.gz)?'

    wf.connect(get_first_inversion, ('inv1', _pickone), rename, 'in_file')
    wf.connect(rename, 'out_file', ds_t1w, 'source_file')
    wf.connect(transform_t1w_wf, 'outputnode.mean_image', ds_t1w, 'in_file')


    ds_t1map = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='averaged_mp2rages',
                                         suffix='T1map',
                                         space='average'),
                                         name='ds_t1map')


    wf.connect(rename, 'out_file', ds_t1map, 'source_file')
    wf.connect(transform_t1map_wf, 'outputnode.mean_image', ds_t1map, 'in_file')

    ds_inv2 = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='averaged_mp2rages',
                                         suffix='INV2',
                                         space='average'),
                                         name='ds_inv2')


    wf.connect(rename, 'out_file', ds_inv2, 'source_file')
    wf.connect(transform_inv2_wf, 'outputnode.mean_image', ds_inv2, 'in_file')


    return wf


def init_transform_to_first_image_wf(name='transform_images', n_images=2):


    wf = pe.Workflow(name=name)

    inputnode = pe.Node(niu.IdentityInterface(fields=['in_files',
                                                  'transforms']),
                        name='inputnode')


    split = pe.Node(niu.Split(splits=[1, n_images-1]),
                    name='split')
    wf.connect(inputnode, 'in_files', split, 'inlist')

    apply_sinc = pe.MapNode(ants.ApplyTransforms(interpolation='LanczosWindowedSinc'), 
                            iterfield=['input_image'],
                            name='apply_sinc')
    wf.connect(inputnode, 'transforms', apply_sinc, 'transforms')
    wf.connect(split, ('out1', _pickone), apply_sinc, 'reference_image')
    wf.connect(split, 'out2', apply_sinc, 'input_image')
    
    merge_lists = pe.Node(niu.Merge(2),
                              name='merge_lists')
    wf.connect(split, 'out1', merge_lists, 'in1')
    wf.connect(apply_sinc, 'output_image', merge_lists, 'in2')

    merge_niftis = pe.Node(fsl.Merge(dimension='t'),
                               name='merge_niftis')
    wf.connect(merge_lists, 'out', merge_niftis, 'in_files')

    mean_image = pe.Node(fsl.MeanImage(dimension='T'),
                       name='mean_image')
    wf.connect(merge_niftis, 'merged_file', mean_image, 'in_file')

    outputnode = pe.Node(niu.IdentityInterface(fields=['mean_image', 'transformed_images']),
                         name='outputnode')
    wf.connect(mean_image, 'out_file', outputnode, 'mean_image')
    wf.connect(merge_lists, 'out', outputnode, 'transformed_images')

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

    args = parser.parse_args()

    main('/sourcedata', 
         '/derivatives',
         tmp_dir='/workflow_folders',
         subject=args.subject,
         session=args.session)
