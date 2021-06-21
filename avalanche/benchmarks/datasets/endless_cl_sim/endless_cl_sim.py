################################################################################
# Copyright (c) 2021 ContinualAI.                                              #
# Copyrights licensed under the MIT License.                                   #
# See the accompanying LICENSE file for terms.                                 #
#                                                                              #
# Date: 15-06-2021                                                             #
# Author: TimmHess                                                             #
# E-mail: hess@ccc.cs.uni-frankfurt.de                                         #
# Website: continualai.org                                                     #
################################################################################

""" Endless-CL-Sim Dataset """

from pathlib import Path
import glob
import os
from typing import Union
from warnings import warn
import sys
import json

import numpy as np
from PIL import Image

from torch.utils.data import Dataset

from avalanche.benchmarks.datasets import default_dataset_location
from avalanche.benchmarks.datasets.endless_cl_sim import \
    endless_cl_sim_data
from avalanche.benchmarks.datasets.downloadable_dataset import \
    DownloadableDataset


class ClassificationSubSequence(Dataset):
    def __init__(self, file_paths, targets, patch_size=64, 
                 transform=None, target_transform=None):
        """
        # TODO:
        """
        self.file_paths = file_paths
        self.targets = targets
        self.patch_size = patch_size
        self.transform = transform
        self.target_transform = target_transform
        return

    def _pil_loader(self, file_path):
        with open(file_path, "rb") as f:
            img = Image.open(f).convert("RGB").resize(
                (self.patch_size, self.patch_size), Image.NEAREST)
        return img

    def __getitem__(self, index: int):
        img_path = self.file_paths[index]
        target = self.targets[index]

        img = self._pil_loader(img_path)

        img = self.transform(img)

        if not self.target_transform is None:
            target = self.target_transform(target)

        return img, target

    def __len__(self) -> int:
        return len(self.file_paths)


class VideoSubSequence(Dataset):
    def __init__(self, file_paths, target_paths, 
                 segmentation_file, classmap_file=None, patch_size=(240, 135), 
                 transform=None, target_transform=None):
        """
        # TODO
        """
        self.file_paths = file_paths
        self.target_paths = target_paths
        self.segmentation_file = segmentation_file
        self.classmap_file = classmap_file
        self.patch_size = patch_size
        self.transform = transform
        self.target_transform = transform

        # Init classmap
        self.classmap = self._load_classmap(classmap_file=self.classmap_file)

        # Init labelmap
        self.labelmap = self._load_labelmap(
            labelmap_file=self.segmentation_file)
        return

    def _pil_loader(self, file_path, is_target=False):
        with open(file_path, "rb") as f:
            convert_identifier = "RGB"
            if is_target:
                convert_identifier = "L"
            img = Image.open(f).convert(convert_identifier).resize(
                (self.patch_size[0], self.patch_size[1]), Image.NEAREST)
        return img

    def _load_classmap(self, classmap_file):
        classmap = {}
        if classmap_file is None:
            classmap = endless_cl_sim_data.default_semseg_classmap_obj
        elif Path(classmap_file).exists():
            with open(classmap_file) as file:
                json_array = json.load(file)
                classmap = json_array["ClassMapping"]
        else:
            raise ValueError(f"classmap_file: {classmap_file} does not exist!")
        return classmap

    def _load_labelmap(self, labelmap_file):
        labelmap = {}
        if Path(labelmap_file).exists():
            with open(labelmap_file) as file:
                json_array = json.load(file)

                segMin = json_array[0]["ObjectClassMapping"]
                segMax = json_array[1]["ObjectClassMapping"]

                for key in segMin:
                    labelmap[key] = [segMin[key], segMax[key]]
        else:
            raise ValueError(f"labelmap_file: {labelmap_file} does not exist!")
        return labelmap

    def _get_label_name(self, label):
        for key in self.labelmap:
            min_val, max_val = self.labelmap[key]
            if min_val == max_val:
                if label == min_val:
                    return key
            else:
                if label >= min_val and label <= max_val:
                    return key
        raise ValueError(f"label: {label} could not be converted!")

    def _convert_target(self, target):
        """ 
        Converts segmentation target (instance-segmented) according to classmap
        """ 
        # Get all unique labels in target
        target = target.copy()
        unique_labels = torch.unique(torch.tensor(target)).numpy()

        for unique_label in unique_labels:
            # Get respective obj class label
            label_name = self._get_label_name(unique_label)
            class_label = self.classmap[label_name]
            # Convert instance label to object class label
            print("converting", unique_label, "to", class_label)
            target[target == unique_label] = class_label
        return target

    def __getitem__(self, index: int):
        img_path = self.file_paths[index]
        target_path = self.target_paths[index]

        # Load image
        img = self._pil_loader(img_path, is_target=False)
        img = self.transform(img)

        # Load target
        target = self._pil_loader(target_path, is_target=True)
        target = self._convert_target(np.asarray(target))

        return img, target

    def __len__(self) -> int:
        return len(self.file_paths)


class EndlessCLSimDataset(DownloadableDataset):
    """ Endless-CL-Sim Dataset """ 

    def __init__(
            self,
            root: Union[str, Path] = None,
            *,
            scenario=None,
            transform=None, target_transform=None,
            download=True, semseg=False,
            labelmap=None):
        """
        Creates an instance of the Endless-Continual-Leanring-Simulator Dataset.
        This dataset is able to download and prepare datasets derived from the Endless-Continual-Learning
        Simulator, including settings of incremental classes, decrasing illumination, and 
        shifting weather conditions, as described in the paper
        A Procedural World Generation Framework for Systematic Evaluation of 
        Continual Learning (https://arxiv.org/abs/2106.02585).
        Also custom datasets are supported when following the same structure. Such can
        be obtained from the Endless-CL-Simulator standalone application (https://zenodo.org/record/4899294).

        Please note:
        1) The EndlessCLSimDataset does not provide examples directly, but 
        SubseqeunceDatasets (ClassificationSubSequence, VideoSubSequence). Each 
        SubSeqeunceDataset will contain the samples for one respective sub sequence. 

        2) For video sequences currently only one sequence per dataset is supported!

        :param root: root for the datasets data. Defaults to None, which means
        that the default location for 'endless-cl-sim' will be used.
        :param scenario: identifier for the dataset to be used. Predefined options 
            are 'Classes', for incremental classes scenario, 'Illumination', for the 
            decreasing lighting scenario, and 'Weather', for the scenario of
            shifting weather conditions. 
            To load a custom (non-predefined/downloadable) dataset, the identifier
            needs to be set to None.
            Defaults to None.
        :param transform: optional transformations to be applied to the image data.
        :param target_transform: optional transformations to be applied to the targets.
        :param download: boolean to automatically download data. 
            Defaults to True.
        :param semseg: boolean to indicate the use of targets for a semantic segmentation task. 
            Defaults to False.
        :param labelmap: dictionary mapping 'class-names'(str) to class-labels(int). 
            The 'class-names' are derived from the sub-directory names for each subsequence.
        """

        if root is None:
            root = default_dataset_location('endless-cl-sim')

        if scenario is None and download:
            raise ValueError("No scenario defined to download!")

        super(EndlessCLSimDataset, self).__init__(
            root, download=download, verbose=True)

        self.scenario = scenario
        self.transform = transform
        self.target_transform = target_transform
        self.semseg = semseg

        self.train_sub_sequence_datasets = []
        self.test_sub_sequence_datasets = []

        # Download the dataset and initialize metadata
        self._load_dataset()
        return

    def _get_scenario_data(self):
        """
        Returns:
            tuple: ("DataName.zip", "download-url", "MD5-checksum") of a derived data
            to be used, as defined in endless_cl_sim_data.py
        """
        data = endless_cl_sim_data.data
        # Video data
        if self.semseg:
            if self.scenario == "Classes":
                return data[3]
            if self.scenario == "Illumination":
                return data[4]
            if self.scenario == "Weather":
                return data[5]
        # Image-patch (classification) data
        if self.scenario == "Classes":
            return data[0]
        if self.scenario == "Illumination":
            return data[1]
        if self.scenario == "Weather":
            return data[2]

        raise ValueError("Provided 'scenario' parameter is not valid!")

    def _prepare_classification_subsequence_datasets(self, path) -> bool:
        """
        Args:
            path (str): Path to the root of the data to be loaded.

        Returns:
            success (bool): Boolean wether the preparation was successfull.
        """
        # Get sequence dirs
        sequence_paths = glob.glob(path + os.path.sep + "*" + os.path.sep)

        # For every sequence (train, test)
        for sequence_path in sequence_paths:
            sub_sequence_paths = glob.glob(
                sequence_path + os.path.sep + "*" + os.path.sep)
            # Get sub-sequence dirs (0,1,....,n)       
            for sub_sequence_path in sub_sequence_paths:
                image_paths = []
                targets = []

                # Get class dirs
                class_name_dirs = [f.name for f
                                   in os.scandir(sub_sequence_path + os.path.sep) if f.is_dir()]

                # Load file_paths and targets
                for class_name in class_name_dirs:
                    try:
                        label = endless_cl_sim_data.default_classification_labelmap[class_name]
                    except:
                        ValueError(
                            f"{class_name} is not part of the provided labelmap!")
                    class_path = sub_sequence_path + class_name + os.path.sep
                    for file_name in os.listdir(class_path):
                        image_paths.append(class_path + file_name)
                        targets.append(label)

                # Create sub-sequence dataset
                subseqeunce_dataset = ClassificationSubSequence(image_paths, targets, 
                                                                transform=self.transform, target_transform=self.target_transform)
                if "train" in (sequence_path.lower()):
                    self.train_sub_sequence_datasets.append(subseqeunce_dataset)
                elif "test" in (sequence_path.lower()):
                    self.test_sub_sequence_datasets.append(subseqeunce_dataset)
                else:
                    raise ValueError(
                        "Sequence path contains neighter 'train' not 'test' identifier!")

        # Check number of train and test subsequence datasets are equal
        if self.verbose:
            print("Num train subsequences:", len(self.train_sub_sequence_datasets),
                  "Num test subsequences:", len(self.test_sub_sequence_datasets))
        assert(len(self.train_sub_sequence_datasets)
               == len(self.test_sub_sequence_datasets))

        # Has run without errors
        if self.verbose:
            print("Successfully created subsequence datasets..")
        return True

    def _load_sequence_indices(self, sequence_file):
        sequence_indices = {}
        with open(sequence_file) as file:
            json_array = json.load(file)

            for i in range(len(json_array)):
                sequence_indices[i] = json_array[i]["Sequence"]["ImageCounter"]
        return sequence_indices

    def _prepare_video_subsequence_datasets(self, path) -> bool:
        """
        Args:
            path (str): Path to the root of the data to be loaded.

        Returns:
            success (bool): Boolean wether the preparation was successfull.
        """
        # Get sequence dirs
        sequence_paths = glob.glob(path + os.path.sep + "*" + os.path.sep)

        # For every sequence (train, test)
        for sequence_path in sequence_paths:
            # Get dir contents (data + files)
            data_contents = glob.glob(sequence_path + os.path.sep + "*")
            print("data_contents:")
            print(data_contents)

            image_paths = []
            target_paths = []
            sequence_file = None
            segmentation_file = None

            # Get Color, Seg dirs  # TODO: Normals, Depth
            for data_content in data_contents:
                # If directory
                if Path(data_content).is_dir():
                    print(data_content, "is dir")
                    dir_name = data_content.split(os.path.sep)[-1]
                    if "Color" == dir_name:
                        print("Color dir found!")
                        # Extend color path
                        color_path = data_content + os.path.sep + "0" + os.path.sep
                        # Get all files
                        for file_name in sorted(os.listdir(color_path)):
                            image_paths.append(color_path + file_name)
                    elif "Seg" == dir_name:
                        print("Seg dir found")
                        # Extend seg path
                        seg_path = data_content + os.path.sep + "0" + os.path.sep
                        # Get all files
                        for file_name in sorted(os.listdir(seg_path)):
                            target_paths.append(seg_path + file_name)

                # If file
                if Path(data_content).is_file():
                    print(data_content, "is file")
                    if "Sequence.json" in data_content:
                        sequence_file = data_content
                        print("Sequence file found!")
                    elif "Segmentation.json" in data_content:
                        segmentation_file = data_content
                        print("Segmentation file found!")

            # Final checks
            if not len(image_paths) == len(target_paths):
                print("Not equal number of images and targets!")
                return False
            if sequence_file is None:
                print("No Sequence.json found!")
                return False
            if segmentation_file is None:
                print("No Segmentation.json found!")
                return False

            if self.verbose:
                print("All metadata checks complete!")

            sequence_indices = self._load_sequence_indices(
                sequence_file=sequence_file)

            if self.verbose:
                print("Seqeunce file loaded..")

            print("Sequnce indeices:", sequence_indices)

            for i in range(len(sequence_indices)):
                print("subsequence index:", i)
                last_index = sequence_indices[i]
                if (i+1) == len(sequence_indices):
                    next_index = len(image_paths)
                else:
                    next_index = sequence_indices[i+1]

                image_subsequence_paths = image_paths[last_index:next_index]
                target_subsequence_paths = target_paths[last_index:next_index]

                assert(len(image_subsequence_paths) ==
                       len(target_subsequence_paths))

                # Create subsequence dataset
                subsequence_dataset = VideoSubSequence(image_subsequence_paths, 
                                                       target_subsequence_paths,
                                                       segmentation_file, transform=self.transform,
                                                       target_transform=self.target_transform)
                if "train" in (sequence_path.lower()):
                    self.train_sub_sequence_datasets.append(subsequence_dataset)
                elif "test" in (sequence_path.lower()):
                    self.test_sub_sequence_datasets.append(subsequence_dataset)
                else:
                    raise ValueError(
                        "Sequence path contains neighter 'train' nor 'test' identifiers!")

        print("train sets:", len(self.train_sub_sequence_datasets))
        print("test sets:", len(self.test_sub_sequence_datasets))
        return True

    def __getitem__(self, index):
        """
        Args:
            index (int): Index

        Returns:
            tuple: (TrainSubSeqquenceDataset, TestSubSequenceDataset), the i-th subsequence
            data, as requested by the provided index.
        """
        return self.train_sub_sequence_datasets[index], self.test_sub_sequence_datasets[index]

    def __len__(self):
        return len(self.train_sub_sequence_datasets)

    def _download_dataset(self) -> None:
        data_name = self._get_scenario_data()

        if self.verbose:
            print("Downloading " + data_name[1] + "...")
        file = self._download_file(data_name[1], data_name[0], data_name[2])
        if data_name[1].endswith('.zip'):
            if self.verbose:
                print(f'Extracting {data_name[0]}...')
            extract_subdir = data_name[0].split(".")[0]
            extract_root = self._extract_archive(file, extract_subdir)

            # see all extracted files and extract all .zip again
            extract_root_file_list = glob.glob(str(extract_root) + "/*")
            for file_name in extract_root_file_list:
                sub_file_name = file_name.split("/")[-1]
                extract_subsubdir = extract_subdir + \
                    "/" + sub_file_name.split(".")[0]
                if self.verbose:
                    print(f"Extracting: {sub_file_name} to {extract_subdir}")
                self._extract_archive(
                    file_name, extract_subdir, remove_archive=True)
                if self.verbose:
                    print("Extraction complete!")

            if self.verbose:
                print("All extractions complete!")

    def _load_metadata(self) -> bool:
        # If a 'named'-scenario has been selected
        if not self.scenario is None:
            print("using named scenario")
            # Get data name
            scenario_data_name = self._get_scenario_data()
            scenario_data_name = scenario_data_name[0].split(".")[0]
            # Check matching directory exists in endless_cl_sim_data
            match_path = None
            for data_name in endless_cl_sim_data.data:
                name = data_name[0].split(".")[0]
                # Omit non selected directories
                if str(scenario_data_name) == str(name):
                    # Check there is such a directory
                    if (self.root / name).exists():
                        if not match_path is None:
                            raise ValueError(
                                "Two directories match the selected scenario!")
                        match_path = str(self.root / name)

            print("match_path:", match_path)
            if match_path is None:
                return False

            if not self.semseg:     
                is_subsequence_preparation_done = self._prepare_classification_subsequence_datasets(
                    match_path)
            else:
                print("preparing video..")
                is_subsequence_preparation_done = self._prepare_video_subsequence_datasets(
                    match_path)

            if is_subsequence_preparation_done and self.verbose:
                print("Data is loaded..")
            else:
                return False    
            return True

        # If a 'generic'-endless-cl-sim-scenario has been selected
        if not self.semseg:
            is_subsequence_preparation_done = self._prepare_classification_subsequence_datasets(
                str(self.root))
        else:
            print("preparing video..")
            is_subsequence_preparation_done = self._prepare_video_subsequence_datasets(
                str(self.root))

        if is_subsequence_preparation_done and self.verbose:
            print("Data is loaded...")
        else:
            return False

        # Finally
        return True

    def _download_error_message(self) -> str:
        scenario_data_name = self._get_scenario_data()
        all_urls = [
            name_url[1] for name_url in scenario_data_name
        ]

        base_msg = \
            '[Endless-CL-Sim] Error downloading the dataset!\n' \
            'You should download data manually using the following links:\n'

        for url in all_urls:
            base_msg += url 
            base_msg += '\n'

        base_msg += 'and place these files in ' + str(self.root)

        return base_msg


if __name__ == "__main__":
    from torch.utils.data.dataloader import DataLoader
    import matplotlib.pyplot as plt
    from torchvision import transforms
    import torch

    _default_transform = transforms.Compose([
        transforms.ToTensor()])

    data = EndlessCLSimDataset(scenario="Classes", root="/data/avalanche",
                               semseg=True, transform=_default_transform)
    # data = EndlessCLSimDataset(scenario=None, download=False, root="/data/avalanche/IncrementalClasses_Classification",
    #        transform=transforms.ToTensor())

    print("num subseqeunces: ", len(data.train_sub_sequence_datasets))

    sub_sequence_index = 0
    subsequence = data.train_sub_sequence_datasets[sub_sequence_index]

    print(
        f"num samples in subseqeunce {sub_sequence_index} = {len(subsequence)}")

    dataloader = DataLoader(subsequence, batch_size=1)

    for i, (img, target) in enumerate(dataloader):
        print(i)
        print(img.shape)
        img = torch.squeeze(img)
        img = transforms.ToPILImage()(img)        
        print("img size:", img.size)
        print("targets:", np.unique(target))
        # plt.imshow(img)
        # plt.show()
        break
    print("Done...")


__all__ = [
    'EndlessCLSimDataset'
]
