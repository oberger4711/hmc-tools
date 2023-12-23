#!/usr/bin/env python3

import argparse
import os
import subprocess

def parse_args():
    parser = argparse.ArgumentParser(description="Converts AVCHD recordings from Panasonic HMC150 for editing (DNxHD) or viewing / sharing (MP4).")
    parser.add_argument("dir", type=str, help="The directory which contains .MTS files somewhere.")
    parser.add_argument("-s", "--for-sharing", action="store_true", help="Convert to MP4 (much smaller files for e. g. Google Drive.")
    parser.add_argument("--deinterlace", action="store_true", help="Add deinterlacing step.")
    return parser.parse_args()

def find_mts_file_pathes(directory):
    mts_file_pathes = []
    for d_path, _, f_names in os.walk(directory):
        for f_name in f_names:
            f_path = os.path.join(d_path, f_name)
            if f_path.endswith(".MTS"):
                mts_file_pathes += [f_path]
    return sorted(mts_file_pathes)

def convert_mts_files(mts_file_pathes, ffmpeg_options_string, out_dir):
    ffmpeg_options = ffmpeg_options_string.split(" ")
    for mts_file_path in mts_file_pathes:
        _, mts_file_name = os.path.split(mts_file_path)
        mp4_file_path = os.path.join(out_dir, mts_file_name[:-4] + ".mp4") # Replace ending.
        cmd = "ffmpeg -loglevel 24 -y -i".split(" ") + [mts_file_path] + ffmpeg_options + "-f mp4".split(" ") + [mp4_file_path]
        print(" ".join(cmd))
        res = subprocess.run(cmd)
        if res.returncode != 0:
            print("ffmpeg returned an error! Aborting.")
            exit(1)

def try_mk_dir(out_dir):
    try:
        os.mkdir(out_dir)
    except FileExistsError:
        print("Output directory {} already exists.".format(out_dir))

def main():
    args = parse_args()
    mts_file_pathes = find_mts_file_pathes(args.dir)
    ffmpeg_options = None
    if args.for_sharing:
        # For sharing
        ffmpeg_options = "-c:v mpeg4 -q:v 1 -c:a aac"
        out_dir = args.dir + "_s"
    else:
        # For editing
        ffmpeg_options = "-c:v dnxhd -b:v 145M -q:v 1 -c:a pcm_s16be"
        out_dir = args.dir + "_c"
    if args.deinterlace:
        ffmpeg_options += " -vf yadif"
    try_mk_dir(out_dir)
    convert_mts_files(mts_file_pathes, ffmpeg_options, out_dir)

if __name__ == "__main__":
    main()
