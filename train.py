import os
import os.path as osp

import torch
import random
import numpy as np
import torch.nn as nn
import albumentations as A

import argparse
import torch.optim as optim

from tqdm.auto import tqdm
from torch.utils.data import DataLoader
from models.base_model import TorchvisionModel
from trainer import Trainer


from dataset import XRayDataset
from omegaconf import OmegaConf

def set_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed) # if use multi-GPU
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    np.random.seed(seed)
    random.seed(seed)

def setup(cfg):
    # 이미지 파일명
    fnames = {
        osp.relpath(osp.join(root, fname), start=cfg.image_root)
        for root, _, files in os.walk(cfg.image_root)
        for fname in files
        if osp.splitext(fname)[1].lower() == ".png"
    }

    # label json 파일명
    labels = {
        osp.relpath(osp.join(root, fname), start=cfg.label_root)
        for root, _, files in os.walk(cfg.label_root)
        for fname in files
        if osp.splitext(fname)[1].lower() == ".json"
    }

    return np.array(sorted(fnames)), np.array(sorted(labels))


def main(cfg):
    set_seed(cfg.seed)

    fnames, labels = setup(cfg)

    transform = [getattr(A, aug)(**params) 
                                         for aug, params in cfg.transform.items()]

    train_dataset = XRayDataset(fnames,
                                labels,
                                cfg.image_root,
                                cfg.label_root,
                                fold=cfg.val_fold,
                                transforms=transform,
                                is_train=True)
    
    valid_dataset = XRayDataset(fnames,
                                labels,
                                cfg.image_root,
                                cfg.label_root,
                                fold=cfg.val_fold,
                                transforms=transform,
                                is_train=False)
    
    train_loader = DataLoader(
        dataset=train_dataset, 
        batch_size=cfg.train_batch_size,
        shuffle=True,
        num_workers=8,
        drop_last=True,
    )

    # 주의: validation data는 이미지 크기가 크기 때문에 `num_wokers`는 커지면 메모리 에러가 발생할 수 있습니다.
    valid_loader = DataLoader(
        dataset=valid_dataset, 
        batch_size=cfg.val_batch_size,
        shuffle=False,
        num_workers=0,
        drop_last=False
    )

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = TorchvisionModel(cfg.model_name,
                             train_dataset.num_classes,
                             cfg.pretrained)

    model.to(device)

    optimizer = optim.Adam(params=model.parameters(),
                           lr=cfg.lr,
                           weight_decay=cfg.weight_decay)
    
    criterion = nn.BCEWithLogitsLoss()

    trainer = Trainer(
        model=model,
        device=device,
        train_loader=train_loader,
        val_loader=valid_loader,
        threshold=cfg.threshold,
        optimizer=optimizer,
        criterion=criterion,
        max_epoch=cfg.max_epoch,
        save_dir=cfg.save_dir,
        val_interval=cfg.val_interval
    )

    trainer.train()


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="configs/base_train.yaml")

    args = parser.parse_args()
    
    with open(args.config, 'r') as f:
        cfg = OmegaConf.load(f)
    
    main(cfg)