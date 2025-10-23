import os
import yaml
import shutil
import pickle as pkl
from natsort import natsorted
import csv
from datetime import datetime
from tqdm import tqdm
from frgtools import jv


MODULE_DIR = os.path.dirname(__file__)
TRAY_VERSIONS_DIR = os.path.join(MODULE_DIR, "tray_versions")
AVAILABLE_VERSIONS = {
    os.path.splitext(f)[0]: os.path.join(TRAY_VERSIONS_DIR, f)
    for f in os.listdir(TRAY_VERSIONS_DIR)
    if ".yaml" in f
}

from jvbot.hardware.gantry import Gantry
from jvbot.hardware.control3 import Control_Keithley
from jvbot.hardware.control5 import Control_Keithley_Eric 
from jvbot.hardware.tray import Tray


class Control:
    def __init__(self, area=0.048, Eric_Opt = None):
        self.area = area  # cm2
        if Eric_Opt is None:
            response = self._prompt_for_input("Do you want to use Eric's Scan-Rate Sweeps or Dark JV's? (y/n)")
            if response in ['y', 'Y']:
                self.control_keithley = Control_Keithley_Eric(area=self.area)
            else:        
                self.control_keithley = Control_Keithley(area=self.area)
        self.gantry = Gantry()

    def _prompt_for_input(s):
        response = input(s)
        return response
    def set_tray(self, version:str, calibrate:bool = False):
        self.gantry.moveto([55,24,30])
        self.tray = Tray(version=version, gantry=self.gantry, calibrate=calibrate)

    def scan_cell(
            self,
            name,
            vmin,
            vmax,
            direction = 'fwdrev',
            vsteps = 50,
            light = True,
            preview = True
        ): 
        
        """
            Conducts a JV scan, previews data, saves file
            
            Args:
                name (string): name of device
                direction (string): direction -- fwd, rev, fwdrev, or revfwd
                vmin (float): start voltage for JV sweep (V)
                xmax (float): end voltage for JV sweep (V)
                vsteps (int = 50): number of voltage steps between max and min
                light (boolean = True): boolean to describe status of light
                preview (boolean = True): boolean to determine if data is plotted
        """

        self.control_keithley.jv(name=name, direction=direction, vmin=vmin, vmax=vmax, vsteps=vsteps, light=light, preview=preview)

    def scan_tray(
            self,
            vmin,
            vmax,
            direction = 'revfwd',
            vsteps = 50,
            repeat_scans=1,
            initial_slot=None,
            final_slot=None,
            slots=None,
            light=True,
            preview=True
        ):

        allslots = natsorted(list(self.tray._coordinates.keys()))
        if final_slot == None:
            slots = allslots
        else: # if a final slot is specified
            final_idx = allslots.index(final_slot)
            if initial_slot is not None:
                initial_idx = allslots.index(initial_slot)
                slots = allslots[initial_idx:final_idx+1]
            else:
                slots = allslots[:final_idx+1]

        if slots is None:
            raise ValueError("Either final_slot or slots must be specified!")

        for slot in tqdm(slots, desc="Scanning Tray"):
            self.gantry.moveto(self.tray(slot))
            for i in range(repeat_scans):
                name = f"{slot}_S{i+1}"
                self.control_keithley.jv(name=name, direction=direction, vmin=vmin, vmax=vmax, vsteps=vsteps, light=light, preview=preview)

        self.gantry.movetoload()