import serial
import time
import re
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QGridLayout, QPushButton
import PyQt5
import yaml
import os

# from PyQt5.QtCore.Qt import AlignHCenter
from functools import partial
from jvbot.hardware.helpers import get_port


MODULE_DIR = os.path.dirname(__file__)
with open(os.path.join(MODULE_DIR, "hardwareconstants.yaml"), "r") as f:
    constants = yaml.load(f, Loader=yaml.FullLoader)


class Gantry:
    def __init__(self, port=None):
        # communication variables
        if port is None:
            self.port = get_port(constants["gantry"]["device_identifiers"])
        else:
            self.port = port

        print(self.port)
        self.POLLINGDELAY = constants["gantry"][
            "pollingrate"
        ]  # delay between sending a command and reading a response, in seconds

        # gantry variables
        self.__LIMITS = constants["gantry"]["limits"]  # coordinate system for gantry
        self.__ZLIM = self.__LIMITS["z_min"]
        self.LOAD_COORDINATES = constants["gantry"][
            "load_coordinates"
        ]  # where to move the gantry to load trays

        self.position = [
            None,
            None,
            None,
        ]  # start at None's to indicate stage has not been homed.
        self.__targetposition = [None, None, None]
        self.GANTRYTIMEOUT = constants["gantry"][
            "timeout"
        ]  # max time allotted to gantry motion before flagging an error, in seconds
        self.POSITIONTOLERANCE = constants["gantry"][
            "positiontolerance"
        ]  # tolerance for position, in mm
        self.ZHOP_HEIGHT = -constants["gantry"][
            "zhop_height"
        ]  # mm above endpoints to move to in between points. note negative because z=0 is top of build volume

        self.connect()  # connect by default

    # communication methods
    def connect(self):
        self._handle = serial.Serial(port=self.port, timeout=1, baudrate=115200)
        self.update()
        # self.update_gripper()
        if self.position == [
            self.__LIMITS["x_max"],
            self.__LIMITS["y_max"],
            self.__LIMITS["z_max"],
        ]:  # this is what it shows when initially turned on, but not homed
            self.position = [
                None,
                None,
                None,
            ]  # start at None's to indicate stage has not been homed.
        self.set_defaults()
        print("Connected to gantry")

    def disconnect(self):
        self._handle.close()
        del self._handle

    def set_defaults(self):
        self.write("M501")  # load defaults from EEPROM
        self.write("G90")  # absolute coordinate system
        self.write(
            "M92 X53.0 Y53.0 Z3200.0"
        )  # feedrate steps/mm, randomly resets to defaults sometimes idk why
        self.write(
            "M201 X250.0 Y250.0 Z10.0"
        )  # acceleration steps/mm/mm, randomly resets to defaults sometimes idk why
        self.write(
            "M906 X580 Y580 Z25 E1"
        )  # set max stepper RMS currents (mA) per axis. E = extruder, unused to set low
        self.write(
            "M84 S0"
        )  # disable stepper timeout, steppers remain engaged all the time
        self.write(
            f"M203 X50 Y50 Z1.00"
        )  # set max speeds, steps/mm. Z is hardcoded, limited by lead screw hardware.

    def write(self, msg):
        #print("We are in selfwrite")
        self._handle.write(f"{msg}\n".encode())
        time.sleep(self.POLLINGDELAY)
        output = []
        while self._handle.in_waiting:
            line = self._handle.readline().decode("utf-8").strip()
            if line != "ok":
                output.append(line)
            time.sleep(self.POLLINGDELAY)
        return output

    def _enable_steppers(self):
        self.write("M17")

    def _disable_steppers(self):
        self.write("M18")

    def update(self):
        found_coordinates = False
        while not found_coordinates:
            output = self.write("M114")  # get current position
            for line in output:
                if line.startswith("X:"):
                    x = float(re.findall(r"X:(\S*)", line)[0])
                    y = float(re.findall(r"Y:(\S*)", line)[0])
                    z = float(re.findall(r"Z:(\S*)", line)[0])
                    found_coordinates = True
                    break
        self.position = [x, y, z]

    # gantry methods
    def gohome(self):
        self.write("G28 Z")
        self.update()
        self.write("G28 X Y")
        self.update()
        self.movetoload()

    def premove(self, x, y, z):
        """
        checks to confirm that all target positions are valid
        """
        if self.position == [None, None, None]:
            raise Exception(
                "Stage has not been homed! Home with self.gohome() before moving please."
            )
        if x is None:
            x = self.position[0]
        if y is None:
            y = self.position[1]
        if z is None:
            y = self.position[2]

        return x, y, z

    def moveto(self, x=None, y=None, z=None, zhop=True):
        """
        moves to target position in x,y,z (mm)
        """
        try:
            if len(x) == 3:
                x, y, z = x  # split 3 coordinates into appropriate variables
        except:
            pass
        
        # here it seems to override that x,y,z
        x, y, z = self.premove(x, y, z)  # will error out if invalid move

        if (x == self.position[0]) and (y == self.position[1]):
            zhop = False  # no use zhopping for no lateral movement
        if zhop:
            z_ceiling = (
                min(self.position[2], z) + self.ZHOP_HEIGHT
            )
            # closest z coordinate to bottom along path
            z_floor = max(
                z_ceiling, self.__ZLIM
            )  # cant z-hop above build volume. mostly here for first move after homing.
            self.moveto(z=z_ceiling, zhop=False)
            self.moveto(x, y, z_ceiling, zhop=False)
            self.moveto(z=z, zhop=False)
        else:
            self._movecommand(x, y, z)

    def movetoload(self):
        self.moveto(self.LOAD_COORDINATES)

    def _movecommand(self, x: float, y: float, z: float):
        """internal command to execute a direct move from current location to new location"""
        if self.position == [x, y, z]:
            return True  # already at target position
        else:
            self.__targetposition = [x, y, z]
            self.write(f"G0 X{x} Y{y} Z{z}")
            return self._waitformovement()

    def moverel(self, x=0, y=0, z=0, zhop=False):
        """
        moves by coordinates relative to the current position
        """
        try:
            if len(x) == 3:
                x, y, z = x  # split 3 coordinates into appropriate variables
        except:
            pass
        x += self.position[0]
        y += self.position[1]
        z += self.position[2]
        self.moveto(x, y, z, zhop)

    def _waitformovement(self):
        """
        confirm that gantry has reached target position. returns False if
        target position is not reached in time allotted by self.GANTRYTIMEOUT
        """
        self.inmotion = True
        start_time = time.time()
        time_elapsed = time.time() - start_time
        self._handle.write(f"M400\n".encode())
        self._handle.write(f"M118 E1 FinishedMoving\n".encode())
        reached_destination = False
        while not reached_destination and time_elapsed < self.GANTRYTIMEOUT:
            time.sleep(self.POLLINGDELAY)
            while self._handle.in_waiting:
                line = self._handle.readline().decode("utf-8").strip()
                if line == "echo:FinishedMoving":
                    self.update()
                    if (
                        np.linalg.norm(
                            [
                                a - b
                                for a, b in zip(self.position, self.__targetposition)
                            ]
                        )
                        < self.POSITIONTOLERANCE
                    ):
                        reached_destination = True
                time.sleep(self.POLLINGDELAY)
            time_elapsed = time.time() - start_time

        self.inmotion = ~reached_destination
        self.update()
        return reached_destination

    # GUI
    def gui(self):
        GantryGUI(gantry=self)  # opens blocking gui to manually jog motors


class GantryGUI:
    def __init__(self, gantry):
        AlignHCenter = PyQt5.QtCore.Qt.AlignHCenter
        self.gantry = gantry
        self.app = PyQt5.QtCore.QCoreApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        self.app.aboutToQuit.connect(self.app.deleteLater)
        self.win = QWidget()
        self.grid = QGridLayout()
        self.stepsize = 1  # default step size, in mm

        ### axes labels
        for j, label in enumerate(["X", "Y", "Z"]):
            temp = QLabel(label)
            temp.setAlignment(AlignHCenter)
            self.grid.addWidget(temp, 0, j)

        ### position readback values
        self.xposition = QLabel("0")
        self.xposition.setAlignment(AlignHCenter)
        self.grid.addWidget(self.xposition, 1, 0)

        self.yposition = QLabel("0")
        self.yposition.setAlignment(AlignHCenter)
        self.grid.addWidget(self.yposition, 1, 1)

        self.zposition = QLabel("0")
        self.zposition.setAlignment(AlignHCenter)
        self.grid.addWidget(self.zposition, 1, 2)

        self.update_position()

        ### status label
        self.gantrystatus = QLabel("Idle")
        self.gantrystatus.setAlignment(AlignHCenter)
        self.grid.addWidget(self.gantrystatus, 5, 4)

        ### jog motor buttons
        self.jogback = QPushButton("Back")
        self.jogback.clicked.connect(partial(self.jog, y=-1))
        self.grid.addWidget(self.jogback, 3, 1)

        self.jogforward = QPushButton("Forward")
        self.jogforward.clicked.connect(partial(self.jog, y=1))
        self.grid.addWidget(self.jogforward, 2, 1)

        self.jogleft = QPushButton("Left")
        self.jogleft.clicked.connect(partial(self.jog, x=-1))
        self.grid.addWidget(self.jogleft, 3, 0)

        self.jogright = QPushButton("Right")
        self.jogright.clicked.connect(partial(self.jog, x=1))
        self.grid.addWidget(self.jogright, 3, 2)

        self.jogup = QPushButton("Up")
        self.grid.addWidget(self.jogup, 2, 3)
        self.jogup.clicked.connect(partial(self.jog, z=-1))

        self.jogdown = QPushButton("Down")
        self.jogdown.clicked.connect(partial(self.jog, z=1))
        self.grid.addWidget(self.jogdown, 3, 3)

        ### step size selector buttons
        self.steppt1 = QPushButton("0.1 mm")
        self.steppt1.clicked.connect(partial(self.set_stepsize, stepsize=0.1))
        self.grid.addWidget(self.steppt1, 5, 0)
        self.step1 = QPushButton("1 mm")
        self.step1.clicked.connect(partial(self.set_stepsize, stepsize=1))
        self.grid.addWidget(self.step1, 5, 1)
        self.step10 = QPushButton("10 mm")
        self.step10.clicked.connect(partial(self.set_stepsize, stepsize=10))
        self.grid.addWidget(self.step10, 5, 2)

        self.stepsize_options = {
            0.1: self.steppt1,
            1: self.step1,
            10: self.step10,
        }

        self.set_stepsize(self.stepsize)

        self.run()

    def set_stepsize(self, stepsize):
        self.stepsize = stepsize
        for setting, button in self.stepsize_options.items():
            if setting == stepsize:
                button.setStyleSheet("background-color: #a7d4d2")
            else:
                button.setStyleSheet("background-color: None")

    def jog(self, x=0, y=0, z=0):
        self.gantrystatus.setText("Moving")
        self.gantrystatus.setStyleSheet("color: red")
        self.gantry.moverel(x * self.stepsize, y * self.stepsize, z * self.stepsize)
        self.update_position()
        self.gantrystatus.setText("Idle")
        self.gantrystatus.setStyleSheet("color: None")

    def update_position(self):
        for position, var in zip(
            self.gantry.position, [self.xposition, self.yposition, self.zposition]
        ):
            var.setText(f"{position:.2f}")

    def run(self):
        self.win.setLayout(self.grid)
        self.win.setWindowTitle("JVBot Gantry GUI")
        self.win.setGeometry(300, 300, 500, 150)
        self.win.show()
        self.app.setQuitOnLastWindowClosed(True)
        self.app.exec_()
        return
