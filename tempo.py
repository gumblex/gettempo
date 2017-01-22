#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright (C) 2017 gumblex

# This program is free software. It comes without any warranty, to
# the extent permitted by applicable law. You can redistribute it
# and/or modify it under the terms of the Do What The Fuck You Want
# To Public License, Version 2, as published by Sam Hocevar. See
# http://www.wtfpl.net/ for more details.

import os
import io
import time
import threading
import collections

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

try:
    import pyaudio
    import wave
    has_pyaudio = True
except ImportError:
    has_pyaudio = False


class GridWindow(Gtk.Window):

    def __init__(self):
        Gtk.Window.__init__(self, title="Tempo")
        self.set_border_width(10)
        self.set_resizable(False)

        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(10)
        self.add(grid)

        self.label1 = Gtk.Label("Measure")
        self.label2 = Gtk.Label("Tempo×2")
        self.label3 = Gtk.Label("BPM")
        self.label4 = Gtk.Label("Metronome")
        self.toggle_start = Gtk.ToggleButton(label="Active")
        self.toggle_start.connect("toggled", self.on_button_toggled)
        self.switch_x2 = Gtk.Switch()
        self.switch_x2.set_active(False)
        self.switch_x2.connect("notify::active", self.on_switch_activated)
        self.adj_spin = Gtk.Adjustment(60, 30, 300, 1, 10, 0)
        self.spin_bpm = Gtk.SpinButton()
        self.spin_bpm.set_adjustment(self.adj_spin)
        self.adj_spin.set_value(60)
        self.adj_spin.connect("value-changed", self.on_spin_changed)
        self.switch_mt = Gtk.Switch()
        self.switch_mt.set_active(False)
        self.switch_mt.set_sensitive(False)
        self.button_beat = Gtk.Button(label="Beat")
        self.button_beat.set_sensitive(False)
        self.button_beat.connect("clicked", self.on_beat)

        grid.attach(self.label1, 0, 0, 1, 1)
        grid.attach(self.label2, 0, 1, 1, 1)
        grid.attach(self.label3, 0, 2, 1, 1)
        grid.attach(self.label4, 0, 3, 1, 1)
        grid.attach(self.toggle_start, 1, 0, 1, 1)
        grid.attach(self.switch_x2, 1, 1, 1, 1)
        grid.attach(self.spin_bpm, 1, 2, 1, 1)
        grid.attach(self.switch_mt, 1, 3, 1, 1)
        grid.attach(self.button_beat, 0, 4, 2, 1)
        self.connect("delete-event", self.on_delete)

        if has_pyaudio:
            self.switch_mt.set_sensitive(True)
            self.metronome = Metronome()
            self.switch_mt.connect("notify::active", self.on_metronome_activated)

        self.tempox = 1
        self.lastbpm = 0
        self.reset_state()

    def reset_state(self):
        self.intervals = collections.deque(maxlen=20)
        self.lastbeat = 0
        self.invalidbeats = 0
        self.stabletimes = 0

    def on_switch_activated(self, switch, gparam):
        if self.switch_x2.get_active():
            self.tempox = 2
            self.adj_spin.set_value(self.adj_spin.get_value() * 2)
        else:
            self.tempox = 1
            self.adj_spin.set_value(self.adj_spin.get_value() // 2)

    def on_spin_changed(self, adjustment):
        if has_pyaudio and self.switch_mt.get_active():
            self.metronome.interval = 60 / self.adj_spin.get_value()

    def on_metronome_activated(self, switch, gparam):
        if self.switch_mt.get_active():
            self.metronome.start(60 / self.adj_spin.get_value())
        else:
            self.metronome.stop()

    def on_button_toggled(self, button):
        if button.get_active():
            state = "on"
            self.switch_mt.set_active(False)
            self.switch_mt.set_sensitive(False)
            self.button_beat.set_sensitive(True)
            self.button_beat.grab_focus()
        else:
            state = "off"
            self.button_beat.set_sensitive(False)
            if has_pyaudio:
                self.switch_mt.set_sensitive(True)
            self.reset_state()

    def on_beat(self, button):
        if self.invalidbeats > 4:
            now = time.time()
            self.intervals.append(now - self.lastbeat)
            self.lastbeat = now
            bpm = round(60 * len(self.intervals) * self.tempox / sum(self.intervals))
            self.adj_spin.set_value(bpm)
            if self.lastbpm == bpm:
                self.stabletimes += 1
                if self.stabletimes > 5:
                    self.toggle_start.set_active(False)
            else:
                self.stabletimes = 0
            self.lastbpm = bpm
        else:
            self.lastbeat = time.time()
            self.invalidbeats = self.invalidbeats + 1

    def on_delete(self, widget, event):
        if has_pyaudio:
            self.metronome.close()
        Gtk.main_quit()


class Metronome:

    def __init__(self):
        with open(os.path.join(os.path.dirname(__file__), 'click.wav'), 'rb') as f:
            self.wave = io.BytesIO(f.read())
        self.wf = wave.open(self.wave, 'rb')
        self.pa = pyaudio.PyAudio()
        self.start_time = 0
        self.closing = False
        self.interval = 0
        self.sleep = time.sleep
        self.thread = None

    def tick(self):
        def callback(in_data, frame_count, time_info, status):
            data = self.wf.readframes(frame_count)
            return (data, pyaudio.paContinue)

        self.wf.rewind()
        stream = self.pa.open(
            format=self.pa.get_format_from_width(self.wf.getsampwidth()),
            channels=self.wf.getnchannels(),
            rate=self.wf.getframerate(),
            output=True,
            stream_callback=callback
        )
        stream.start_stream()
        while stream.is_active() and self.start_time:
            self.sleep(0.05)
        stream.stop_stream()
        stream.close()

    def start(self, interval):
        self.interval = interval
        self.thread = threading.Thread(target=self.background)
        self.thread.start()

    def background(self):
        self.start_time = time.monotonic()
        while self.start_time:
            self.tick()
            self.sleep_interval(self.interval)

    def sleep_interval(self, interval):
        now = time.monotonic()
        preset = now + interval - ((now - self.start_time) % interval)
        while self.start_time:
            delta = preset - time.monotonic()
            if delta <= 0:
                return
            elif delta >= 0.05:
                time.sleep(delta/2)

    def stop(self):
        self.start_time = 0

    def close(self):
        self.stop()
        self.sleep(0.01)
        self.pa.terminate()


if __name__ == '__main__':
    win = GridWindow()
    win.show_all()
    Gtk.main()
