#!/usr/bin/env python3

import argparse
import os
import subprocess
import curses
import curses.textpad
import abc

MTS_FILE_ENDING = ".MTS"
MOV_FILE_ENDING = ".mov"

def parse_args():
    parser = argparse.ArgumentParser(description="Tool to quickly check the (converted) footage and remove bad clips.")
    parser.add_argument("dir", type=str, help="The directory which contains .MOV files or .MTS files.")
    parser.add_argument("--read-only", action="store_true", help="Disables delete functionality. Clips can only be watched.")
    return parser.parse_args()

def find_file_pathes(directory, ending):
    file_pathes = []
    for d_path, _, f_names in os.walk(directory):
        for f_name in f_names:
            f_path = os.path.join(d_path, f_name)
            if f_path.endswith(ending):
                file_pathes += [f_path]
    return file_pathes

def get_file_name_base(file_path, ending):
    return os.path.basename(file_path)[:-len(ending)]

class Clip:
    def __init__(self, mov_file_path, mts_file_path, mov_file_size):
        self.mov_file_path = mov_file_path
        self.mts_file_path = mts_file_path
        assert get_file_name_base(self.mov_file_path, MOV_FILE_ENDING) == get_file_name_base(self.mts_file_path, MTS_FILE_ENDING)
        self.mov_file_size = mov_file_size
        self.file_base_name = get_file_name_base(self.mov_file_path, MOV_FILE_ENDING)
        self.played = False
        self.marked_for_del = False

def find_clips(mts_dir, mov_dir):
    mts_file_pathes = find_file_pathes(mts_dir, MTS_FILE_ENDING)
    mov_file_pathes = find_file_pathes(mov_dir, MOV_FILE_ENDING)
    mts_files = {} # File name base (no ending) -> complete path
    for mts_fp in mts_file_pathes:
        fn_base = get_file_name_base(mts_fp, MTS_FILE_ENDING)
        mts_files[fn_base] = mts_fp
    clips = []
    for mov_fp in sorted(mov_file_pathes):
        fn_base = get_file_name_base(mov_fp, MOV_FILE_ENDING)
        try:
            mov_file_size = os.path.getsize(mov_fp)
        except OSError:
            mov_file_size = 0
        if fn_base in mts_files:
            clips += [Clip(mov_fp, mts_files[fn_base], mov_file_size)]
        else:
            print("Could not find MTS clip for {}.".format(mov_fp))
    return clips

class Model:
    def __init__(self, mov_dir, mts_dir, clips):
        self.mov_dir = mov_dir
        self.mts_dir = mts_dir
        self.clips = clips

    def delete_marked_clips(self):
        to_del = [c for c in self.clips if c.marked_for_del]
        for c_to_del in to_del:
            os.remove(c_to_del.mov_file_path)
            os.remove(c_to_del.mts_file_path)
            self.clips.remove(c_to_del)

class CursesViewController:
    CP_MARK = 1
    CP_BAR = 2
    CP_PLAY = 6
    CP_DEL = 4

    class Mode(abc.ABC):
        def __init__(self, vc, name, cursor_line_attr=0, cursor_line_del_attr=None):
            self.vc = vc
            self.name = name
            self.cursor_line_attr = cursor_line_attr
            if cursor_line_del_attr is not None:
                self.cursor_line_del_attr = cursor_line_del_attr
            else:
                self.cursor_line_del_attr = curses.color_pair(CursesViewController.CP_DEL)

        @abc.abstractmethod
        def update(self):
            pass

        @abc.abstractmethod
        def handle_input(self, enter_pressed):
            return True

    class PlayMode(Mode):
        def __init__(self, vc, p):
            super().__init__(vc, "PLAY", curses.color_pair(CursesViewController.CP_PLAY))
            self.p = p

        def update(self):
            if self.p.poll() is not None:
                self.vc.switch_mode(CursesViewController.NormalMode(self.vc))

        def handle_input(self, enter_pressed):
            if self.vc.in_buf == " ":
                self.p.kill()
                self.vc.switch_mode(CursesViewController.NormalMode(self.vc))
            return True

    class NormalMode(Mode):
        def __init__(self, vc):
            super().__init__(vc, "NORMAL", curses.color_pair(CursesViewController.CP_MARK))

        def update(self):
            pass

        def handle_input(self, enter_pressed):
            in_buf = self.vc.in_buf
            if in_buf.startswith(":"):
                # Multi charactar command is being typed in.
                if enter_pressed:
                    if in_buf == ":w":
                        self.vc.save()
                    elif in_buf == ":wq":
                        self.vc.save()
                        self.vc.exit_no_save()
                    elif in_buf == ":q":
                        self.vc.exit_no_save()
                    elif in_buf == ":q!" or in_buf == ":cq":
                        self.vc.exit_no_save_forced()
                    else:
                        self.vc.set_msg("Unknown command: '{}'.".format(in_buf))
                    return True
                else:
                    return False # Command not yet complete.
            elif in_buf == "j":
                self.vc.move_cursor_line(1)
            elif in_buf == "k":
                self.vc.move_cursor_line(-1)
            elif in_buf == "g":
                self.vc.move_cursor_line_all_up()
            elif in_buf == "G":
                self.vc.move_cursor_line_all_down()
            elif in_buf == "l":
                self.vc.move_cursor_line(self.vc.rows_editor - 1)
            elif in_buf == "h":
                self.vc.move_cursor_line(-(self.vc.rows_editor - 1))
            elif in_buf == " ":
                p = self.vc.play_at_cursor_line()
                self.vc.switch_mode(CursesViewController.PlayMode(self.vc, p))
            elif in_buf == "d":
                self.vc.toggle_del_at_cursor_line()

            return True

    def __init__(self, scr, model, read_only):
        self.scr = scr
        self.model = model
        self.read_only = read_only
        self.exit = False
        self.in_buf = ""
        self.last_in = 0
        self.msg = None
        self.cursor_line = 0
        self.top_v_line = 0
        self.init_curses()
        self.mode = CursesViewController.NormalMode(self)
        self.reset()

    def __trunc_text(self, text, length):
        limit = max(0, min(self.cols, length))
        if len(text) <= limit: return text
        elif len(text) >= 3: return text[:limit-3] + "..."
        else: return "." * limit

    def __crop_text(self, text, length=999999):
        limit = max(0, min(self.cols, length))
        if len(text) <= limit: return text
        else: return text[:limit]

    def __s_addstr(self, w, row, col, text, fmt=0):
        rows, cols = w.getmaxyx()
        if col >= cols or row >= rows:
            return
        if col < 0 or row < 0:
            return
        if len(text) + col > cols:
            text = text[:cols - col]
        w.addstr(row, col, text, fmt)

    def init_curses(self):
        self.rows, self.cols = self.scr.getmaxyx()
        curses.curs_set(0)
        self.scr.timeout(100)
        curses.use_default_colors()
        curses.init_pair(CursesViewController.CP_MARK, 11, 15) # 12, 15
        curses.init_pair(CursesViewController.CP_BAR, 12, 7) # -1, 7
        curses.init_pair(CursesViewController.CP_PLAY, curses.COLOR_GREEN, curses.COLOR_WHITE) # 2, 7
        curses.init_pair(CursesViewController.CP_DEL, curses.COLOR_RED, -1) # curses.COLOR_RED, -1
        #if self.rows < 4 or self.cols < 25: exit(-1) # Should not be necessary.

    def reset_editor(self):
        self.cursor_line = max(0, min(len(self.model.clips) - 1, self.cursor_line))
        self.top_v_line = max(0, min(len(self.model.clips) - 1, self.top_v_line))
        self.rows_editor = self.rows - 2
        self.pad_editor = curses.newpad(len(self.model.clips) + 1, self.cols)
        for i, _ in enumerate(self.model.clips):
            self.refresh_line(i)
        self.refresh_editor()

    def reset(self):
        # Build windows and pads.
        self.scr.clear()
        self.scr.refresh()
        # Title bar
        self.win_title_bar = curses.newwin(1, self.cols + 1, 0, 0)
        self.refresh_title_bar()
        # Editor
        self.reset_editor()
        # Status bar
        self.win_status_bar = curses.newwin(1, self.cols + 1, self.rows - 1, 0)
        self.refresh_status_bar()

    def refresh_title_bar(self):
        self.win_title_bar.clear()
        label = self.__crop_text(" MTS / MOV: ")
        prog_name = self.__crop_text(" review ")
        # Simplify mov dir name
        if self.model.mov_dir.startswith(self.model.mts_dir):
            mov_dir_truncated = self.model.mov_dir[len(self.model.mts_dir):]
        else:
            mov_dir_truncated = self.model.mov_dir
        # Left aligned
        self.__s_addstr(self.win_title_bar, 0, 0, label, curses.color_pair(CursesViewController.CP_BAR) | curses.A_REVERSE)
        dirs_text = self.__trunc_text(" {} / {}".format(self.model.mts_dir, mov_dir_truncated), self.cols - len(label) - len(prog_name))
        self.__s_addstr(self.win_title_bar, 0, len(label), dirs_text)
        # Right aligned
        self.__s_addstr(self.win_title_bar, 0, self.cols - len(prog_name), prog_name, curses.color_pair(CursesViewController.CP_BAR) | curses.A_REVERSE)
        self.win_title_bar.refresh()

    def refresh_status_bar(self):
        self.win_status_bar.clear()
        padded_mode_name = " {} ".format(self.mode.name)
        s_last_in = " {} ".format(self.last_in)
        self.__s_addstr(self.win_status_bar, 0, 0, self.__trunc_text(padded_mode_name, self.cols - len(s_last_in)), curses.color_pair(CursesViewController.CP_BAR) | curses.A_REVERSE | curses.A_BOLD)
        if self.in_buf == "" and self.msg is not None:
            self.__s_addstr(self.win_status_bar, 0, len(padded_mode_name), " {} ".format(self.msg))
        else:
            # Show current buffer.
            self.__s_addstr(self.win_status_bar, 0, len(padded_mode_name), " {} ".format(self.in_buf))
        self.__s_addstr(self.win_status_bar, 0, self.cols - len(s_last_in), s_last_in, curses.color_pair(CursesViewController.CP_BAR) | curses.A_REVERSE)
        self.win_status_bar.refresh()

    def refresh_line(self, i):
        if i < 0 or i >= len(self.model.clips): return
        # Erase old line.
        self.pad_editor.move(i, 0)
        self.pad_editor.clrtoeol()
        clip = self.model.clips[i]
        s_file_size = " {:.1f} MB ".format(clip.mov_file_size / (1024 * 1024))
        stat = ""
        if not clip.played:
            stat += "*"
        if clip.marked_for_del:
            stat += "D"
        s_file_name = " {:2} {}".format(stat, clip.file_base_name)
        s_file_name = self.__trunc_text(s_file_name, self.cols - len(s_file_size))
        attr = 0
        if i == self.cursor_line:
            if clip.marked_for_del:
                attr |= self.mode.cursor_line_del_attr
            else:
                attr |= self.mode.cursor_line_attr
            attr |= curses.A_REVERSE
            s_file_name = s_file_name + " " * (max(0, self.cols - len(s_file_name)))
        else:
            if clip.marked_for_del:
                attr |= curses.color_pair(CursesViewController.CP_DEL)
        if not clip.played: attr |= curses.A_BOLD
        self.__s_addstr(self.pad_editor, i, 0, s_file_name, attr)
        self.__s_addstr(self.pad_editor, i, self.cols - len(s_file_size), s_file_size, attr)

    def refresh_editor(self):
        self.pad_editor.refresh(self.top_v_line, 0, 1, 0, self.rows_editor, self.cols)

    def move_cursor_line(self, inc):
        prev_cursor_line = self.cursor_line
        self.cursor_line = max(0, min(len(self.model.clips) - 1, self.cursor_line + inc))
        self.refresh_line(prev_cursor_line)
        self.refresh_line(self.cursor_line)
        # Scroll window if needed.
        lines_below_window = (self.cursor_line - self.top_v_line) - (self.rows - 3)
        lines_above_window = self.top_v_line - self.cursor_line
        if lines_below_window > 0:
            self.top_v_line += lines_below_window
        elif lines_above_window > 0:
            self.top_v_line -= lines_above_window
        self.refresh_editor()

    def move_cursor_line_all_up(self):
        prev_cursor_line = self.cursor_line
        self.cursor_line = 0
        self.top_v_line = 0
        self.refresh_line(prev_cursor_line)
        self.refresh_line(self.cursor_line)
        self.refresh_editor()

    def move_cursor_line_all_down(self):
        prev_cursor_line = self.cursor_line
        self.cursor_line = len(self.model.clips) - 1
        self.top_v_line = max(0, self.cursor_line - (self.rows_editor - 1))
        self.refresh_line(prev_cursor_line)
        self.refresh_line(self.cursor_line)
        self.refresh_editor()

    def play_at_cursor_line(self):
        clip = self.model.clips[self.cursor_line]
        mov_file_path = clip.mov_file_path
        clip.played = True
        return subprocess.Popen(["cvlc", "--play-and-exit", mov_file_path], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    def toggle_del_at_cursor_line(self):
        if self.read_only: return
        clip = self.model.clips[self.cursor_line]
        clip.marked_for_del = not clip.marked_for_del
        self.refresh_line(self.cursor_line)
        self.refresh_editor()

    def set_msg(self, msg):
        self.msg = msg
        self.refresh_status_bar()

    def switch_mode(self, mode):
        self.mode = mode
        self.refresh_status_bar()
        self.refresh_line(self.cursor_line)
        self.refresh_editor()

    def exit_no_save_forced(self):
        self.exit = True

    def exit_no_save(self):
        # Check if there are unsaved changes.
        if any(c.marked_for_del for c in self.model.clips):
            self.msg = "There are unsaved changes. Use :q! to force exit"
            return
        else:
            self.exit = True

    def save(self):
        if self.read_only: return
        self.model.delete_marked_clips()
        if len(self.model.clips) == 0:
            self.exit = True
        self.reset()

    def loop(self):
        while not self.exit:
            ch = self.scr.getch()
            if ch != -1:
                self.msg = None # Reset error message.
                if ch == curses.KEY_RESIZE:
                    # Terminal has been resized. Reset view.
                    self.init_curses()
                    self.reset()
                self.last_in = ch
                if 0x20 <= self.last_in <= 0x7e:
                    self.in_buf += chr(self.last_in) # ASCII input goes to the buffer.
                elif self.last_in == 263: # Backspace
                    self.in_buf = self.in_buf[:-1]
                enter_pressed = (self.last_in == 0xa)
                if self.mode.handle_input(enter_pressed):
                    self.in_buf = "" # Reset buffer.
                self.refresh_status_bar()
            else:
                self.mode.update()

def show_curses_ui(scr, model, read_only):
    view_controller = CursesViewController(scr, model, read_only)
    view_controller.loop()

def main():
    args = parse_args()
    # Load the data.
    if args.dir.endswith("_s"):
        # MOV dir was given. Derive MTS dir.
        mov_dir = args.dir
        mts_dir = mov_dir[:-2]
    else:
        # MTS dir was given. Derive MOV dir.
        mts_dir = args.dir
        mov_dir = mts_dir + "_s"
    if not os.path.isdir(mts_dir):
        print("MTS dir '{}' does not exist.".format(mts_dir))
    if not os.path.isdir(mov_dir):
        print("MOV dir '{}' does not exist.".format(mov_dir))
    clips = find_clips(mts_dir, mov_dir)
    if len(clips) == 0:
        print("Could not find any clips.")
        return 0
    #for i in range(len(clips)):
    #    print(i)
    model = Model(mov_dir, mts_dir, clips)
    # Start ncurses UI.
    curses.wrapper(show_curses_ui, model, args.read_only)

if __name__ == "__main__":
    main()
