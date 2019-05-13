from bids import BIDSLayout
import argparse
import os
import nipype.pipeline.engine as pe
from nipype.interfaces import ants
from nipype.interfaces import afni
from nipype.interfaces import fsl
from nipype.interfaces import utility as niu
from fmriprep.interfaces import DerivativesDataSink
from utils import get_derivative


def nighres_skullstrip(inv2, t1w, t1map):
    from nighres.brain import mp2rage_skullstripping
    import os
    
    results = mp2rage_skullstripping(inv2,
                                 t1w,
                                 t1map,
                                 output_dir=os.getcwd(),
                                 save_data=True)
    
    return results['brain_mask'].get_filename()

def nighres_dura_masker(inv2, inv2_mask):
    from nighres.brain import mp2rage_dura_estimation
    import os
    
    results = mp2rage_dura_estimation(inv2,
                                 inv2_mask,
                                 output_dir=os.getcwd(),
                                 save_data=True)
    
    return results['result'].get_filename()


def mask_t1w(t1w, inv2, t1w_mask, 
                     manual_inside=None, manual_outside=None,
                     dura_mask=None):

    from nilearn import image
    import os
    from nipype.utils.filemanip import split_filename
    from scipy import ndimage

    _, t1w_fn, ext= split_filename(t1w)
    
    if manual_inside:
        t1w_mask = image.math_img('(t1w_mask + manual_inside) > 0',
                                  t1w_mask=t1w_mask,
                                  manual_inside=manual_inside)

    if manual_outside:
        # Stuff like dura should be put to 0, not just multiplied with INV2
        t1w = image.math_img('t1w * (np.ones_like(t1w) - manual_outside)',
                             t1w=t1w,
                             manual_outside=manual_outside)

        t1w_mask = image.math_img('(t1w_mask - manual_outside) > 0',
                                  t1w_mask=t1w_mask,
                                  manual_outside=manual_outside)



    new_t1w = image.math_img('t1w * t1w_mask * np.mean(inv2[t1w_mask == 1]/np.max(inv2))'
                             '+ t1w * inv2/np.max(inv2) * (1-t1w_mask)',
                              t1w=t1w,
                              t1w_mask=t1w_mask,
                              inv2=inv2)

    if dura_mask:
        # Dilate dura mask
        dilated_dura_mask = ndimage.binary_dilation(image.load_img(dura_mask).get_data(),
                                                    iterations=2)
        dilated_dura_mask = image.new_img_like(dura_mask, dilated_dura_mask)

        # Make a mask of dilated dura, but only outwards
        dilated_dura_mask = image.math_img('(dilated_dura_mask - (t1w_mask - dura_mask)) > 0',
                                           t1w_mask=t1w_mask,
                                           dura_mask=dura_mask,
                                           dilated_dura_mask=dilated_dura_mask)
        
        if manual_inside:
            dilated_dura_mask = image.math_img('dilated_dura_mask - manual_inside > 0',
                                               dilated_dura_mask=dilated_dura_mask,
                                               manual_inside=manual_inside)

        new_t1w = image.math_img('t1w * (np.ones_like(dura_mask) - dura_mask)',
                                  t1w=new_t1w,
                                  dura_mask=dilated_dura_mask)

        t1w_mask = image.math_img('(t1w_mask - dilated_dura_mask) > 0',
                                  t1w_mask=t1w_mask,
                                  dilated_dura_mask=dilated_dura_mask)

    new_t1w_fn = os.path.abspath('{}_masked{}'.format(t1w_fn, ext))
    new_t1w.to_filename(new_t1w_fn)

    new_mask_fn= os.path.abspath('{}_brainmask{}'.format(t1w_fn, ext))
    t1w_mask.to_filename(new_mask_fn)

    return new_t1w_fn, new_mask_fn


def main(sourcedata,
         derivatives,
         tmp_dir,
         subject,
         num_threads=8,
         session=None):
    
    if session is None:
        session = '.*'

    derivatives_layout = BIDSLayout(os.path.join(derivatives, 'averaged_mp2rages'), validate=False)

    inv2 = get_bids_file(derivatives_layout, 
                         subject,
                         suffix='INV2')

    t1w = get_bids_file(derivatives_layout, 
                         subject,
                         suffix='T1w')

    t1map = get_bids_file(derivatives_layout, 
                         subject,
                         suffix='T1map')


    manual_outside = get_derivative(derivatives, type='manual_segmentation',
                                    modality='anat', subject=subject,
                                    suffix='mask', description='outside',
                                    space='average', session=session,
                                    check_exists=False)

    manual_inside = get_derivative(derivatives, type='manual_segmentation',
                                    modality='anat', subject=subject,
                                    suffix='mask', description='gm',
                                    space='average', session=session,
                                    check_exists=False)



    wf_name = 'mask_wf_{}'.format(subject)
    mask_wf = init_masking_wf(name=wf_name, num_threads=num_threads)
    mask_wf.base_dir = '/workflow_folders'

    mask_wf.inputs.inputnode.inv2 = inv2
    mask_wf.inputs.inputnode.t1w = t1w
    mask_wf.inputs.inputnode.t1map = t1map
    mask_wf.inputs.inputnode.manual_inside = manual_inside
    mask_wf.inputs.inputnode.manual_outside = manual_outside

    mask_wf.run()


def init_masking_wf(name='mask_wf',
                    derivatives='/derivatives',
                    num_threads=8):

    wf = pe.Workflow(name=name)

    inputnode = pe.Node(niu.IdentityInterface(fields=['inv2',
                                                      't1w',
                                                      't1map',
                                                      'manual_inside',
                                                      'manual_outside'],
                                              ),
                        name='inputnode')

    n4 = pe.Node(ants.N4BiasFieldCorrection(copy_header=True,
                                            num_threads=num_threads),
                 name='n4')

    wf.connect(inputnode, 'inv2', n4, 'input_image')


    bet = pe.Node(fsl.BET(mask=True, skull=True), name='bet')
    wf.connect(n4, 'output_image', bet, 'in_file')


    nighres_brain_extract = pe.Node(niu.Function(function=nighres_skullstrip,
                                          input_names=['inv2', 't1w', 't1map'],
                                          output_names=['brainmask']),
                             name='nighres_brain_extract')

    wf.connect(n4, 'output_image', nighres_brain_extract, 'inv2')
    wf.connect(inputnode, 't1w', nighres_brain_extract, 't1w')
    wf.connect(inputnode, 't1map', nighres_brain_extract, 't1map')

    dura_masker = pe.Node(niu.Function(function=nighres_dura_masker,
                                          input_names=['inv2', 'inv2_mask'],
                                          output_names=['duramask']),
                             name='dura_masker')

    wf.connect(n4, 'output_image', dura_masker, 'inv2')
    wf.connect(nighres_brain_extract, 'brainmask', dura_masker, 'inv2_mask')



    afni_mask = pe.Node(afni.Automask(outputtype='NIFTI_GZ',
                                      clfrac=0.5),
                        name='afni_mask')
    wf.connect(bet, 'out_file', afni_mask, 'in_file')

    threshold_dura = pe.Node(fsl.Threshold(thresh=.8, args='-bin'),
                             name='threshold_dura')
    wf.connect(dura_masker, 'duramask', threshold_dura, 'in_file')

    mask_t1map = pe.Node(fsl.ApplyMask(), name='mask_t1map')
    wf.connect(inputnode, 't1map', mask_t1map, 'in_file')
    wf.connect(afni_mask, 'out_file', mask_t1map, 'mask_file')

    t1w_masker = pe.Node(niu.Function(function=mask_t1w,
                                    input_names=['t1w', 'inv2', 't1w_mask',
                                                 'dura_mask', 'manual_inside', 
                                                 'manual_outside'],
                                    output_names=['out_file',
                                                  'brain_mask']),
                       name='t1w_masker')


    wf.connect(inputnode, 't1w', t1w_masker, 't1w')
    wf.connect(inputnode, 'manual_inside', t1w_masker, 'manual_inside')
    wf.connect(inputnode, 'manual_outside', t1w_masker, 'manual_outside')
    wf.connect(n4, 'output_image', t1w_masker, 'inv2')
    wf.connect(afni_mask, 'out_file', t1w_masker, 't1w_mask')
    wf.connect(threshold_dura, 'out_file', t1w_masker, 'dura_mask')


    ds_t1map = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='masked_mp2rages',
                                         suffix='T1map',
                                         desc='masked'),
                                         name='ds_t1map')

    wf.connect(inputnode, 't1map', ds_t1map, 'source_file')
    wf.connect(mask_t1map, 'out_file', ds_t1map, 'in_file')

    ds_t1w = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='masked_mp2rages',
                                         desc='masked',
                                         suffix='T1w'),
                                         name='ds_t1w')


    ds_dura = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='masked_mp2rages',
                                         desc='dura',
                                         suffix='mask'),
                                         name='ds_dura')

    ds_brainmask = pe.Node(DerivativesDataSink(base_directory=derivatives,
                                         keep_dtype=False,
                                         out_path_base='masked_mp2rages',
                                         desc='brainmask',
                                         suffix='mask'),
                                         name='ds_brainmask')

    wf.connect(inputnode, 't1w', ds_t1w, 'source_file')
    wf.connect(t1w_masker, 'out_file', ds_t1w, 'in_file')

    wf.connect(inputnode, 't1w', ds_dura, 'source_file')
    wf.connect(dura_masker, 'duramask', ds_dura, 'in_file')

    wf.connect(inputnode, 't1w', ds_brainmask, 'source_file')
    wf.connect(t1w_masker, 'brain_mask', ds_brainmask, 'in_file')

    return wf

def get_bids_file(layout,
                  subject,
                  suffix,
                  filter=None):

    img = layout.get(subject=subject,
                     suffix=suffix,
                     return_type='file')

    if filter is not None:
        img = [im for im in img if filter in im]

    if len(img) == 0:
        raise Exception('Found no image for {}, {}'.format(modality, 
                                                           filter))
    if len(img) > 1:
        warnings.warn('Found more than one {}-image, using {}'.format(modality,
                                                                      img[0]))

    return img[0]

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

