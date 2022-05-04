# Copyright 2020-present, Pietro Buzzega, Matteo Boschini, Angelo Porrello, Simone Calderara.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
from torch.utils.data import DataLoader
from torchvision.datasets import CIFAR10
import torchvision.transforms as transforms
from backbone.ResNet import ResNet18
import torch.nn.functional as F
from utils.conf import base_path
from PIL import Image
from datasets.utils.validation import get_train_val
from datasets.utils.continual_dataset import ContinualDataset, store_masked_loaders
from datasets.utils.continual_dataset import get_previous_train_loader
from datasets.transforms.denormalization import DeNormalize
import torch
from typing import Tuple
import numpy as np

class MyCIFAR10(CIFAR10):
    """
    Overrides the CIFAR10 dataset to change the getitem function.
    """
    def __init__(self, root, train=True, transform=None,
                 target_transform=None, download=False) -> None:
        self.not_aug_transform = transforms.Compose([transforms.ToTensor()])
        super(MyCIFAR10, self).__init__(root, train, transform, target_transform, download)
        if train and False:
            new_labels = []
            new_labels = []
            new_data = []
            targets_ = np.array (self.targets)
            p = 0.01
            n_classes = len (np.unique(targets_))
            n_samples_per_class = len (self.targets) / n_classes
            for y in np.unique(targets_):
                n_samples_in_this_class = 0
                data_y = self.data[targets_ == y]
                
                for d in self.data[targets_ == y]:
                    if np.random.rand(1) < p:
                        new_labels.append(y)
                        new_data.append(d)
                        n_samples_in_this_class += 1
            print (len(new_labels))
            perm = np.random.permutation(len(new_labels))
            self.targets = list (np.array(new_labels)[perm])
            self.data = np.array(new_data)[perm]        

    def __getitem__(self, index: int) -> Tuple[type(Image), int, type(Image)]:
        """
        Gets the requested element from the dataset.
        :param index: index of the element to be returned
        :returns: tuple: (image, target) where target is index of the target class.
        """
        img, target = self.data[index], self.targets[index]

        # to return a PIL Image
        img = Image.fromarray(img, mode='RGB')
        original_img = img.copy()

        not_aug_img = self.not_aug_transform(original_img)

        if self.transform is not None:
            img = self.transform(img)

        if self.target_transform is not None:
            target = self.target_transform(target)

        if hasattr(self, 'logits'):
            return img, target, not_aug_img, self.logits[index]

        return img, target, not_aug_img


class SequentialCIFAR10(ContinualDataset):

    NAME = 'seq-cifar10'
    SETTING = 'class-il'
    N_CLASSES_PER_TASK = 2
    N_TASKS = 5
    TRANSFORM = transforms.Compose(
            [transforms.RandomCrop(32, padding=4),
             transforms.RandomHorizontalFlip(),
             transforms.ToTensor(),
             transforms.Normalize((0.4914, 0.4822, 0.4465),
                                  (0.2470, 0.2435, 0.2615))])

    def get_data_loaders(self, nomask=False):
        transform = self.TRANSFORM

        test_transform = transforms.Compose(
            [transforms.ToTensor(), self.get_normalization_transform()])

        train_dataset = MyCIFAR10(base_path() + 'CIFAR10', train=True,
                                  download=True, transform=transform)
        if self.args.validation:
            train_dataset, test_dataset = get_train_val(train_dataset,
                                                    test_transform, self.NAME)
        else:
            test_dataset = CIFAR10(base_path() + 'CIFAR10', train=False,
                                   download=True, transform=test_transform)

        if not nomask:
            if isinstance(train_dataset.targets, list):
                train_dataset.targets = torch.tensor(train_dataset.targets, dtype=torch.long)
            if isinstance(test_dataset.targets, list):
                test_dataset.targets = torch.tensor(test_dataset.targets, dtype=torch.long)
            train, test = store_masked_loaders(train_dataset, test_dataset, self)
            return train, test
        else:
            train_loader = DataLoader(train_dataset,
                                      batch_size=32, shuffle=True, num_workers=2)
            test_loader = DataLoader(test_dataset,
                                     batch_size=32, shuffle=False, num_workers=2)
            return train_loader, test_loader

    def get_joint_loaders(self, nomask=False):
        return self.get_data_loaders(nomask=True)

    def not_aug_dataloader(self, args, batch_size):

        if hasattr(args, 'iba') and args.iba:
            transform = transforms.Compose([transforms.ToTensor()])
        else:
            transform = transforms.Compose([transforms.ToTensor(),
                                            self.get_normalization_transform()])

        train_dataset = MyCIFAR10(base_path() + 'CIFAR10', train=True,
                                  download=True, transform=transform)

        if isinstance(train_dataset.targets, list):
            train_dataset.targets = torch.tensor(train_dataset.targets, dtype=torch.long)

        train_mask = np.logical_and(np.array(train_dataset.targets) >= (self.i - 1) * self.N_CLASSES_PER_TASK
                                    , np.array(train_dataset.targets) < self.i * self.N_CLASSES_PER_TASK)

        train_dataset.data = train_dataset.data[train_mask]
        train_dataset.targets = np.array(train_dataset.targets)[train_mask]

        train_loader = get_previous_train_loader(train_dataset, batch_size, self)

        return train_loader

    @staticmethod
    def get_transform():
        transform = transforms.Compose(
            [transforms.ToPILImage(), SequentialCIFAR10.TRANSFORM])
        return transform

    @staticmethod
    def get_backbone():
        return ResNet18(SequentialCIFAR10.N_CLASSES_PER_TASK * SequentialCIFAR10.N_TASKS)

    @staticmethod
    def get_loss():
        return F.cross_entropy

    @staticmethod
    def get_normalization_transform():
        transform = transforms.Normalize((0.4914, 0.4822, 0.4465),
                                         (0.2470, 0.2435, 0.2615))
        return transform

    @staticmethod
    def get_denormalization_transform():
        transform = DeNormalize((0.4914, 0.4822, 0.4465),
                                (0.2470, 0.2435, 0.2615))
        return transform