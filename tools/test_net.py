"""Perform inference on one or more datasets."""

import argparse
import cv2
import logging
import os
import pprint
import subprocess
import sys

import torch
import numpy as np

import _init_paths  # pylint: disable=unused-import
from core.config import (cfg, merge_cfg_from_file, merge_cfg_from_cfg,
                         merge_cfg_from_list, assert_and_infer_cfg)
from core.test_engine import run_inference
import utils.logging

# OpenCL may be enabled by default in OpenCV3; disable it because it's not
# thread safe and causes unwanted GPU memory allocations.
cv2.ocl.setUseOpenCL(False)


def parse_args():
    """Parse in command line arguments"""
    parser = argparse.ArgumentParser(description='Test a Fast R-CNN network')
    parser.add_argument(
        '--dataset',
        help='training dataset')
    parser.add_argument(
        '--cfg', dest='cfg_file', required=True,
        help='optional config file')

    parser.add_argument(
        '--load_ckpt', help='path of checkpoint to load')
    parser.add_argument(
        '--load_detectron', help='path to the detectron weight pickle file')

    parser.add_argument(
        '--output_dir',
        help='output directory to save the testing results. If not provided, '
             'defaults to [args.load_ckpt|args.load_detectron]/../test.')

    parser.add_argument(
        '--set', dest='set_cfgs',
        help='set config keys, will overwrite config in the cfg_file.'
             ' See lib/core/config.py for all options',
        default=[], nargs='*')

    parser.add_argument(
        '--range',
        help='start (inclusive) and end (exclusive) indices',
        type=int, nargs=2)
    parser.add_argument(
        '--multi-gpu-testing', help='using multiple gpus for inference',
        action='store_true')
    parser.add_argument(
        '--vis', dest='vis', help='visualize detections', action='store_true')

    return parser.parse_args()


if __name__ == '__main__':

    if not torch.cuda.is_available():
        sys.exit("Need a CUDA device to run the code.")

    args = parse_args()

    assert (torch.cuda.device_count() == 1) ^ bool(args.multi_gpu_testing)

    assert bool(args.load_ckpt) ^ bool(args.load_detectron), \
        'Exactly one of --load_ckpt and --load_detectron should be specified.'
    output_dir_automatically_set = False
    if args.output_dir is None:
        ckpt_path = args.load_ckpt if args.load_ckpt else args.load_detectron
        args.output_dir = os.path.join(
            os.path.dirname(os.path.dirname(ckpt_path)), 'test')
        output_dir_automatically_set = True
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    utils.logging.setup_logging(
        os.path.join(args.output_dir, 'evaluation.log'))
    subprocess.call([
        './git-state/save_git_state.sh',
        os.path.join(args.output_dir, 'git-state')
    ])

    logger = logging.getLogger(__name__)
    if output_dir_automatically_set:
        logger.info('Automatically set output directory to %s',
                    args.output_dir)

    logger.info('Called with args:')
    logger.info(args)

    cfg.VIS = args.vis

    if args.cfg_file is not None:
        if args.cfg_file.endswith('.pkl'):
            import pickle
            import yaml
            with open(args.cfg_file, 'rb') as f:
                other_cfg = yaml.load(pickle.load(f)['cfg'])
                if ('FPN' in other_cfg
                        and 'RPN_COLLECT_SCALE' in other_cfg['FPN']):
                    other_cfg['FPN']['RPN_COLLECT_SCALE'] = int(
                        other_cfg['FPN']['RPN_COLLECT_SCALE'])
                merge_cfg_from_cfg(other_cfg)
        else:
            merge_cfg_from_file(args.cfg_file)
    if args.set_cfgs is not None:
        merge_cfg_from_list(args.set_cfgs)

    print('Pixel means: %s' % cfg.PIXEL_MEANS)
    if args.dataset == "coco2017":
        cfg.TEST.DATASETS = ('coco_2017_val',)
        cfg.MODEL.NUM_CLASSES = 81
    elif args.dataset == "keypoints_coco2017":
        cfg.TEST.DATASETS = ('keypoints_coco_2017_val',)
    elif args.dataset == 'coco_2017_objectness':
        cfg.TEST.DATASETS = ('coco_2017_val_objectness',)
        cfg.MODEL.NUM_CLASSES = 2
    elif args.dataset == 'flyingthings':
        cfg.TEST.DATASETS = ('flyingthings3d_test',)
    elif args.dataset == 'flyingthings_train':
        cfg.TEST.DATASETS = ('flyingthings3d_train',)
    elif args.dataset == 'flyingthings_estimatedflow':
        cfg.TEST.DATASETS = ('flyingthings3d_estimatedflow_test',)
    elif args.dataset == 'flyingthings_estimatedflow_train':
        cfg.TEST.DATASETS = ('flyingthings3d_estimatedflow_train',)
    elif args.dataset == "fbms_flow":
        cfg.TEST.DATASETS = ("fbms_flow_test",)
    elif args.dataset == "fbms_flow_train":
        cfg.TEST.DATASETS = ("fbms_flow_train",)
    elif args.dataset == "davis_flow_moving":
        cfg.TEST.DATASETS = ("davis_flow_moving_test",)
    elif args.dataset == "davis_flow_moving_train":
        cfg.TEST.DATASETS = ("davis_flow_moving_train",)
    elif args.dataset is not None:
        raise ValueError('Unknown --dataset: %s' % args.dataset)
    else:  # For subprocess call
        assert cfg.TEST.DATASETS, 'cfg.TEST.DATASETS shouldn\'t be empty'

    if any(x in args.dataset for x in ('flyingthings', 'fbms', 'davis')):
        cfg.PIXEL_MEANS = np.array([[[0, 0, 0]]])
        cfg.MODEL.NUM_CLASSES = 2
        cfg.TEST.FORCE_JSON_DATASET_EVAL = True
    assert_and_infer_cfg()

    logger.info('Testing with config:')
    logger.info(pprint.pformat(cfg))

    # For test_engine.multi_gpu_test_net_on_dataset
    args.test_net_file, _ = os.path.splitext(__file__)
    # manually set args.cuda
    args.cuda = True

    run_inference(
        args,
        ind_range=args.range,
        multi_gpu_testing=args.multi_gpu_testing,
        check_expected_results=True)
