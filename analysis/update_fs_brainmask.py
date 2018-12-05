import argparse
from utils import get_derivative
import os
from nilearn import image
import nibabel as nb

def main(sourcedata,
         derivatives,
         tmp_dir,
         subject,
         session=None):

    
    brainmask_fn = os.path.join(derivatives, 'freesurfer', 'sub-{}'.format(subject),
                             'mri', 'brainmask.mgz')

    if not os.path.exists(brainmask_fn):
        raise Exception('Brainmask {} does not exits. Did you run Freesurfer?'.format(brainmask_fn))

    brainmask = image.load_img(brainmask_fn)

    manual_outside = get_derivative(derivatives, type='manual_segmentation',
                                    modality='anat', subject=subject,
                                    suffix='mask', description='outside',
                                    space='average', session=session,
                                    check_exists=False)

    manual_outside = image.resample_to_img(manual_outside, brainmask,
                                           interpolation='nearest')

    manual_inside = get_derivative(derivatives, type='manual_segmentation',
                                    modality='anat', subject=subject,
                                    suffix='mask', description='gm',
                                    space='average', session=session,
                                    check_exists=False)

    manual_inside = image.resample_to_img(manual_inside, brainmask,
                                           interpolation='nearest')

    new_brainmask = image.math_img('brainmask * (np.ones_like(brainmask) - manual_outside)' 
                               '+ (manual_inside - (brainmask > 0)) ',
                               brainmask=brainmask,
                               manual_inside=manual_inside,
                               manual_outside=manual_outside)
    print(new_brainmask.shape)

    new_brainmask = nb.freesurfer.MGHImage(new_brainmask.get_data(), brainmask.affine, brainmask.header)

    if not (brainmask.get_data() == new_brainmask.get_data()).all():
        print('Brain mask has been altered')
        new_brainmask.to_filename(brainmask_fn)
        print('writing to {}'.format(brainmask_fn))
    else:
        print('Brain mask has NOT been altered')
                               
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

