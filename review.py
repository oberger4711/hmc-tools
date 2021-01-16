#!/usr/bin/env python3

import argparse
import os
import subprocess

MTS_FILE_ENDING = ".MTS"
MOV_FILE_ENDING = ".mov"

def parse_args():
    parser = argparse.ArgumentParser(description="Tool to quickly check the (converted) footage and remove bad clips.")
    parser.add_argument("dir", type=str, help="The directory which contains .MOV files or .MTS files.")
    return parser.parse_args()

def find_file_pathes(directory, ending):
    file_pathes = []
    for d_path, _, f_names in os.walk(directory):
        for f_name in f_names:
            f_path = os.path.join(d_path, f_name)
            if f_path.endswith(ending):
                file_pathes += [f_path]
    return file_pathes

class Clip:
    def __init__(self, mov_file_path, mts_file_path):
        self.mov_file_path = mov_file_path
        self.mts_file_path = mts_file_path
        operation = "none"

def get_file_name_base(file_path, ending):
    return os.path.basename(file_path)[:-len(ending)]

def find_clips(mts_dir, mov_dir):
    mts_file_pathes = find_file_pathes(mts_dir, MTS_FILE_ENDING)
    mov_file_pathes = find_file_pathes(mov_dir, MOV_FILE_ENDING)
    mts_files = {} # File name base (no ending) -> complete path
    for mts_fp in mts_file_pathes:
        fn_base = get_file_name_base(mts_fp, MTS_FILE_ENDING)
        mts_files[fn_base] = mts_fp
    clips = []
    for mov_fp in sorted(mov_file_pathes):
        fn_base = os.path.basename(mov_fp)[:-len(MOV_FILE_ENDING)]
        if fn_base in mts_files:
            clips += [Clip(mov_fp, mts_files[fn_base])]
        else:
            print("Could not find MTS clip for {}.".format(mov_fp))
    return clips

def review_files(clips):
    # TODO: Run cvlc --play-and-exit, which can be stopped with ctrl-w.
    pass

def main():
    args = parse_args()
    if args.dir.endswith("_s"):
        # MOV dir was given. Derive MTS dir.
        mov_dir = args.dir
        mts_dir = mov_dir[:-2]
    else:
        # MTS dir was given. Derive MOV dir.
        mts_dir = args.dir
        mov_dir = mts_dir + "_s"
    clips = find_clips(mts_dir, mov_dir)
    if len(clips) == 0:
        print("Could not find any clips.")
        return 0
    for c in clips:
        print("mov: {}, mts: {}".format(c.mov_file_path, c.mts_file_path))
    review_files(clips)

if __name__ == "__main__":
    main()
